"""Customer responses must never contain backend diagnostics or provider failures."""

import json
from types import SimpleNamespace

import anyio
import pytest
from fastapi.testclient import TestClient

from app import api, desk_api
from app.api import get_graph
from app.main import app

SECRET = "provider traceback /private/config.py SECRET-KEY"
OPERATOR = "private-operator-" + "x" * 32
CUSTOMER = "customer-" + "y" * 32


@pytest.fixture
def client(graph, monkeypatch):
    app.dependency_overrides[get_graph] = lambda: graph
    monkeypatch.setenv("LIGHTHOUSE_OPERATOR_TOKEN", OPERATOR)
    monkeypatch.setenv("LIGHTHOUSE_DESK_USERS", f"{CUSTOMER}=tenant/user")
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_customer_status_uses_allowlists_even_when_diagnostics_contain_secrets(client, monkeypatch):
    summaries = {
        "feed": {
            "at": "2026-10-15T12:00:00",
            "port_calls": {"created": 2, SECRET: 3},
            "error": SECRET,
        },
        "feed-error": {"at": "2026-10-15T12:01:00", "error": SECRET},
        "portwatch": {
            "at": "2026-10-15T12:00:00",
            "rows": {"unchanged": 2, "conflict": 1},
            "state": "partial",
            "skipped": 7,
        },
        "desk": {
            "at": "2026-10-15T12:00:00",
            "failed": SECRET,
            "model": SECRET,
            "did": {"failed": 1},
            "waiting": 4,
        },
    }
    monkeypatch.setattr(api, "last_poll", lambda graph, source="feed": summaries.get(source))
    monkeypatch.setattr(
        api, "readiness", lambda: {"ready": True, "problem": SECRET, "service": SECRET}
    )
    found = client.get("/api/status").json()
    assert SECRET not in json.dumps(found)
    assert found["availability"] == {"feed": False, "portwatch": True, "desk": False}
    assert found["last_desk"] == {"at": "2026-10-15T12:00:00", "did": {}, "waiting": 4}
    assert found["last_poll"]["port_calls"] == {"created": 2}
    assert found["last_world_poll"]["rows"] == {"unchanged": 2}
    assert found["last_world_poll"]["state"] == "updating"
    assert "refused_writes" not in client.get("/api/quality").json()


def test_private_diagnostics_require_distinct_operator_credentials(client, monkeypatch):
    assert client.get("/api/operator/diagnostics").status_code == 401
    assert (
        client.get(
            "/api/operator/diagnostics", headers={"Authorization": f"Bearer {CUSTOMER}"}
        ).status_code
        == 401
    )
    found = client.get("/api/operator/diagnostics", headers={"Authorization": f"Bearer {OPERATOR}"})
    assert found.status_code == 200 and found.headers["cache-control"] == "no-store"
    assert "model" in found.json() and "refused_writes" in found.json()["quality"]
    assert "/api/operator/diagnostics" not in client.get("/openapi.json").json()["paths"]
    monkeypatch.delenv("LIGHTHOUSE_OPERATOR_TOKEN")
    assert (
        client.get(
            "/api/operator/diagnostics", headers={"Authorization": f"Bearer {OPERATOR}"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("exception", [RuntimeError(SECRET), ValueError(SECRET), TypeError(SECRET)])
def test_exceptions_are_logged_but_never_echoed(client, monkeypatch, exception, caplog):
    def broken():
        raise exception

    app.dependency_overrides[get_graph] = broken
    found = client.get("/api/status")
    assert found.status_code in {422, 503}
    assert SECRET not in found.text and SECRET in caplog.text


def test_failed_assistant_returns_generic_message_and_logs_private_reason(
    client, monkeypatch, caplog
):
    def broken(*args):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(desk_api, "_memory", lambda tenant: None)
    monkeypatch.setattr(desk_api.desk, "answer", broken)
    found = client.post(
        "/api/desk/ask",
        json={"session": "s", "text": "Hi"},
        headers={"Authorization": f"Bearer {CUSTOMER}"},
    )
    assert found.status_code == 502 and SECRET not in found.text and SECRET in caplog.text
    invalid = client.post(
        "/api/desk/ask",
        json={"session": SECRET, "text": "Hi"},
        headers={"Authorization": f"Bearer {CUSTOMER}"},
    )
    assert invalid.status_code == 422 and SECRET not in invalid.text


def test_mcp_errors_never_reach_model_context(caplog):
    class Session:
        async def call_tool(self, name, arguments):
            return SimpleNamespace(isError=True, content=[SimpleNamespace(text=SECRET)])

    turns = iter(
        [
            {"tool_calls": [{"id": "x", "function": {"name": "look", "arguments": "{}"}}]},
            {"content": "Information is unavailable."},
        ]
    )
    conversation = []
    found = anyio.run(
        desk_api.desk.converse, Session(), conversation, lambda *args: next(turns), []
    )
    assert SECRET not in json.dumps(conversation) and SECRET not in json.dumps(found)
    assert SECRET in caplog.text and found["calls"][0]["ok"] is False
