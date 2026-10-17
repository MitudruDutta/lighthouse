"""The Memory API over MCP: project keys, scopes, the agent's name, and safe errors."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import memory_api as api
from app.memory_main import app
from tests.test_memory_product import account, client, key, project  # noqa: F401

ACCEPT = {"Accept": "application/json, text/event-stream"}


@pytest.fixture
def mcp(client):  # noqa: F811
    # The MCP server runs inside the application's lifespan.
    with TestClient(app, raise_server_exceptions=False) as running:
        yield running


def rpc(mcp, headers, method, params=None, number=1):
    body = {"jsonrpc": "2.0", "id": number, "method": method, "params": params or {}}
    return mcp.post("/mcp", headers=headers | ACCEPT, json=body)


def call(mcp, headers, tool, **arguments):
    response = rpc(mcp, headers, "tools/call", {"name": tool, "arguments": arguments})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    text = result["content"][0]["text"] if result["content"] else "null"
    return result.get("isError", False), text


def test_agents_use_memory_through_mcp_with_their_project_key(mcp):
    owner, data = account(mcp)
    pid = project(mcp, owner, data)
    writer, _ = key(mcp, owner, pid, name="planner")
    reader, _ = key(mcp, owner, pid, scopes=("memory:read",), name="reader")

    assert mcp.post("/mcp", headers=ACCEPT, json={}).status_code == 401
    wrong = {"Authorization": "Bearer lhm_not-a-key"}
    assert rpc(mcp, wrong, "tools/list").status_code == 401

    started = rpc(
        mcp,
        writer,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )
    assert started.json()["result"]["serverInfo"]["name"] == "Lighthouse Memory"
    tools = {tool["name"] for tool in rpc(mcp, reader, "tools/list").json()["result"]["tools"]}
    assert {"remember", "recall", "history", "open_episode", "claim_task", "hand_off"} <= tools

    failed, text = call(mcp, writer, "remember", key="goal", title="Goal", text="Ship on Friday")
    assert not failed and json.loads(text)["status"] == "created"
    # Stored time is in whole seconds: the next version is a second later.
    later = (datetime.fromisoformat(api.memory.now()) + timedelta(seconds=1)).isoformat()
    with patch.object(api.memory, "now", return_value=later):
        call(mcp, writer, "remember", key="goal", title="Goal", text="Ship on Monday")
    failed, text = call(mcp, reader, "remember", key="x", title="X", text="no")
    assert failed and "does not allow" in text

    failed, text = call(mcp, reader, "history", key="goal")
    versions = json.loads(text)["data"]
    assert [version["text"] for version in versions] == ["Ship on Friday", "Ship on Monday"]
    failed, text = call(mcp, reader, "recall", query="Monday")
    (found,) = json.loads(text)["data"]
    assert found["key"] == "goal" and "words" not in found  # the index's words stay inside

    call(mcp, writer, "open_episode", id="launch", about=["goal"])
    failed, text = call(
        mcp,
        writer,
        "record",
        episode_id="launch",
        type="decision",
        values={"choice": "delay"},
        cites={"memories": ["goal"]},
    )
    assert not failed, text
    failed, text = call(mcp, reader, "episode", episode_id="launch")
    (entry,) = json.loads(text)["data"]["entries"]
    assert entry["by"] == "planner"  # the key names the agent

    call(mcp, writer, "add_task", id="t1", kind="review")
    failed, text = call(mcp, writer, "claim_task", kind="review")
    assert json.loads(text)["data"]["id"] == "t1"

    failed, text = call(mcp, writer, "episode", episode_id="bad id")
    assert failed and "identifier" in text
    failed, text = call(mcp, writer, "remember", key="", title="", text="")
    assert failed and text.endswith("Please check the values you sent: key, title.")

    usage = mcp.get(f"/console/projects/{pid}/summary", headers=owner).json()["usage"]
    assert {item["operation"] for item in usage} >= {"api.write", "api.history", "api.episode"}


def test_mcp_hides_infrastructure_errors(mcp, monkeypatch):
    owner, data = account(mcp)
    pid = project(mcp, owner, data)
    writer, _ = key(mcp, owner, pid)

    def broken(*args, **kwargs):
        raise ConnectionError("redis://internal-host:6379 refused")

    monkeypatch.setattr("app.memory_api.list_facts", broken)
    failed, text = call(mcp, writer, "recall")
    assert failed and "temporarily unavailable" in text and "internal-host" not in text
