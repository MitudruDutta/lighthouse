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


def key(client, headers, project, scopes=("memory:read", "memory:write"), name="Test agent"):
    response = client.post(
        f"/console/projects/{project}/keys",
        headers=headers,
        json={"name": name, "scopes": list(scopes), "days": 30},
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


def test_failed_logins_are_limited_per_account(client):
    email = uuid.uuid4().hex + "@example.test"
    right = {"email": email, "password": "test-password-123!"}
    wrong = {**right, "password": "wrong-password-123!"}
    assert client.post("/auth/register", json={**right, "name": "Owner"}).status_code == 200
    other, _ = account(client, "Other")
    for _ in range(api.LOGIN_FAILURES):
        assert client.post("/auth/login", json=wrong).status_code == 401
    assert client.post("/auth/login", json=wrong).status_code == 429
    # Locked even with the right password, and for this account only.
    assert client.post("/auth/login", json=right).status_code == 429
    assert client.get("/console/overview", headers=other).status_code == 200
    # An unknown email is limited the same way, so the limit reveals no account.
    unknown = {**wrong, "email": uuid.uuid4().hex + "@example.test"}
    statuses = [client.post("/auth/login", json=unknown).status_code for _ in range(11)]
    assert statuses == [401] * 10 + [429]
    with database() as control:
        control.execute("UPDATE login_failures SET at=at-?", (api.LOGIN_WINDOW,))
    assert client.post("/auth/login", json=right).status_code == 200
    with database() as control:
        assert control.execute(
            "SELECT count(*) FROM login_failures WHERE account=?", (digest(email),)
        ).fetchone()[0] == 0


def test_sign_in_limit_follows_the_browser_only_with_the_proxy_token(client, monkeypatch):
    monkeypatch.setenv("LIGHTHOUSE_PROXY_TOKEN", "proxy-secret")
    now = int(time.time())
    with database() as control:
        for address in ("203.0.113.9", "testclient"):
            control.executemany(
                "INSERT INTO attempts VALUES (?,?)", [(digest(address), now)] * 30
            )
    form = {"email": uuid.uuid4().hex + "@example.test", "password": "test-password-123!"}

    def login(address, token):
        headers = {"X-Lighthouse-Client": address, "X-Lighthouse-Proxy": token}
        return client.post("/auth/login", json=form, headers=headers).status_code

    # Browsers behind the website server no longer share its limit.
    assert login("203.0.113.9", "proxy-secret") == 429
    assert login("198.51.100.7", "proxy-secret") == 401
    # Without the token, a claimed address is ignored and the caller's own address counts.
    assert login("198.51.100.7", "wrong-secret") == 429
    assert login("198.51.100.7", "pröxy".encode()) == 429
    monkeypatch.delenv("LIGHTHOUSE_PROXY_TOKEN")
    assert login("198.51.100.7", "") == 429


def test_agents_coordinate_through_episodes_tasks_and_handoffs(client):
    owner, data = account(client)
    pid = project(client, owner, data)
    watcher, _ = key(client, owner, pid, name="watcher")
    desk, _ = key(client, owner, pid, name="desk")
    reader, _ = key(client, owner, pid, scopes=("memory:read",), name="reader")
    fact = {"key": "berth:vc2", "title": "Berth VC2", "text": "Holds four ships at most."}
    assert client.post("/v1/memories", headers=watcher, json=fact).status_code == 200

    start = {"id": "overload-1", "about": ["berth:vc2"]}
    assert client.post("/v1/episodes", headers=watcher, json=start).json()["status"] == "opened"
    assert client.post("/v1/episodes", headers=watcher, json=start).json()["status"] == "exists"
    missing = {"id": "overload-2", "about": ["berth:none"]}
    assert client.post("/v1/episodes", headers=watcher, json=missing).status_code == 422
    assert client.post("/v1/episodes", headers=reader, json=start).status_code == 403

    seen = {
        "type": "observation",
        "values": {"expected": 5},
        "cites": {"memories": ["berth:vc2"]},
        "by": "mallory",  # the writer comes from the key, never from the request
    }
    entries = "/v1/episodes/overload-1/entries"
    written = client.post(entries, headers=watcher, json=seen)
    assert written.json() == {"id": "overload-1/1", "seq": 1, "status": "recorded"}
    unknown = {**seen, "cites": {"entries": ["overload-1/9"]}}
    assert client.post(entries, headers=watcher, json=unknown).status_code == 422
    outcome = client.post(entries, headers=watcher, json={**seen, "type": "outcome"})
    assert outcome.status_code == 422 and "Close the episode" in outcome.json()["detail"]
    assert client.post("/v1/episodes/nope/entries", headers=watcher, json=seen).status_code == 404
    assert client.get("/v1/episodes/bad%20id", headers=reader).status_code == 422
    (entry,) = client.get("/v1/episodes/overload-1", headers=reader).json()["data"]["entries"]
    assert entry["by"] == "watcher" and entry["expected"] == 5
    assert entry["cites"] == [["Memory", "berth:vc2"]]

    task = {"id": "review-1", "kind": "review", "about": "berth:vc2"}
    assert client.post("/v1/tasks", headers=watcher, json=task).json()["status"] == "added"
    assert client.post("/v1/tasks", headers=watcher, json=task).json()["status"] == "exists"
    waiting = {"id": "review-2", "kind": "review", "after": ["review-0"]}
    assert client.post("/v1/tasks", headers=watcher, json=waiting).status_code == 422
    claimed = client.post("/v1/tasks/claim", headers=desk, json={"kind": "review", "lease": 60})
    assert claimed.json()["data"]["id"] == "review-1"
    assert client.post("/v1/tasks/claim", headers=watcher, json={"kind": "review"}).json() == {
        "data": None
    }
    assert client.post("/v1/tasks/review-1/complete", headers=watcher).status_code == 409
    done = client.post("/v1/tasks/review-1/complete", headers=desk)
    assert done.json() == {"id": "review-1", "status": "done"}

    given = {
        "id": "h1",
        "to": "desk",
        "points_to": {"entries": ["overload-1/1"]},
        "values": {"ask": "check the berth"},
    }
    assert client.post("/v1/handoffs", headers=watcher, json=given).json()["status"] == "given"
    empty = {**given, "id": "h2", "points_to": {}}
    assert client.post("/v1/handoffs", headers=watcher, json=empty).status_code == 422
    (handed,) = client.get("/v1/handoffs", headers=desk).json()["data"]
    assert handed["by"] == "watcher" and handed["ask"] == "check the berth"
    assert handed["points_to"] == [["Entry", "overload-1/1"]]
    assert client.get("/v1/handoffs", headers=watcher).json()["data"] == []
    assert client.post("/v1/handoffs/h1/accept", headers=watcher).status_code == 403
    assert client.post("/v1/handoffs/h1/accept", headers=desk).json()["status"] == "accepted"
    assert client.post("/v1/handoffs/h1/accept", headers=desk).json()["status"] == "exists"
    assert client.get("/v1/handoffs", headers=desk).json()["data"] == []
    assert len(client.get("/v1/handoffs?waiting=false", headers=desk).json()["data"]) == 1

    closing = {"outcome": {"held": True}, "cites": {"entries": ["overload-1/1"]}}
    closed = client.post("/v1/episodes/overload-1/close", headers=watcher, json=closing)
    assert closed.json()["status"] == "recorded"
    assert client.post(entries, headers=watcher, json=seen).status_code == 409
    (about,) = client.get("/v1/memories/berth:vc2/episodes", headers=reader).json()["data"]
    assert about["id"] == "overload-1" and about["outcome"]["held"] is True

    # Another account's agents cannot see this project's episodes, tasks, or handoffs.
    stranger, stranger_data = account(client, "Stranger")
    outsider, _ = key(client, stranger, project(client, stranger, stranger_data), name="desk")
    assert client.get("/v1/episodes/overload-1", headers=outsider).status_code == 404
    assert client.get("/v1/handoffs?waiting=false", headers=outsider).json()["data"] == []
