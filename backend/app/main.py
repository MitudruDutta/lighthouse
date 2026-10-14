from fastapi import FastAPI, HTTPException

from app.db import get_db

app = FastAPI(title="Lighthouse API")


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
