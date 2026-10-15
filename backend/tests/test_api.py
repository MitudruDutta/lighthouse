"""The port desk over HTTP: every route reads what the graph holds, and none writes."""

import pytest
from fastapi.testclient import TestClient
from feed import poll, record, when
from lighthouse import close_episode, learn, open_episode, retire, write_playbook

from app.api import get_graph
from app.main import app
from app.portcalls import BERTH
from app.watcher import watch

VC2 = "FIHEL/VUOS/VC2"


def call(id, minute=0, berth="VC2", **times) -> dict:
    return record(id=id, minute=minute, imo=9000000 + id, berth=berth, **times)


@pytest.fixture
def client(graph):
    app.dependency_overrides[get_graph] = lambda: graph
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def desk(graph, client):
    """Two port calls expected at VC2 together, one at VA8, and the Watcher's look."""
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    poll(graph, 0, call(3, berth="VA8", eta=600, etd=700, name="Nordic Star"))
    (opened,) = watch(graph, when(5))
    client.episode, client.graph = opened["episode"], graph
    return client


def test_status_counts_what_the_graph_holds(desk):
    found = desk.get("/api/status").json()
    assert found["counts"]["PortCall"] == 3 and found["counts"]["Berth"] == 2
    assert found["open_episodes"] == 1 and found["last_poll"] is None


def test_berths_come_overloaded_first_with_their_names(desk):
    found = desk.get("/api/berths", params={"at": when(5).isoformat()}).json()
    assert [b["berth"] for b in found] == [VC2, "FIHEL/VUOS/VA8"]
    assert found[0]["overload"]["calls"] == [1, 2] and found[0]["name"] == "Berth VC2"
    assert found[0]["area"] == "Area VUOS" and found[1]["overload"] is None


def test_episodes_are_listed_and_read_whole(desk, graph):
    open_episode(graph, "past", "watcher", [(BERTH, VC2)], at=when(1))
    close_episode(graph, "past", "watcher", {"held": True}, at=when(2))
    (listed,) = desk.get("/api/episodes", params={"state": "open"}).json()
    assert listed["id"] == desk.episode and ["Berth", VC2] in listed["about"]
    assert [e["id"] for e in desk.get("/api/episodes", params={"state": "closed"}).json()] == [
        "past"
    ]
    assert len(desk.get("/api/episodes").json()) == 2
    found = desk.get(f"/api/episodes/{desk.episode}").json()  # the id holds slashes
    assert found["id"] == desk.episode and found["entries"][0]["type"] == "observation"
    assert desk.get("/api/episodes/nothing").status_code == 404


def test_port_call_is_given_as_it_was_at_any_time(desk, graph):
    poll(graph, 30, call(1, minute=30, eta=640, etd=900))
    now = desk.get("/api/portcalls/1").json()
    assert now["values"]["eta"].startswith("2026-10-12T20:40") and "fp" not in now["values"]
    assert now["relations"]["AT"] == [VC2] and len(now["versions"]) == 2
    assert all("fp" not in version for version in now["versions"])
    assert [e["id"] for e in now["episodes"]] == [desk.episode]
    then = desk.get("/api/portcalls/1", params={"at": when(10).isoformat()}).json()
    assert then["values"]["eta"].startswith("2026-10-12T20:00")
    assert desk.get("/api/portcalls/99").status_code == 404


def test_vessels_are_found_by_name_now_and_earlier(desk, graph):
    assert [v["key"] for v in desk.get("/api/search", params={"q": "nordic"}).json()] == [9000003]
    poll(graph, 60, call(3, minute=60, berth="VA8", eta=600, etd=700, name="Baltic Dawn"))
    assert desk.get("/api/search", params={"q": "nordic"}).json() == []
    earlier = desk.get("/api/search", params={"q": "nordic", "earlier": True}).json()
    assert [(e["key"], e["state"]["name"]) for e in earlier] == [(9000003, "Nordic Star")]
    berths = desk.get("/api/search", params={"q": "va8", "kind": "Berth"}).json()
    assert [b["key"] for b in berths] == ["FIHEL/VUOS/VA8"]


