"""Memory product API: account sessions and scoped project keys are distinct credentials."""

import hmac
import json
import logging
import os
import re
import sqlite3
import time
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import lighthouse as memory
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from lighthouse.values import without_words
from pydantic import BaseModel, Field

from app.db import get_db
from app.memory_control import (
    DUMMY_PASSWORD,
    USER_COLUMNS,
    check_password,
    database,
    digest,
    identifier,
    issue_key,
    new_session,
    password_hash,
    public_user,
)

router = APIRouter()
log = logging.getLogger("lighthouse.memory")
FACT = memory.Kind(
    "Memory", key="key", text=("title", "text"), relations={"LINKED_TO": memory.SELF}
)
NAME = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,99}$"


def reject(status=401, message="Please sign in to continue."):
    raise HTTPException(status_code=status, detail=message)


def bearer(authorization: str | None) -> str:
    return (authorization or "").removeprefix("Bearer ").strip()


def signed_in(authorization: Annotated[str | None, Header()] = None) -> dict:
    token = bearer(authorization)
    if not token.startswith("lhs_"):
        reject()
    with database() as db:
        user = db.execute(
            f"SELECT {USER_COLUMNS} FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.hash=? AND s.expires>?",
            (digest(token), int(time.time())),
        ).fetchone()
    if not user:
        reject()
    return public_user(user)


User = Annotated[dict, Depends(signed_in)]


def owned_project(user: dict, project_id: str) -> dict:
    with database() as db:
        project = db.execute(
            "SELECT p.* FROM projects p JOIN workspaces w ON w.id=p.workspace_id WHERE p.id=? AND w.owner=?",
            (project_id, user["id"]),
        ).fetchone()
    if not project:
        reject(404, "Project not found.")
    return dict(project)


def graph_for(project_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", project_id):
        reject(404, "Project not found.")
    graph = get_db().select_graph("memory_" + project_id)
    memory.ensure_schema(graph, [FACT])
    return graph


LOGIN_FAILURES, LOGIN_WINDOW = 10, 900


def client_address(request: Request) -> str:
    # Browsers sign in through the Next.js servers, so every such request comes from them.
    # They pass on the browser's address, believed only with the token they share with us.
    secret = os.environ.get("LIGHTHOUSE_PROXY_TOKEN", "")
    forwarded = request.headers.get("x-lighthouse-client", "")
    proof = request.headers.get("x-lighthouse-proxy", "")
    if secret and forwarded and hmac.compare_digest(proof.encode(), secret.encode()):
        return forwarded[:100]
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request):
    ip = digest(client_address(request))
    now = int(time.time())
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM attempts WHERE at<?", (now - 600,))
        if db.execute("SELECT count(*) FROM attempts WHERE ip=?", (ip,)).fetchone()[0] >= 30:
            reject(429, "Too many attempts. Please try again in a few minutes.")
        db.execute("INSERT INTO attempts VALUES (?,?)", (ip, now))


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default="", max_length=80)


