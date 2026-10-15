import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.db import get_db

app = FastAPI(title="Lighthouse API")
app.include_router(router)
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
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    # GRAPH.LIST, not PING: a plain Redis answers PING but is not FalkorDB.
    try:
        get_db().list_graphs()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="FalkorDB unreachable") from exc
    return {"status": "ready"}
