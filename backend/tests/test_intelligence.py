import pytest
from fastapi.testclient import TestClient
from feed import poll, record, when

from app.api import get_graph
from app.intelligence import EDGES, NODES
from app.main import app
from app.watcher import watch


@pytest.fixture
def client(graph):
    app.dependency_overrides[get_graph] = lambda: graph
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def loaded(graph, client):
    poll(
        graph,
        0,
        record(id=1, imo=9000001, eta=600, etd=900),
        record(id=2, imo=9000002, eta=700, etd=1000),
    )
    watch(graph, when(5))
    return client


def test_network_is_directed_bounded_and_excludes_old_assignments(graph, loaded):
    first = loaded.get("/api/network", params={"kind": "PortCall", "key": "1"}).json()
    assert {tuple(n["ref"]) for n in first["nodes"]} >= {
        ("PortCall", 1),
        ("Vessel", 9000001),
        ("Port", "FIHEL"),
    }
    assert all(e["source"] in {n["id"] for n in first["nodes"]} for e in first["edges"])
    poll(graph, 1, record(id=1, minute=1, imo=9000001, berth="NEW", eta=600, etd=900))
    changed = loaded.get("/api/network", params={"kind": "PortCall", "key": "1"}).json()
    refs = {tuple(n["ref"]) for n in changed["nodes"]}
    assert ("Berth", "FIHEL/VUOS/NEW") in refs
    assert ("Berth", "FIHEL/VUOS/VC2") not in refs
    assert len(changed["nodes"]) <= NODES and len(changed["edges"]) <= EDGES


def test_default_network_follows_an_actual_episode_and_mcp_actions(loaded):
    found = loaded.get("/api/network").json()
    focus = next(n for n in found["nodes"] if n["id"] == found["focus"])
    assert focus["ref"][0] == "Episode"
    assert {e["type"] for e in found["edges"]} >= {"ABOUT", "HAS"}
    assert any(n["ref"][0] == "Entry" for n in found["nodes"])


def test_graph_inputs_cannot_change_a_query(loaded):
    assert loaded.get("/api/network", params={"kind": "Port) DELETE n"}).status_code == 422
    assert (
        loaded.get("/api/network", params={"kind": "Port", "key": "x'}) DELETE n //"}).json()[
            "nodes"
        ]
        == []
    )
    assert loaded.get("/api/network", params={"key": "x" * 301}).status_code == 422


def test_native_graph_algorithms_and_coordination_are_visible(loaded):
    found = loaded.get("/api/intelligence").json()
    assert found["tasks"]["open"] == 1
    assert found["handoffs"] == {"total": 1, "accepted": 0}
    assert found["assessments"] == {"total": 0, "grounded": 0}
    assert found["groups"] and any(p["entity"] == ["Port", "FIHEL"] for p in found["central"])


def test_quality_reports_missing_coverage_instead_of_zero_filling(loaded):
    found = loaded.get("/api/quality").json()
    assert found["ports"]["total"] > 0 and found["ports"]["located"] == 0
    assert found["calls"]["with_berth"] == 2 and found["calls"]["with_eta"] == 2
    assert found["calls"]["with_actual_arrival"] == 0 and found["versions"] >= 2
    assert "detail" not in str(found)


def test_new_views_handle_an_empty_graph(client):
    assert client.get("/api/network").json()["nodes"] == []
    assert client.get("/api/intelligence").json()["central"] == []
    assert client.get("/api/quality").json()["calls"]["total"] == 0
