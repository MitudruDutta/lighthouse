"""Standalone Memory service. No routes or data from the operations application."""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import google_auth, memory_agents, memory_mcp, memory_workspaces
from app.db import get_db
from app.memory_api import router
from app.memory_control import database


class BodyLimit:
    """Bound request bodies before JSON parsing, including chunked requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > 65536:
                response = JSONResponse(
                    status_code=413,
                    content={"detail": "Request is too large."},
                    headers={"Cache-Control": "no-store"},
                )
                return await response(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if chunks:
                return chunks.pop(0)
            return await receive()

        await self.app(scope, replay, send)


app = FastAPI(title="Lighthouse Memory API", version="0.1.0", lifespan=memory_mcp.lifespan)
app.include_router(router)
app.include_router(memory_agents.router)
app.include_router(memory_workspaces.router)
# Agent clients over MCP, with a project key: the same operations as /v1.
app.add_route("/mcp", memory_mcp.Endpoint(), methods=["GET", "POST", "DELETE"])
app.include_router(google_auth.router)
app.add_middleware(BodyLimit)
log = logging.getLogger("lighthouse.memory")


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValueError)
@app.exception_handler(TypeError)
def invalid(request: Request, exc: Exception):
    log.warning("Memory request rejected: %s", type(exc).__name__)
    return JSONResponse(
        status_code=422, content={"detail": "Please check the information you entered."}
    )


@app.exception_handler(Exception)
def unavailable(request: Request, exc: Exception):
    log.error("Memory request failed", exc_info=exc)
    return JSONResponse(
        status_code=503,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        content={"detail": "This service is temporarily unavailable. Please try again shortly."},
    )


@app.get("/readyz")
def ready():
    try:
        get_db().list_graphs()
        with database() as db:
            db.execute("SELECT 1")
    except Exception:
        log.exception("Memory readiness failed")
        raise HTTPException(503, "Service temporarily unavailable.") from None
    return {"status": "ready"}
