"""Real memory graphs; isolated control database. No production account data."""

import json
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from app import memory_api as api
from app.memory_control import database, digest
from app.memory_main import app


@pytest.fixture
def client(tmp_path, monkeypatch, db):
    monkeypatch.setenv("LIGHTHOUSE_MEMORY_CONTROL_DB", str(tmp_path / "accounts.sqlite3"))
    yield TestClient(app, raise_server_exceptions=False)
    with database() as control:
        ids = [row[0] for row in control.execute("SELECT id FROM projects")]
    for project in ids:
        db.select_graph("memory_" + project).delete()


def account(client, name="Owner"):
    response = client.post(
        "/auth/register",
        json={
            "name": name,
            "email": uuid.uuid4().hex + "@example.test",
            "password": "test-password-123!",
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    headers = {"Authorization": "Bearer " + token}
    data = client.get("/console/overview", headers=headers).json()
    return headers, data


def project(client, headers, data):
    response = client.post(
        "/console/projects",
        headers=headers,
        json={"workspace_id": data["workspaces"][0]["id"], "name": "Research memory"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def key(client, headers, project, scopes=("memory:read", "memory:write")):
    response = client.post(
        f"/console/projects/{project}/keys",
        headers=headers,
        json={"name": "Test agent", "scopes": list(scopes), "days": 30},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return {"Authorization": "Bearer " + data["secret"]}, data


def test_register_login_preferences_logout_and_secret_storage(client):
    headers, data = account(client)
    with database() as control:
        row = control.execute("SELECT * FROM users").fetchone()
        assert row["password"] != "test-password-123!"
        assert headers["Authorization"][7:] not in json.dumps(
            [dict(r) for r in control.execute("SELECT * FROM sessions")]
        )
    login = client.post(
        "/auth/login",
        json={"email": data["user"]["email"].upper(), "password": "test-password-123!"},
    )
    assert login.status_code == 200
    assert (
        client.post(
            "/auth/login", json={"email": data["user"]["email"], "password": "wrong-password-123"}
        ).status_code
        == 401
    )
    response = client.patch(
        "/console/profile", headers=headers, json={"name": "New name", "timezone": "Asia/Kolkata"}
    )
    assert response.status_code == 200
    assert (
        client.get("/console/overview", headers=headers).json()["user"]["timezone"]
        == "Asia/Kolkata"
    )
    assert (
        client.patch(
            "/console/profile", headers=headers, json={"name": "New", "timezone": "Invalid/Nowhere"}
        ).status_code
        == 422
    )
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/console/overview", headers=headers).status_code == 401


def test_projects_keys_and_graphs_are_isolated_between_accounts(client):
    owner, data = account(client)
    other, otherdata = account(client, "Other")
    first = project(client, owner, data)
    second = project(client, other, otherdata)
    ownerkey, secret = key(client, owner, first)
    otherkey, _ = key(client, other, second)
    assert client.get(f"/console/projects/{first}/keys", headers=other).status_code == 404
    assert (
        client.post(
            f"/console/projects/{first}/keys",
            headers=other,
            json={"name": "bad", "scopes": ["memory:read"]},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/console/projects",
            headers=other,
            json={"workspace_id": data["workspaces"][0]["id"], "name": "bad"},
        ).status_code
        == 404
    )
    response = client.post(
        "/v1/memories",
        headers=ownerkey,
        json={"key": "pref-1", "title": "Preference", "text": "Private information"},
    )
    assert response.status_code == 200, response.text
    assert client.get("/v1/memories", headers=otherkey).json()["data"] == []
    assert "Private information" in client.get("/v1/memories", headers=ownerkey).text
    assert client.get("/v1/memories", headers=owner).status_code == 401
    assert client.get("/console/overview", headers=ownerkey).status_code == 401
    listing = client.get(f"/console/projects/{first}/keys", headers=owner)
    assert secret["secret"] not in listing.text
    with database() as control:
        stored = control.execute(
            "SELECT hash FROM api_keys WHERE id=?", (secret["id"],)
        ).fetchone()[0]
        assert stored == digest(secret["secret"])
    assert (
        client.delete(f"/console/projects/{first}/keys/{secret['id']}", headers=owner).status_code
        == 200
    )
    assert client.get("/v1/memories", headers=ownerkey).status_code == 401


def test_key_scopes_expiry_and_validation(client):
    owner, data = account(client)
    pid = project(client, owner, data)
    readonly, secret = key(client, owner, pid, ("memory:read",))
    assert (
        client.post(
            "/v1/memories", headers=readonly, json={"key": "x", "title": "X", "text": "X"}
        ).status_code
        == 403
    )
    with database() as control:
        control.execute(
            "UPDATE api_keys SET expires=? WHERE id=?", (int(time.time()) - 1, secret["id"])
        )
    assert client.get("/v1/memories", headers=readonly).status_code == 401
    invalid = client.post(
        f"/console/projects/{pid}/keys", headers=owner, json={"name": "bad", "scopes": ["admin"]}
    )
    assert invalid.status_code == 422 and "admin" not in invalid.text
    assert client.get("/v1/memories").status_code == 401


def test_memory_versions_links_graph_algorithms_search_and_usage(client):
    owner, data = account(client)
    pid = project(client, owner, data)
    agent, _ = key(client, owner, pid)
    for name, links in [("alpha", []), ("beta", ["alpha"])]:
        response = client.post(
            "/v1/memories",
            headers=agent,
            json={
                "key": name,
                "title": name.title(),
                "text": "connected research note",
                "links": links,
                "metadata": {"source": "test"},
            },
        )
        assert response.status_code == 200, response.text
    # Stored time is in whole seconds; force a later valid observation for a new version.
    original = api.memory.now
    from datetime import datetime, timedelta

    later = (datetime.fromisoformat(original()) + timedelta(seconds=1)).isoformat()
    from unittest.mock import patch

    with patch.object(api.memory, "now", return_value=later):
        assert (
            client.post(
                "/v1/memories",
                headers=agent,
                json={"key": "alpha", "title": "Alpha updated", "text": "revised research note"},
            ).status_code
            == 200
        )
    history = client.get("/v1/memories/alpha/history", headers=agent).json()["data"]
    assert len(history) == 2
    assert len(client.get("/v1/memories?q=research", headers=agent).json()["data"]) == 2
    chain = client.get("/v1/connections?start=beta&end=alpha", headers=agent)
    assert chain.status_code == 200 and len(chain.json()["data"]) == 1, chain.text
    summary = client.get(f"/console/projects/{pid}/summary", headers=owner).json()
    assert summary["counts"]["Memory"] == 2 and summary["counts"]["State"] == 3
    assert summary["edges"] == [{"from": "beta", "to": "alpha"}]
    assert {r["operation"]: r["count"] for r in summary["usage"]}["api.write"] == 3
    assert (
        client.post(
            "/v1/memories",
            headers=agent,
            json={"key": "bad", "title": "Bad", "text": "bad", "links": ["missing"]},
        ).status_code
        == 422
    )

    # Hierarchical identifiers accepted by writes must remain addressable in history.
    assert (
        client.post(
            "/v1/memories",
            headers=agent,
            json={"key": "user/preference", "title": "Preference", "text": "Python"},
        ).status_code
        == 200
    )
    assert (
        len(client.get("/v1/memories/user%2Fpreference/history", headers=agent).json()["data"]) == 1
    )
    assert (
        len(
            client.get(
                f"/console/projects/{pid}/memories/user%2Fpreference/history", headers=owner
            ).json()
        )
        == 1
    )


def test_infrastructure_errors_never_reach_customer(client, monkeypatch):
    owner, data = account(client)

    def broken(*args):
        raise RuntimeError("PRIVATE infrastructure secret")

    monkeypatch.setattr(api, "graph_for", broken)
    response = client.post(
        "/console/projects",
        headers=owner,
        json={"workspace_id": data["workspaces"][0]["id"], "name": "Broken"},
    )
    assert response.status_code == 503 and "PRIVATE" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_api_key_request_limits_and_body_bound(client):
    owner, data = account(client)
    pid = project(client, owner, data)
    headers, secret = key(client, owner, pid)
    with database() as control:
        control.execute(
            "INSERT INTO key_limits VALUES (?,?,?)", (secret["id"], int(time.time()) // 60, 120)
        )
    assert client.get("/v1/memories", headers=headers).status_code == 429
    with database() as control:
        control.execute("UPDATE key_limits SET window=window-1")
    assert client.get("/v1/memories", headers=headers).status_code == 200
    assert client.post("/v1/memories", headers=headers, content=b"x" * 70000).status_code == 413
    assert client.get("/console/overview", headers=owner).status_code == 200
