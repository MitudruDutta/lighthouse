"""Private diagnostics, separate from customer tokens and never sent to the screen."""

import hmac
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.api import Desk
from app.intelligence import quality
from app.model import readiness
from app.poller import last_poll

router = APIRouter(prefix="/api/operator", include_in_schema=False)


def operator(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get("LIGHTHOUSE_OPERATOR_TOKEN", "")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if len(expected) < 32 or not hmac.compare_digest(expected.encode(), given.encode()):
        raise HTTPException(status_code=401, detail="Authentication required.")


@router.get("/diagnostics", dependencies=[Depends(operator)])
def diagnostics(graph: Desk, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {
        "model": readiness(),
        "imports": {source: last_poll(graph, source) for source in ("feed", "portwatch", "desk")},
        "import_errors": {source: last_poll(graph, f"{source}-error") for source in ("feed", "portwatch")},
        "quality": quality(graph, diagnostics=True),
    }