def email_address(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        reject(422, "Enter a valid email address.")
    return value


@router.post("/auth/register", dependencies=[Depends(rate_limit)])
def register(form: Credentials) -> dict:
    email = email_address(form.email)
    if not form.name.strip():
        reject(422, "Enter your name.")
    user_id, workspace_id, now = identifier(), identifier(), int(time.time())
    try:
        with database() as db:
            db.execute(
                "INSERT INTO users(id,email,name,password,created) VALUES (?,?,?,?,?)",
                (user_id, email, form.name.strip(), password_hash(form.password), now),
            )
            db.execute(
                "INSERT INTO workspaces VALUES (?,?,?,?)",
                (workspace_id, user_id, form.name.strip() + "'s workspace", now),
            )
            token = new_session(db, user_id)
            user = public_user(db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
    except sqlite3.IntegrityError:
        reject(409, "An account could not be created with that email. Try signing in.")
    return {"token": token, "user": user}


@router.post("/auth/login", dependencies=[Depends(rate_limit)])
def login(form: Credentials) -> dict:
    email = email_address(form.email)
    # Counted per email whether or not the account exists, so the limit reveals nothing,
    # and whatever address the attempts come from.
    account, now = digest(email), int(time.time())
    with database() as db:
        failures = db.execute(
            "SELECT count(*) FROM login_failures WHERE account=? AND at>?",
            (account, now - LOGIN_WINDOW),
        ).fetchone()[0]
    if failures >= LOGIN_FAILURES:
        reject(429, "Too many attempts. Please try again in a few minutes.")
    with database() as db:
        user = db.execute(
            f"SELECT {USER_COLUMNS} FROM users u WHERE u.email=?", (email,)
        ).fetchone()
        # Equal work for unknown accounts limits timing-based account discovery.
        stored = user["password"] if user else DUMMY_PASSWORD
        valid = check_password(form.password, stored)
        if user and valid:
            db.execute("DELETE FROM login_failures WHERE account=?", (account,))
            token = new_session(db, user["id"])
            return {"token": token, "user": public_user(user)}
        # Recorded before the refusal: a refusal inside this block would roll it back.
        db.execute("DELETE FROM login_failures WHERE at<=?", (now - LOGIN_WINDOW,))
        db.execute("INSERT INTO login_failures VALUES (?,?)", (account, now))
    reject(401, "Email or password is incorrect.")


@router.post("/auth/logout")
def logout(user: User, authorization: Annotated[str | None, Header()] = None):
    with database() as db:
        db.execute("DELETE FROM sessions WHERE hash=?", (digest(bearer(authorization)),))
    return {"signed_out": True}


@router.get("/console/overview")
def overview(user: User):
    with database() as db:
        workspaces = [
            dict(row)
            for row in db.execute(
                "SELECT id,name,created FROM workspaces WHERE owner=? ORDER BY created",
                (user["id"],),
            )
        ]
        projects = [
            dict(row)
            for row in db.execute(
                "SELECT p.* FROM projects p JOIN workspaces w ON w.id=p.workspace_id WHERE w.owner=? ORDER BY p.created DESC,p.id LIMIT 100",
                (user["id"],),
            )
        ]
    return {
        "user": user,
        "workspaces": workspaces,
        "projects": projects,
        "plan": {"name": "Workspace", "billing_active": False},
    }


class Project(BaseModel):
    workspace_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)


@router.post("/console/projects")
def create_project(form: Project, user: User):
    if not form.name.strip():
        reject(422, "Enter a project name.")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute(
            "SELECT id FROM workspaces WHERE id=? AND owner=?", (form.workspace_id, user["id"])
        ).fetchone():
            reject(404, "Workspace not found.")
        if (
            db.execute(
                "SELECT count(*) FROM projects WHERE workspace_id=?", (form.workspace_id,)
            ).fetchone()[0]
            >= 20
        ):
            reject(409, "A workspace can contain up to 20 projects.")
        project_id, now = identifier(), int(time.time())
        graph_for(project_id)
        db.execute(
            "INSERT INTO projects VALUES (?,?,?,?,?)",
            (project_id, form.workspace_id, form.name.strip(), form.description.strip(), now),
        )
    return {"id": project_id, **form.model_dump(), "created": now}


class Profile(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    timezone: str = Field(max_length=80)


@router.patch("/console/profile")
def update_profile(form: Profile, user: User):
    if not form.name.strip():
        reject(422, "Enter your name.")
    try:
        ZoneInfo(form.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        reject(422, "Choose a valid time zone.")
    with database() as db:
        db.execute(
            "UPDATE users SET name=?,timezone=? WHERE id=?",
            (form.name.strip(), form.timezone, user["id"]),
        )
    return user | form.model_dump()


class Key(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[Literal["memory:read", "memory:write"]] = Field(min_length=1, max_length=2)
    days: int = Field(default=90, ge=1, le=365)


@router.get("/console/projects/{project_id}/keys")
def keys(project_id: str, user: User):
    owned_project(user, project_id)
    with database() as db:
        rows = db.execute(
            "SELECT id,name,prefix,scopes,created,expires,revoked,last_used FROM api_keys WHERE project_id=? ORDER BY created DESC,id LIMIT 100",
            (project_id,),
        ).fetchall()
    return [dict(row) | {"scopes": json.loads(row["scopes"])} for row in rows]


@router.post("/console/projects/{project_id}/keys")
def create_key(project_id: str, form: Key, user: User):
    owned_project(user, project_id)
    if not form.name.strip():
        reject(422, "Enter a key name.")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        if (
            db.execute(
                "SELECT count(*) FROM api_keys WHERE project_id=? AND revoked IS NULL AND expires>?",
                (project_id, int(time.time())),
            ).fetchone()[0]
            >= 20
        ):
            reject(409, "Revoke an unused key before creating another.")
        return issue_key(db, project_id, form.name.strip(), sorted(set(form.scopes)), form.days)


@router.delete("/console/projects/{project_id}/keys/{key_id}")
def revoke_key(project_id: str, key_id: str, user: User):
    owned_project(user, project_id)
    with database() as db:
        result = db.execute(
            "UPDATE api_keys SET revoked=? WHERE id=? AND project_id=? AND revoked IS NULL",
            (int(time.time()), key_id, project_id),
        )
    if not result.rowcount:
        reject(404, "Active key not found.")
    return {"revoked": True}


class Fact(BaseModel):
    key: str = Field(pattern=NAME)
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(max_length=12000)
    metadata: dict = Field(default_factory=dict)
    links: list[str] = Field(default_factory=list, max_length=50)


def write_fact(project: str, form: Fact, by: str):
    metadata = json.dumps(form.metadata, ensure_ascii=False)
    if len(metadata) > 12000 or any(not re.fullmatch(NAME, key) for key in form.links):
        reject(422, "Check metadata size and linked memory identifiers.")
    graph = graph_for(project)
    for key in form.links:
        if memory.as_of(graph, FACT, key, memory.now()) is None:
            reject(422, "A linked memory does not exist in this project.")
    receipt = memory.remember(
        graph,
        FACT,
        by=by,
        rows=[
            {
                "key": form.key,
                "t": memory.now(),
                "values": {"title": form.title, "text": form.text, "metadata": metadata},
                "relations": {"LINKED_TO": form.links},
            }
        ],
    )[0]
    if receipt["status"] not in {"created", "changed", "unchanged", "inserted"}:
        log.warning("Memory write refused in project %s: %s", project, receipt)
        reject(422, "Memory could not be saved. Check the values and try again.")
    return receipt


def list_facts(project: str, q: str = ""):
    graph = graph_for(project)
    if q:
        found = memory.search(graph, FACT, q, limit=100, match="any")
        identifiers = [item["key"] for item in found]
        rows = graph.ro_query(
            "MATCH (m:Memory) WHERE m.key IN $keys RETURN m ORDER BY m.title LIMIT 100",
            {"keys": identifiers},
        ).result_set
    else:
        rows = graph.ro_query(
            "MATCH (m:Memory) RETURN m ORDER BY m.title,m.key LIMIT 100"
        ).result_set
    # The search words of a memory are the index's, not the reader's.
    return [
        without_words(row[0].properties)
        | {"metadata": json.loads(row[0].properties.get("metadata", "{}"))}
        for row in rows
    ]


def usage_event(project: str, operation: str, key: str | None = None, status=200):
    with database() as db:
        db.execute(
            "INSERT INTO usage(project_id,key_id,operation,status,at) VALUES (?,?,?,?,?)",
            (project, key, operation, status, int(time.time())),
        )


@router.get("/console/projects/{project_id}/summary")
def project_summary(project_id: str, user: User):
    owned_project(user, project_id)
    graph = graph_for(project_id)
    counts = {
        label: graph.ro_query(f"MATCH (n:{label}) RETURN count(n)").result_set[0][0]
        for label in ("Memory", "State", "Episode", "Lesson", "Playbook", "Session", "Task")
    }
    rows = graph.ro_query(
        "MATCH (m:Memory)-[r:LINKED_TO]->(n:Memory) WHERE r.valid_to IS NULL RETURN m.key,n.key LIMIT 200"
    ).result_set
    with database() as db:
        total = db.execute(
            "SELECT operation,count(*) AS count FROM usage WHERE project_id=? GROUP BY operation",
            (project_id,),
        ).fetchall()
        days = db.execute(
            "SELECT date(at,'unixepoch') AS day,count(*) AS count FROM usage WHERE project_id=? AND at>? GROUP BY day ORDER BY day",
            (project_id, int(time.time()) - 14 * 86400),
        ).fetchall()
        recent = db.execute(
            "SELECT operation,status,at FROM usage WHERE project_id=? ORDER BY id DESC LIMIT 12",
            (project_id,),
        ).fetchall()
    return {
        "counts": counts,
        "edges": [{"from": a, "to": b} for a, b in rows],
        "usage": [dict(row) for row in total],
        "days": [dict(row) for row in days],
        "recent": [dict(row) for row in recent],
    }


@router.get("/console/projects/{project_id}/memories")
def console_memories(project_id: str, user: User, q: str = Query(default="", max_length=200)):
    owned_project(user, project_id)
    return list_facts(project_id, q)


@router.post("/console/projects/{project_id}/memories")
def console_write(project_id: str, form: Fact, user: User):
    owned_project(user, project_id)
    result = write_fact(project_id, form, "console:" + user["id"])
    usage_event(project_id, "console.write")
    return result


@router.get("/console/projects/{project_id}/memories/{key:path}/history")
def console_history(project_id: str, key: str, user: User):
    owned_project(user, project_id)
    return memory.history(graph_for(project_id), FACT, key)


def check_key(token: str, scope: str | None, count: bool = True) -> dict:
    """The active project key behind `token`. `scope` is the access the operation needs;
    `count` spends one of the key's requests this minute."""
    if not token.startswith("lhm_"):
        reject(401, "A valid project API key is required.")
    now = int(time.time())
    with database() as db:
        key = db.execute(
            "SELECT * FROM api_keys WHERE hash=? AND revoked IS NULL AND expires>?",
            (digest(token), now),
        ).fetchone()
        if not key:
            reject(401, "A valid project API key is required.")
        if scope and scope not in json.loads(key["scopes"]):
            reject(403, "This API key does not allow this operation.")
        if count:
            spent = db.execute(
                "INSERT INTO key_limits VALUES (?,?,1) ON CONFLICT(key_id) DO UPDATE SET window=excluded.window,count=CASE WHEN key_limits.window=excluded.window THEN key_limits.count+1 ELSE 1 END RETURNING count",
                (key["id"], now // 60),
            ).fetchone()[0]
            if spent > 120:
                reject(429, "Request limit reached. Retry shortly.")
            db.execute("UPDATE api_keys SET last_used=? WHERE id=?", (now, key["id"]))
    return dict(key)


def project_key(scope: str):
    def authorize(authorization: Annotated[str | None, Header()] = None):
        return check_key(bearer(authorization), scope)

    return authorize


ReadKey = Annotated[dict, Depends(project_key("memory:read"))]
WriteKey = Annotated[dict, Depends(project_key("memory:write"))]


@router.get("/v1/memories")
def api_memories(key: ReadKey, q: str = Query(default="", max_length=200)):
    result = list_facts(key["project_id"], q)
    usage_event(key["project_id"], "api.read", key["id"])
    return {"data": result, "limit": 100}


@router.post("/v1/memories")
def api_write(form: Fact, key: WriteKey):
    result = write_fact(key["project_id"], form, "key:" + key["id"])
    usage_event(key["project_id"], "api.write", key["id"])
    return result


@router.get("/v1/memories/{memory_key:path}/history")
def api_history(memory_key: str, key: ReadKey):
    result = memory.history(graph_for(key["project_id"]), FACT, memory_key)
    usage_event(key["project_id"], "api.history", key["id"])
    return {"data": result}


@router.get("/v1/connections")
def api_connection(
    key: ReadKey, start: str = Query(max_length=100), end: str = Query(max_length=100)
):
    result = memory.connection(
        graph_for(key["project_id"]),
        (FACT, start),
        (FACT, end),
        kinds=[FACT],
        relations=["LINKED_TO"],
        max_hops=6,
    )
    usage_event(key["project_id"], "api.connection", key["id"])
    return {"data": result}
