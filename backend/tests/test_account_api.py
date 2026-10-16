import pytest
from fastapi.testclient import TestClient

from app.api import get_graph
from app.main import app
from app.memory_main import app as memory_app
from app import desk_api, operations


@pytest.fixture
def clients(graph, monkeypatch, tmp_path, db):
    monkeypatch.setenv("LIGHTHOUSE_MEMORY_CONTROL_DB", str(tmp_path / "accounts.sqlite3"))
    app.dependency_overrides[get_graph] = lambda: graph
    ops = TestClient(app, raise_server_exceptions=False)
    memory = TestClient(memory_app, raise_server_exceptions=False)
    tenants = []
    yield ops, memory, tenants
    app.dependency_overrides.clear()
    for tenant in tenants:
        name = "tenant:account_" + tenant
        if name in db.list_graphs():
            db.select_graph(name).delete()
    operations.workspace.cache_clear()
    desk_api._memory.cache_clear()


def test_accounts_open_private_profiles_across_both_products(clients):
    ops, memory, tenants = clients
    credentials = {
        "email": "account@example.test",
        "password": "a-strong-test-password",
        "name": "Anika",
    }
    created = ops.post("/api/auth/register", json=credentials)
    assert created.status_code == 200, created.text
    token = created.json()["token"]
    headers = {"Authorization": "Bearer " + token}
    identity = ops.get("/api/auth/me", headers=headers).json()
    tenants.append(identity["workspace"])
    assert memory.get("/console/overview", headers=headers).json()["user"]["name"] == "Anika"
    assert ops.get("/api/operations/profile", headers=headers).json()["name"] == "Anika"
    changed = ops.put(
        "/api/operations/profile",
        headers=headers,
        json={
            "name": "Anika",
            "timezone": "Asia/Kolkata",
            "focus": "finland",
            "view": "watching",
            "ports": [],
            "vessels": [],
        },
    )
    assert changed.status_code == 200
    login = memory.post("/auth/login", json=credentials)
    other_headers = {"Authorization": "Bearer " + login.json()["token"]}
    assert ops.get("/api/operations/profile", headers=other_headers).json()["view"] == "watching"
    second = ops.post(
        "/api/auth/register", json={**credentials, "email": "other@example.test", "name": "Other"}
    ).json()
    h2 = {"Authorization": "Bearer " + second["token"]}
    tenants.append(ops.get("/api/auth/me", headers=h2).json()["workspace"])
    assert ops.get("/api/operations/profile", headers=h2).json()["view"] == "attention"
    assert ops.get("/api/auth/me").status_code == 401
    assert ops.post("/api/auth/logout", headers=headers).status_code == 200
    assert ops.get("/api/auth/me", headers=headers).status_code == 401
    assert ops.get("/api/auth/me", headers=other_headers).status_code == 200
