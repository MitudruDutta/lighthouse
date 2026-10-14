from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_never_crashes():
    # 200 with the Compose FalkorDB service up, 503 without it.
    assert client.get("/readyz").status_code in (200, 503)
