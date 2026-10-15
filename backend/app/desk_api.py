"""The desk over HTTP: what was handed to the Desk and what it concluded, for everyone who
may read the screen; and a conversation with the Desk, for a signed-in user only.

A user signs in with a token. LIGHTHOUSE_DESK_USERS lists the tokens, each with the tenant
and the user it stands for, separated by commas:

    LIGHTHOUSE_DESK_USERS=<token>=<tenant>/<user>,<token>=<tenant>/<user>

The user and the tenant come from the token, never from the request: a session of one user
cannot be read or written under another name, and each tenant's sessions are in a graph of
their own. A token is at least 32 characters; make one with `openssl rand -hex 24`.
"""

import hmac
import logging
import os
import re
from functools import cache
from typing import Annotated

import lighthouse
from falkordb import Graph
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from lighthouse import ensure_schema, handoffs_for, messages, sessions
from lighthouse.values import without_words
from pydantic import BaseModel, Field

from app import desk, model
from app.api import MOST, Desk
from app.db import get_db

router = APIRouter(prefix="/api/desk")
log = logging.getLogger("lighthouse.desk")
_ENTRY = re.compile(r"([A-Za-z0-9_-]{32,})=([a-z0-9][a-z0-9_-]{0,62})/([A-Za-z0-9_.@-]{1,100})")


def _users(text: str) -> dict[str, tuple[str, str]]:
    """{token: (tenant, user)} from the text of LIGHTHOUSE_DESK_USERS."""
    found = {}
    for item in filter(None, (part.strip() for part in text.split(","))):
        match = _ENTRY.fullmatch(item)
        if not match:
            raise RuntimeError(
                "LIGHTHOUSE_DESK_USERS holds an entry that is not <token>=<tenant>/<user> with "
                "a token of at least 32 letters and digits"
            )
        token, tenant, user = match.groups()
        found[token] = (tenant, user)
    return found


def signed_in(authorization: Annotated[str | None, Header()] = None) -> tuple[str, str]:
    """The tenant and the user of the token in the Authorization header."""
    given = (authorization or "").removeprefix("Bearer ").strip()
    for token, who in _users(os.environ.get("LIGHTHOUSE_DESK_USERS", "")).items():
        if hmac.compare_digest(token.encode(), given.encode()):
            return who
    raise HTTPException(status_code=401, detail="Please sign in again.")


@cache
def _memory(tenant: str) -> Graph:
    """The tenant's own graph, with its schema."""
    graph = lighthouse.tenant(get_db(), tenant)
    ensure_schema(graph)
    return graph


User = Annotated[tuple[str, str], Depends(signed_in)]


@router.get("")
def inbox(graph: Desk, limit: Annotated[int, Query(ge=1, le=MOST)] = 20) -> dict:
    """What waits for the Desk, newest first, and what it concluded last."""
    waiting = handoffs_for(graph, desk.AGENT)
    rows = graph.ro_query(
        "MATCH (ep:Episode)-[:HAS]->(e:Entry {type: 'assessment'}) "
        "RETURN ep.id, e ORDER BY e.recorded_at DESC, e.id LIMIT $limit",
        {"limit": limit},
    ).result_set
    return {
        "waiting_count": len(waiting),
        "waiting": waiting[::-1][:limit],
        "assessed": [
            {"episode": episode_id, **without_words(entry.properties)} for episode_id, entry in rows
        ],
    }


class Question(BaseModel):
    session: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    text: str = Field(min_length=1, max_length=4_000)
    model: str | None = Field(default=None, max_length=300)


@router.get("/models")
def available_models(who: User) -> list[dict]:
    """Model choices enabled for this workspace, without credentials or diagnostics."""
    return model.catalog()


@router.post("/ask")
def ask(question: Question, graph: Desk, who: User) -> dict:
    """Ask the Desk. The answer comes from the model, with the tools it picked."""
    tenant, user = who
    if question.model and question.model not in {choice["id"] for choice in model.catalog()}:
        raise HTTPException(status_code=400, detail="That model is unavailable. Please choose another.")
    try:
        options = {"model_selection": question.model} if question.model else {}
        return desk.answer(graph, _memory(tenant), user, question.session, question.text, **options)
    except RuntimeError as exc:  # the model service failed or cannot be reached
        log.warning("the desk could not answer: %s", exc)
        raise HTTPException(status_code=502, detail="The assistant is temporarily unavailable. Please try again shortly.") from None


@router.get("/sessions")
def my_sessions(who: User, limit: Annotated[int, Query(ge=1, le=MOST)] = 20) -> list[dict]:
    """The sessions of the signed-in user, the one written to last first."""
    tenant, user = who
    return sessions(_memory(tenant), user, limit)


@router.get("/sessions/{session_id}")
def my_session(session_id: str, who: User) -> list[dict]:
    """The messages of one session of the signed-in user, oldest first."""
    tenant, user = who
    found = messages(_memory(tenant), user, session_id, MOST)
    if not found:
        raise HTTPException(status_code=404, detail="no such session")
    return found
