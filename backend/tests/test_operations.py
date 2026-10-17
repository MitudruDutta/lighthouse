import uuid

import pytest
from fastapi.testclient import TestClient
from lighthouse import close_episode, ensure_schema, open_episode, record

from app import operations
from app.api import get_graph
from app.main import app


@pytest.fixture
def client(graph, db, monkeypatch):
    private = {}

    def workspace(tenant):
        if tenant not in private:
            private[tenant] = db.select_graph("test_ops_" + uuid.uuid4().hex)
            ensure_schema(private[tenant])
        return private[tenant]

    monkeypatch.setattr(operations, "workspace", workspace)
    monkeypatch.setenv(
        "LIGHTHOUSE_DESK_USERS",
        "a" * 32 + "=team/ann," + "b" * 32 + "=team/bob," + "c" * 32 + "=other/ann",
    )
    app.dependency_overrides[get_graph] = lambda: graph
    open_episode(graph, "berth-overload:FIHEL/VC2:sample", "watcher")
    record(
        graph,
        "berth-overload:FIHEL/VC2:sample",
        "observation",
        "watcher",
        {"berth": "FIHEL/VC2", "expected": 3, "capacity": 1},
    )
    graph.query("MERGE (p:Port {locode:'FIHEL'}) SET p.name='Helsinki'")
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()
    for memory in private.values():
        memory.delete()


def auth(letter="a"):
    return {"Authorization": "Bearer " + letter * 32}


def mutate(client, operation, revision, text="", user="a"):
    return client.post(
        "/api/operations/case",
        headers=auth(user),
        json={
            "id": "berth-overload:FIHEL/VC2:sample",
            "operation": operation,
            "revision": revision,
            "text": text,
        },
    )


def test_profile_and_watchlist_are_personal_and_validated(client):
    assert client.get("/api/operations/profile").status_code == 401
    profile = {
        "name": "Ann",
        "timezone": "Asia/Kolkata",
        "focus": "finland",
        "ports": ["FIHEL"],
        "vessels": [],
    }
    assert client.put("/api/operations/profile", headers=auth(), json=profile).status_code == 200
    assert client.get("/api/operations/profile", headers=auth()).json()["ports"] == ["FIHEL"]
    assert client.get("/api/operations/profile", headers=auth("b")).json()["ports"] == []
    assert client.get("/api/operations/profile", headers=auth("c")).json()["ports"] == []
    assert (
        client.put(
            "/api/operations/profile", headers=auth(), json={**profile, "ports": ["unknown"]}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/operations/profile", headers=auth(), json={**profile, "timezone": "bad/zone"}
        ).status_code
        == 422
    )
    queue = client.get("/api/operations/cases", headers=auth()).json()
    assert queue["cases"][0]["watching"] is True
    assert queue["cases"][0]["impact"].startswith("3 expected")


def test_claim_approval_outcome_and_reopen_keep_source_unchanged(client):
    assert mutate(client, "resolve", 0, "Finished").status_code == 403
    assert mutate(client, "claim", 0).status_code == 200
    assert mutate(client, "claim", 0, user="b").status_code == 409
    assert mutate(client, "propose", 1, "Call berth coordinator", user="b").status_code == 403
    assert mutate(client, "approve", 1).status_code == 409
    assert mutate(client, "propose", 1, "Call berth coordinator").status_code == 200
    assert mutate(client, "approve", 2).status_code == 200
    assert mutate(client, "resolve", 3, "   ").status_code == 422
    assert (
        mutate(client, "resolve", 3, "Coordinator confirmed staggered arrivals").status_code == 200
    )
    params = {"id": "berth-overload:FIHEL/VC2:sample"}
    case = client.get("/api/operations/case", params=params, headers=auth()).json()
    assert case["case"]["status"] == "resolved" and case["case"]["action_status"] == "approved"
    assert case["source"].get("closed_at") is None
    assert len(case["events"]) == 4 and case["events"][0]["by"] == "ann"
    assert mutate(client, "claim", 4).status_code == 409
    assert mutate(client, "reopen", 4).status_code == 200
    assert mutate(client, "release", 5).status_code == 200
    assert mutate(client, "claim", 6, user="b").status_code == 200
    other = client.get("/api/operations/case", params=params, headers=auth("c")).json()
    assert other["case"]["revision"] == 0 and other["events"] == []