def test_vessel_and_berth_pages(desk):
    vessel = desk.get("/api/vessels/9000001").json()
    assert vessel["port_calls"] == [1] and vessel["versions"][0]["name"] == "Test Ship"
    berth = desk.get(f"/api/berths/{VC2}").json()
    assert berth["port_calls"] == [1, 2] and [e["id"] for e in berth["episodes"]] == [desk.episode]
    assert desk.get("/api/vessels/1").status_code == 404
    assert desk.get("/api/berths/FIHEL/NONE/X").status_code == 404


def test_lessons_and_playbooks_are_listed_with_their_evidence(desk, graph):
    open_episode(graph, "past", "watcher", [(BERTH, VC2)], at=when(1))
    close_episode(graph, "past", "watcher", {"held": True}, at=when(2))
    learn(graph, "vc2-holds", "reviewer", "VC2 takes them all", ["past"], [(BERTH, VC2)])
    for other in ("past-2", "past-3"):
        open_episode(graph, other, "watcher", [(BERTH, VC2)], at=when(1))
        close_episode(graph, other, "watcher", {"held": True}, at=when(2))
    learn(graph, "z-heavy", "reviewer", "VC2 is busy", ["past", "past-2", "past-3"])
    learn(graph, "b-retired", "reviewer", "VC2 is quiet", ["past"])
    retire(graph, "b-retired", "reviewer", "it is not")
    steps = [{"do": "propose another berth", "berth": "FIHEL/VUOS/VA8"}]
    trigger = {"situation": "berth-overload", "berth": VC2}
    write_playbook(graph, "move", "reviewer", trigger, steps, ["past"], needs=1)
    heavy, lesson = desk.get("/api/lessons").json()  # heaviest first; none retired
    assert (heavy["id"], heavy["weight"]) == ("z-heavy", 3)
    assert (lesson["id"], lesson["weight"], lesson["supported_by"]) == ("vc2-holds", 1, ["past"])
    (book,) = desk.get("/api/playbooks").json()
    assert book["steps"] == steps and book["trigger"] == trigger
    assert desk.get(f"/api/berths/{VC2}").json()["lessons"][0]["id"] == "vc2-holds"


def test_connection_of_two_port_calls_through_their_berth(desk):
    params = {"from_kind": "PortCall", "from_key": "1", "to_kind": "PortCall", "to_key": "2"}
    steps = desk.get("/api/connection", params=params).json()["steps"]
    assert [(s["from"][1], s["relation"], s["to"][1]) for s in steps] == [
        (1, "AT", VC2),
        (VC2, "AT", 2),
    ]
    later = params | {"to_key": "4"}
    poll(desk.graph, 30, call(4, minute=30, eta=800, etd=950))
    assert len(desk.get("/api/connection", params=later).json()["steps"]) == 2
    before = desk.get("/api/connection", params=later | {"at": when(10).isoformat()}).json()
    assert before["steps"] is None  # port call 4 was not known then


@pytest.mark.parametrize(
    "url",
    [
        "/api/search?q=x&kind=Episode",
        "/api/episodes?state=some",
        "/api/episodes?limit=0",
        "/api/search?q=x&limit=1000",
        "/api/connection?from_kind=Ship&from_key=1&to_kind=PortCall&to_key=2",
        "/api/connection?from_kind=PortCall&from_key=1&to_kind=PortCall&to_key=2&max_hops=50",
        "/api/berths?at=tomorrow",
    ],
)
def test_question_of_a_wrong_form_is_a_422(desk, url):
    response = desk.get(url)
    assert response.status_code == 422 and response.json()["detail"]


def test_routes_write_nothing(desk, graph):
    before = graph.ro_query("MATCH (n) RETURN count(n)").result_set
    for url in ("/api/status", "/api/berths", "/api/episodes", "/api/lessons", "/api/playbooks"):
        assert desk.get(url).status_code == 200
    assert desk.get("/api/portcalls/1").status_code == 200
    assert graph.ro_query("MATCH (n) RETURN count(n)").result_set == before


def test_screen_may_read_from_its_own_origin_only(desk):
    allowed = desk.get("/api/status", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    other = desk.get("/api/status", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers
