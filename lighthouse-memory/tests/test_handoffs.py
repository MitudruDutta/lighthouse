"""Handoffs: work is passed by pointing at the record, and only the receiver can take it."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import connect
from devices import DEVICE, ROOM, count, failures, row, shape, when, write

from lighthouse import (
    accept,
    as_of,
    close_episode,
    episode,
    hand_off,
    handoffs_for,
    open_episode,
    record,
)


@pytest.fixture
def graph(graph):
    """A device, and an episode about it with one observation."""
    write(graph, row(key="d1", room="r1"))
    open_episode(graph, "ep1", by="watcher", about=[(DEVICE, "d1")], at=when(1))
    record(graph, "ep1", "observation", by="watcher", values={"what": "hot"}, at=when(2))
    return graph


def given(graph, handoff_id="h1", to="forecaster", points_to=("ep1/1",), **more) -> dict:
    return hand_off(graph, handoff_id, by="watcher", to=to, points_to=list(points_to), **more)


def check_handoffs(graph):
    """What must hold for every handoff, whatever was written."""
    handoffs = count(graph, "(h:Handoff)")
    assert count(graph, "(:Agent)-[g:GAVE]->(:Handoff)", "g") == handoffs
    assert count(graph, "(:Handoff)-[t:TO]->(:Agent)", "t") == handoffs
    assert count(graph, "(a:Agent)-[:GAVE]->(h:Handoff) WHERE a.id <> h.by") == 0
    assert count(graph, "(h:Handoff)-[:TO]->(a:Agent) WHERE a.id <> h.to") == 0
    assert count(graph, "(h:Handoff) WHERE NOT (h)-[:POINTS_TO]->()") == 0  # none points at nothing
    assert (
        count(graph, "(h:Handoff)-[p:POINTS_TO]->() WHERE p.as_of <> h.at OR p.as_of IS NULL") == 0
    )


# --- giving ---------------------------------------------------------------------------


def test_handoff_points_at_the_record_and_copies_none_of_it(graph):
    points = [
        "ep1/1",
        ("Episode", "ep1"),
        (DEVICE, "d1"),
        (ROOM, "r1"),
        ("Entry", "ep1/1"),
        "ep1/1",
    ]
    receipt = given(graph, points_to=points, values={"ask": "forecast the failure"}, at=when(5))
    assert receipt == {"id": "h1", "status": "given"}
    (handoff,) = handoffs_for(graph, "forecaster")
    assert handoff["points_to"] == [
        ("Device", "d1"),
        ("Entry", "ep1/1"),
        ("Episode", "ep1"),
        ("Room", "r1"),
    ]
    assert {k: v for k, v in handoff.items() if k not in ("points_to", "recorded_at")} == {
        "id": "h1",
        "by": "watcher",
        "to": "forecaster",
        "at": when(5),
        "ask": "forecast the failure",
    }
    assert "what" not in handoff  # the observation is read from the graph, not from the handoff
    assert count(graph, "(:Handoff)-[p:POINTS_TO]->()", "p") == 4  # no doubles
    path = (
        "(:Agent {id: 'watcher'})-[:GAVE]->(:Handoff {id: 'h1'})-[:TO]->(:Agent {id: 'forecaster'})"
    )
    assert count(graph, path) == 1
    check_handoffs(graph)


def test_receiver_reads_what_the_giver_pointed_at(graph):
    given(graph, points_to=["ep1/1", (DEVICE, "d1")], at=when(5))
    write(graph, row(key="d1", minute=10, status="cold"))  # the device changes after the handoff
    (handoff,) = handoffs_for(graph, "forecaster")
    assert ("Entry", "ep1/1") in handoff["points_to"]
    assert episode(graph, "ep1")["entries"][0]["what"] == "hot"
    pinned = graph.ro_query("MATCH (:Handoff)-[p:POINTS_TO]->(:Device) RETURN p.as_of").result_set
    assert as_of(graph, DEVICE, "d1", pinned[0][0])["status"] == "ok"  # as the giver saw it


def test_handoff_that_points_at_nothing_is_refused(graph):
    for nothing in ([], ()):
        receipt = given(graph, points_to=nothing)
        assert receipt["status"] == "invalid" and "must point at something" in receipt["reason"]
    assert count(graph, "(h:Handoff)") == 0 and [f[0] for f in failures(graph)] == ["invalid"] * 2


def test_handoff_that_points_at_something_unknown_is_refused_and_stored(graph):
    before = shape(graph)
    for points in (
        ["ep1/9"],
        [("Episode", "nope")],
        [(DEVICE, "nope")],
        ["ep1/1", (ROOM, "nowhere")],
    ):
        receipt = given(graph, to="mallory", points_to=points)
        assert receipt == {
            "id": None,
            "status": "missing",
            "reason": "something it points at does not exist",
        }
    nodes, edges = shape(graph)
    assert nodes.pop("WriteFailure") == 4 and (nodes, edges) == before  # no agent, no room made
    assert all(
        f[:3] == ["missing", "Handoff", "h1"] and "'to': 'mallory'" in f[3] for f in failures(graph)
    )


def test_handoff_given_again_changes_nothing(graph):
    given(graph, values={"ask": "first"}, at=when(5))
    again = hand_off(graph, "h1", by="mallory", to="mallory", points_to=[(DEVICE, "d1")])
    assert again == {"id": "h1", "status": "exists"}
    (handoff,) = handoffs_for(graph, "forecaster")
    assert (handoff["by"], handoff["ask"], handoff["points_to"]) == (
        "watcher",
        "first",
        [("Entry", "ep1/1")],
    )
    assert handoffs_for(graph, "mallory") == [] and count(graph, "(a:Agent {id: 'mallory'})") == 0


INVALID_HANDOFFS = {
    "map as a value": {"values": {"ask": {"deep": 1}}},
    "value named like the receiver": {"values": {"to": "mallory"}},
    "value named like the giver": {"values": {"by": "mallory"}},
    "value named like the acceptance": {"values": {"accepted_at": "2026-01-01"}},
    "value named like the id": {"values": {"id": "h2"}},
    "unsafe value name": {"values": {"a b": 1}},
    "points_to not a list": {"points_to": "ep1/1"},
    "reference of a wrong form": {"points_to": [("Device", "d1")]},
    "reference to a record that cannot be pointed at": {"points_to": [("Agent", "watcher")]},
    "reference with bad bytes": {"points_to": ["ep1/1\x00"]},
    "time that is not a time": {"at": "soon"},
    "time in the future": {"at": "2999-01-01T00:00:00Z"},
    "too much content": {"values": {f"p{i}": "x" * 50_000 for i in range(5)}},
}


@pytest.mark.parametrize("name", INVALID_HANDOFFS)
def test_invalid_handoff_is_refused_and_stored(graph, name):
    receipt = hand_off(
        graph,
        "h1",
        by="watcher",
        to="forecaster",
        **{"points_to": ["ep1/1"]} | INVALID_HANDOFFS[name],
    )
    assert receipt["status"] == "invalid" and receipt["id"] is None and receipt["reason"]
    assert count(graph, "(h:Handoff)") == 0 and handoffs_for(graph, "forecaster") == []
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("invalid", "Handoff", "h1") and receipt["reason"] in detail


@pytest.mark.parametrize("bad", [None, "", 7, "a\x00b", " padded "])
def test_names_must_be_text(graph, bad):
    for call in (
        lambda: hand_off(graph, bad, by="w", to="f", points_to=["ep1/1"]),
        lambda: hand_off(graph, "h1", by=bad, to="f", points_to=["ep1/1"]),
        lambda: hand_off(graph, "h1", by="w", to=bad, points_to=["ep1/1"]),
        lambda: accept(graph, bad, by="f"),
        lambda: accept(graph, "h1", by=bad),
        lambda: handoffs_for(graph, bad),
    ):
        with pytest.raises(ValueError, match="must be text"):
            call()
    assert count(graph, "(h:Handoff)") == 0 and failures(graph) == []


def test_database_error_is_stored_and_reported(graph, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr("lighthouse.handoffs._give_query", lambda groups: "RETURN no_such_function()")
        receipt = given(graph)
    assert receipt["status"] == "failed" and "no_such_function" in receipt["reason"]
    assert [f[:3] for f in failures(graph)] == [["failed", "Handoff", "h1"]]
    assert given(graph)["status"] == "given"


# --- accepting ------------------------------------------------------------------------


def test_only_the_receiver_accepts_and_only_once(graph):
    given(graph)
    assert accept(graph, "h1", by="mallory")["status"] == "refused"
    assert accept(graph, "h1", by="watcher")["status"] == "refused"  # not the giver either
    assert accept(graph, "nope", by="forecaster")["status"] == "unknown"
    assert handoffs_for(graph, "forecaster")[0].get("accepted_at") is None
    assert accept(graph, "h1", by="forecaster") == {"id": "h1", "status": "accepted"}
    first = handoffs_for(graph, "forecaster", waiting_only=False)[0]["accepted_at"]
    assert accept(graph, "h1", by="forecaster") == {"id": "h1", "status": "exists"}
    assert accept(graph, "h1", by="mallory")["status"] == "refused"
    assert handoffs_for(graph, "forecaster", waiting_only=False)[0]["accepted_at"] == first
    stored = failures(graph)  # who tried is on record
    assert sorted(f[0] for f in stored) == ["refused", "refused", "refused", "unknown"]
    assert sum("'by': 'mallory'" in f[3] for f in stored) == 2
    check_handoffs(graph)


def test_handoff_is_accepted_once_when_the_receiver_asks_many_times_at_once(graph):
    for n in range(10):
        given(graph, f"h{n}")
    results, start = [], threading.Barrier(8)

    def worker(agent):
        own = connect().select_graph(graph.name)
        start.wait(timeout=30)
        for n in range(10):
            results.append((agent, accept(own, f"h{n}", by=agent)["status"]))

    with ThreadPoolExecutor(max_workers=8) as pool:
        agents = ["forecaster"] * 4 + ["mallory"] * 4
        for future in [pool.submit(worker, agent) for agent in agents]:
            future.result()
    by_receiver = sorted(status for agent, status in results if agent == "forecaster")
    assert by_receiver == ["accepted"] * 10 + ["exists"] * 30
    assert {status for agent, status in results if agent == "mallory"} == {"refused"}
    assert handoffs_for(graph, "forecaster") == []
    assert len(handoffs_for(graph, "forecaster", waiting_only=False)) == 10
    check_handoffs(graph)


# --- reading --------------------------------------------------------------------------


def test_what_waits_for_an_agent_oldest_first(graph):
    given(graph, "newer", at=when(9))
    given(graph, "older", at=when(3))
    given(graph, "same-b", at=when(5))
    given(graph, "same-a", at=when(5))
    given(graph, "elsewhere", to="desk", at=when(1))
    waiting = [h["id"] for h in handoffs_for(graph, "forecaster")]
    assert waiting == ["older", "same-a", "same-b", "newer"]
    accept(graph, "same-a", by="forecaster")
    assert [h["id"] for h in handoffs_for(graph, "forecaster")] == ["older", "same-b", "newer"]
    assert len(handoffs_for(graph, "forecaster", waiting_only=False)) == 4
    assert [h["id"] for h in handoffs_for(graph, "desk")] == ["elsewhere"]
    assert handoffs_for(graph, "nobody") == []
    check_handoffs(graph)


def test_long_list_of_handoffs_is_complete(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.read.PAGE", 3)
    for n in range(8):
        given(graph, f"h{n}", at=when(n))
    assert [h["id"] for h in handoffs_for(graph, "forecaster")] == [f"h{n}" for n in range(8)]


def test_handoff_can_point_at_a_closed_episode_and_an_agent_can_give_to_itself(graph):
    close_episode(graph, "ep1", by="reviewer", outcome={"failed": False})
    assert given(graph, to="watcher", points_to=[("Episode", "ep1"), "ep1/2"])["status"] == "given"
    assert accept(graph, "h1", by="watcher")["status"] == "accepted"
    assert count(graph, "(a:Agent {id: 'watcher'})") == 1
    check_handoffs(graph)
