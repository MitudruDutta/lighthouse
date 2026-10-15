import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import desk_api, operator_api
from app.api import router
from app.db import get_db

app = FastAPI(title="Lighthouse API")
app.include_router(router)
app.include_router(desk_api.router)
app.include_router(operator_api.router)
log = logging.getLogger("lighthouse.api")
# The screen runs on another port in development. LIGHTHOUSE_ORIGINS lists the origins that
# may read the API, separated by commas.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("LIGHTHOUSE_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET"],
)


@app.exception_handler(ValueError)
@app.exception_handler(TypeError)
def refused(_request: Request, exc: Exception) -> JSONResponse:
    """A question the library cannot take, such as a key of the wrong form."""
    log.warning("Request rejected: %s", exc)
    return JSONResponse(status_code=422, content={"detail": "Please check the information you entered."})


@app.exception_handler(RequestValidationError)
def invalid(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    # Pydantic's default response echoes input values and internal schema context.
    return JSONResponse(status_code=422, content={"detail": "Please check the information you entered."})


@app.exception_handler(Exception)
def unavailable(_request: Request, exc: Exception) -> JSONResponse:
    log.error("Request failed", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "This service is temporarily unavailable. Please try again shortly."})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    # GRAPH.LIST, not PING: a plain Redis answers PING but is not FalkorDB.
    try:
        get_db().list_graphs()
    except Exception as exc:
        log.exception("Readiness check failed")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.") from exc
    return {"status": "ready"}