def test_assessed_and_source_cleared_are_distinct_from_human_resolution(client, graph):
    id = "berth-overload:FIHEL/VC2:sample"
    record(
        graph,
        id,
        "assessment",
        "desk",
        {"text": "Review the arrival window.", "outcome": "grounded"},
    )
    assert (
        client.get("/api/operations/cases", headers=auth()).json()["cases"][0]["status"]
        == "needs_review"
    )
    close_episode(graph, id, "watcher", {"cleared": True})
    found = client.get("/api/operations/cases", headers=auth()).json()["cases"][0]
    assert found["status"] == "source_cleared" and found["source_cleared"] is True
    assert mutate(client, "claim", 0).status_code == 200
    assert (
        client.get("/api/operations/cases", headers=auth()).json()["cases"][0]["status"]
        == "investigating"
    )


def test_competing_claims_have_one_owner(client):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda user: mutate(client, "claim", 0, user=user).status_code, ["a", "b"])
        )
    assert sorted(results) == [200, 409]
    case = client.get(
        "/api/operations/case", params={"id": "berth-overload:FIHEL/VC2:sample"}, headers=auth()
    ).json()["case"]
    assert case["owner"] in {"ann", "bob"} and case["revision"] == 1


def test_prior_outcomes_are_recalled_only_inside_the_same_workspace(client, graph):
    assert mutate(client, "claim", 0).status_code == 200
    assert (
        mutate(client, "resolve", 1, "Confirmed staggered arrivals with coordinator").status_code
        == 200
    )
    next_id = "berth-overload:FIHEL/VC3:next"
    open_episode(graph, next_id, "watcher")
    record(
        graph,
        next_id,
        "observation",
        "watcher",
        {"berth": "FIHEL/VC3", "expected": 4, "capacity": 2},
    )
    found = client.get("/api/operations/case", params={"id": next_id}, headers=auth()).json()
    assert found["prior_outcomes"][0]["outcome"] == "Confirmed staggered arrivals with coordinator"
    assert (
        client.get("/api/operations/case", params={"id": next_id}, headers=auth("c")).json()[
            "prior_outcomes"
        ]
        == []
    )


def test_followed_vessel_is_recognized_in_queue_and_case(client, graph):
    graph.query(
        "MATCH (e:Episode {id:'berth-overload:FIHEL/VC2:sample'}) "
        "MERGE (p:PortCall {id:123}) MERGE (v:Vessel {imo:9999999}) "
        "MERGE (e)-[:ABOUT {label:'PortCall',key:123}]->(p) MERGE (p)-[:MADE_BY]->(v)"
    )
    assert (
        client.put(
            "/api/operations/profile", headers=auth(), json={"name": "Ann", "vessels": ["9999999"]}
        ).status_code
        == 200
    )
    queue = client.get("/api/operations/cases", headers=auth()).json()
    detail = client.get(
        "/api/operations/case", headers=auth(), params={"id": "berth-overload:FIHEL/VC2:sample"}
    ).json()
    assert queue["cases"][0]["watching"] is True
    assert detail["case"]["watching"] is True


def test_a_berth_the_feed_cannot_name_is_shown_by_its_code(client, graph):
    def title():
        return client.get("/api/operations/cases", headers=auth()).json()["cases"][0]["title"]

    graph.query("MERGE (b:Berth {key:'FIHEL/VC2'}) SET b.name='Ei tiedossa'")
    assert title() == "Arrival overlap at FIHEL/VC2"
    graph.query("MATCH (b:Berth {key:'FIHEL/VC2'}) SET b.name='Länsisatama 2'")
    assert title() == "Arrival overlap at Länsisatama 2"
