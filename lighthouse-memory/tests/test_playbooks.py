"""Playbooks: enough evidence before any is written, never changed, and a way to stop them."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import connect
from devices import DEVICE, count, failures, row, shape, when, write

from lighthouse import (
    close_episode,
    hand_off,
    open_episode,
    playbook,
    playbooks_for,
    ran,
    switch,
    write_playbook,
)

STEPS = [
    {"do": "tell the desk", "wait_minutes": 5},
    {"do": "move the device"},
    {"do": "check again"},
]
TRIGGER = {"event": "hot", "site": "a"}


@pytest.fixture
def graph(graph):
    """Episodes e1 to e8 have ended; `open` has not."""
    write(graph, row(key="d1"))
    for n in range(1, 9):
        open_episode(graph, f"e{n}", by="watcher", about=[(DEVICE, "d1")], at=when(n))
        close_episode(graph, f"e{n}", by="reviewer", outcome={"ok": True}, at=when(n + 1))
    open_episode(graph, "open", by="watcher", at=when(20))
    return graph


def written(graph, name="hot-device", supported_by=("e1", "e2", "e3"), **more) -> dict:
    trigger = more.pop("trigger", TRIGGER)
    steps = more.pop("steps", STEPS)
    episodes = supported_by if isinstance(supported_by, str) else list(supported_by)
    return write_playbook(graph, name, "reviewer", trigger, steps, episodes, **more)


def check_playbooks(graph):
    """What must hold for every playbook, whatever was written."""
    versions = graph.ro_query(
        "MATCH (pb:Playbook) WITH pb ORDER BY pb.version "
        "RETURN pb.name, collect(pb.version), collect(pb.enabled), collect(pb.id)"
    ).result_set
    for name, numbers, enabled, ids in versions:
        assert numbers == list(range(1, len(numbers) + 1)), name  # versions 1..n, each once
        assert ids == [f"{name}#{n}" for n in numbers]
        assert not any(enabled[:-1]), f"an old version of {name} is switched on"
    playbooks = count(graph, "(pb:Playbook)")
    assert count(graph, "(:Playbook)-[r:REPLACES]->(:Playbook)", "r") == playbooks - len(versions)
    assert (
        count(
            graph,
            "(a:Playbook)-[:REPLACES]->(b:Playbook) WHERE a.name <> b.name OR a.version <> b.version + 1",
        )
        == 0
    )
    assert count(graph, "(:Playbook)-[w:WHEN]->(:Trigger)", "w") == playbooks  # one trigger each
    assert count(graph, "(:Agent)-[w:WROTE]->(:Playbook)", "w") == playbooks
    assert count(graph, "(pb:Playbook) WHERE NOT (pb)-[:SUPPORTED_BY]->(:Episode)") == 0
    assert count(graph, "(:Playbook)-[:SUPPORTED_BY]->(ep:Episode) WHERE ep.closed_at IS NULL") == 0
    steps = graph.ro_query(
        "MATCH (pb:Playbook)-[:HAS_STEP]->(s:Step) WITH pb, s ORDER BY s.seq RETURN pb.id, collect(s.seq)"
    ).result_set
    assert len(steps) == playbooks and all(seq == list(range(1, len(seq) + 1)) for _, seq in steps)
    runs = graph.ro_query(
        "MATCH (pb:Playbook) OPTIONAL MATCH (pb)-[r:RAN_IN]->(:Episode) "
        "WITH pb, count(r) AS runs, "
        "sum(CASE WHEN r.succeeded = true THEN 1 ELSE 0 END) AS won, "
        "sum(CASE WHEN r.succeeded = false THEN 1 ELSE 0 END) AS lost "
        "RETURN pb.id, [pb.runs, pb.succeeded, pb.failed], [runs, won, lost]"
    ).result_set
    for playbook_id, stored, edges in runs:
        assert stored == [int(n) for n in edges], playbook_id  # every count equals its edges


# --- writing --------------------------------------------------------------------------


def test_playbook_is_stored_with_its_trigger_steps_and_evidence(graph):
    receipt = written(graph, at=when(30))
    assert receipt == {"id": "hot-device#1", "version": 1, "status": "written"}
    found = playbook(graph, "hot-device")
    assert {k: v for k, v in found.items() if k != "recorded_at"} == {
        "id": "hot-device#1",
        "name": "hot-device",
        "version": 1,
        "by": "reviewer",
        "at": when(30),
        "enabled": True,
        "runs": 0,
        "succeeded": 0,
        "failed": 0,
        "failed_in_a_row": 0,
        "trigger": TRIGGER,
        "steps": STEPS,
        "supported_by": ["e1", "e2", "e3"],
    }
    nodes, edges = shape(graph)
    assert (nodes["Playbook"], nodes["Trigger"], nodes["Step"]) == (1, 1, 3)
    assert (edges["WHEN"], edges["HAS_STEP"], edges["SUPPORTED_BY"]) == (1, 3, 3)
    check_playbooks(graph)


def test_next_version_replaces_the_one_before_and_changes_nothing_in_it(graph):
    written(graph, at=when(30))
    receipt = written(
        graph, steps=[{"do": "call the owner"}], supported_by=["e4", "e5", "e6"], at=when(31)
    )
    assert receipt == {"id": "hot-device#2", "version": 2, "status": "written"}
    new, old = playbook(graph, "hot-device"), playbook(graph, "hot-device", version=1)
    assert (new["version"], new["enabled"], new["steps"]) == (2, True, [{"do": "call the owner"}])
    assert (old["version"], old["enabled"], old["steps"]) == (1, False, STEPS)
    assert old["supported_by"] == ["e1", "e2", "e3"] and new["supported_by"] == ["e4", "e5", "e6"]
    assert (
        count(
            graph,
            "(:Playbook {id: 'hot-device#2'})-[r:REPLACES]->(:Playbook {id: 'hot-device#1'})",
            "r",
        )
        == 1
    )
    assert playbook(graph, "hot-device", version=3) is None and playbook(graph, "nope") is None
    check_playbooks(graph)


def test_playbook_needs_enough_episodes_that_ended(graph):
    assert written(graph, supported_by=["e1", "e2"])["status"] == "unsupported"
    assert (
        written(graph, supported_by=["e1", "e1", "e1", "e2"])["status"] == "unsupported"
    )  # doubles count once
    assert written(graph, supported_by=["e1", "e2"], needs=2)["status"] == "written"
    assert (
        written(graph, "strict", supported_by=["e1", "e2", "e3"], needs=4)["status"]
        == "unsupported"
    )
    assert (
        written(graph, "strict", supported_by=["e1", "e2", "e3", "e4"], needs=4)["status"]
        == "written"
    )
    assert [f[:3] for f in failures(graph)] == [["unsupported", "Playbook", "hot-device"]] * 2 + [
        ["unsupported", "Playbook", "strict"]
    ]
    check_playbooks(graph)


@pytest.mark.parametrize(
    "episodes", [["e1", "e2", "nope"], ["e1", "e2", "open"], ["e1", "e2", "e3", "open"]]
)
def test_playbook_that_rests_on_an_episode_that_is_not_real_is_refused(graph, episodes):
    before = shape(graph)
    receipt = written(graph, supported_by=episodes)
    assert receipt["status"] == "missing" and receipt["id"] is None
    nodes, edges = shape(graph)
    assert nodes.pop("WriteFailure") == 1 and (nodes, edges) == before
    assert playbook(graph, "hot-device") is None


def test_refused_version_leaves_the_current_one_switched_on(graph):
    written(graph)
    assert written(graph, supported_by=["e1"])["status"] == "unsupported"
    assert written(graph, steps=[])["status"] == "invalid"
    current = playbook(graph, "hot-device")
    assert (current["version"], current["enabled"]) == (1, True)
    check_playbooks(graph)


INVALID_PLAYBOOKS = {
    "no trigger": {"trigger": {}},
    "trigger not a map": {"trigger": ["hot"]},
    "trigger with a null only": {"trigger": {"event": None}},
    "trigger too wide": {"trigger": {f"p{n}": n for n in range(21)}},
    "trigger with an unsafe name": {"trigger": {"a b": 1}},
    "trigger with a map": {"trigger": {"a": {"b": 1}}},
    "no steps": {"steps": []},
    "steps not a list": {"steps": {"do": "x"}},
    "too many steps": {"steps": [{"do": "x"}] * 51},
    "step that is not a map": {"steps": ["tell the desk"]},
    "step with a map": {"steps": [{"do": {"a": 1}}]},
    "step that sets its own place": {"steps": [{"do": "x", "seq": 9}]},
    "step with bad bytes": {"steps": [{"do": "a\x00b"}]},
    "episodes not a list": {"supported_by": "e1"},
    "episode id of a wrong form": {"supported_by": ["e1", "e2", ""]},
    "too many episodes": {"supported_by": [f"e{n}" for n in range(201)]},
    "needs nothing": {"needs": 0},
    "needs not a number": {"needs": "3"},
    "needs a boolean": {"needs": True},
    "needs too many": {"needs": 201},
    "time that is not a time": {"at": "soon"},
    "time in the future": {"at": "2999-01-01T00:00:00Z"},
    "too much content": {"steps": [{f"p{i}": "x" * 50_000 for i in range(5)}]},
}


@pytest.mark.parametrize("name", INVALID_PLAYBOOKS)
def test_invalid_playbook_is_refused_and_stored(graph, name):
    receipt = written(graph, **INVALID_PLAYBOOKS[name])
    assert receipt["status"] == "invalid" and receipt["id"] is None and receipt["reason"]
    assert playbook(graph, "hot-device") is None and count(graph, "(n:Step)") == 0
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("invalid", "Playbook", "hot-device") and len(detail) <= 2_000


def test_database_error_is_stored_and_reported(graph, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr("lighthouse.playbooks.WRITE", "RETURN no_such_function(), 1")
        receipt = written(graph)
    assert receipt["status"] == "failed" and "no_such_function" in receipt["reason"]
    assert [f[:3] for f in failures(graph)] == [["failed", "Playbook", "hot-device"]]
    assert written(graph)["status"] == "written"


def test_writers_at_once_get_one_version_each_and_one_is_switched_on(graph):
    results, start = [], threading.Barrier(8)

    def writer(n):
        own = connect().select_graph(graph.name)
        start.wait(timeout=30)
        results.append(
            write_playbook(
                own,
                "hot-device",
                f"agent-{n}",
                TRIGGER,
                [{"do": f"step of {n}"}],
                ["e1", "e2", "e3"],
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in [pool.submit(writer, n) for n in range(8)]:
            future.result()
    assert sorted(r["version"] for r in results) == list(range(1, 9))
    assert count(graph, "(pb:Playbook {enabled: true})") == 1
    assert playbook(graph, "hot-device")["version"] == 8
    check_playbooks(graph)


# --- the off switch -------------------------------------------------------------------


def test_playbook_can_be_switched_off_and_on(graph):
    written(graph)
    assert switch(graph, "hot-device", "admin", on=False) == {"id": "hot-device#1", "status": "off"}
    assert switch(graph, "hot-device", "admin", on=False)["status"] == "exists"
    off = playbook(graph, "hot-device")
    assert (off["enabled"], off["switched_by"]) == (False, "admin") and off[
        "switched_at"
    ] is not None
    assert playbooks_for(graph, TRIGGER) == []
    assert switch(graph, "hot-device", "admin", on=True)["status"] == "on"
    assert switch(graph, "hot-device", "admin", on=True)["status"] == "exists"
    assert [pb["id"] for pb in playbooks_for(graph, TRIGGER)] == ["hot-device#1"]
    assert switch(graph, "nope", "admin", on=False)["status"] == "unknown"
    assert [f[:3] for f in failures(graph)] == [["unknown", "Playbook", "nope"]]


def test_switch_works_on_the_newest_version_only(graph):
    written(graph)
    written(graph)
    assert switch(graph, "hot-device", "admin", on=False)["id"] == "hot-device#2"
    assert switch(graph, "hot-device", "admin", on=True)["id"] == "hot-device#2"
    assert playbook(graph, "hot-device", version=1)["enabled"] is False  # an old version stays off
    check_playbooks(graph)


# --- runs -----------------------------------------------------------------------------


def test_run_is_recorded_and_judged_once(graph):
    written(graph)
    assert ran(graph, "hot-device", "desk", "open", at=when(40)) == {
        "id": "hot-device#1",
        "status": "recorded",
        "enabled": True,
    }
    assert ran(graph, "hot-device", "desk", "open")["status"] == "exists"
    assert ran(graph, "hot-device", "reviewer", "open", succeeded=True)["status"] == "judged"
    assert (
        ran(graph, "hot-device", "mallory", "open", succeeded=False)["status"] == "exists"
    )  # said once
    found = playbook(graph, "hot-device")
    assert (found["runs"], found["succeeded"], found["failed"]) == (1, 1, 0)
    judged = graph.ro_query(
        "MATCH (:Playbook)-[r:RAN_IN]->(:Episode) RETURN r.by, r.succeeded, r.judged_by"
    )
    assert judged.result_set == [["desk", True, "reviewer"]]
    check_playbooks(graph)


def test_playbook_switches_itself_off_after_failures_in_a_row(graph):
    written(graph)
    assert ran(graph, "hot-device", "desk", "e1", succeeded=False)["enabled"] is True
    assert ran(graph, "hot-device", "desk", "e2", succeeded=False)["enabled"] is True
    assert (
        ran(graph, "hot-device", "desk", "e3", succeeded=True)["enabled"] is True
    )  # the row is broken
    assert playbook(graph, "hot-device")["failed_in_a_row"] == 0
    for episode_id in ("e4", "e5"):
        assert ran(graph, "hot-device", "desk", episode_id, succeeded=False)["enabled"] is True
    stopped = ran(graph, "hot-device", "desk", "e6", succeeded=False, at=when(60))
    assert stopped == {"id": "hot-device#1", "status": "recorded", "enabled": False}
    found = playbook(graph, "hot-device")
    assert (found["enabled"], found["failed"], found["failed_in_a_row"], found["stopped_at"]) == (
        False,
        5,
        3,
        when(60),
    )
    assert playbooks_for(graph, TRIGGER) == []
    check_playbooks(graph)


def test_switching_on_again_starts_the_count_of_failures_anew(graph):
    written(graph)
    for episode_id in ("e1", "e2", "e3"):
        ran(graph, "hot-device", "desk", episode_id, succeeded=False)
    assert playbook(graph, "hot-device")["enabled"] is False
    switch(graph, "hot-device", "admin", on=True)
    assert playbook(graph, "hot-device")["failed_in_a_row"] == 0
    assert ran(graph, "hot-device", "desk", "e4", succeeded=False)["enabled"] is True
    assert playbook(graph, "hot-device")["failed"] == 4


def test_number_of_failures_that_stops_a_playbook_can_be_chosen(graph):
    written(graph)
    assert ran(graph, "hot-device", "desk", "e1", succeeded=False, stop_after=1)["enabled"] is False
    written(graph, "patient")
    for n in range(1, 6):
        assert (
            ran(graph, "patient", "desk", f"e{n}", succeeded=False, stop_after=6)["enabled"] is True
        )


def test_failure_that_is_judged_later_counts_too(graph):
    written(graph)
    for episode_id in ("e1", "e2", "e3"):
        ran(graph, "hot-device", "desk", episode_id)  # how they ended is not known yet
    assert playbook(graph, "hot-device")["enabled"] is True
    assert ran(graph, "hot-device", "reviewer", "e1", succeeded=False)["enabled"] is True
    assert ran(graph, "hot-device", "reviewer", "e2", succeeded=False)["enabled"] is True
    assert ran(graph, "hot-device", "reviewer", "e3", succeeded=False) == {
        "id": "hot-device#1",
        "status": "judged",
        "enabled": False,
    }
    check_playbooks(graph)


def test_run_of_something_that_does_not_exist_is_refused(graph):
    written(graph)
    assert ran(graph, "hot-device", "desk", "nope", succeeded=True)["status"] == "missing"
    assert ran(graph, "nope", "desk", "e1", succeeded=True)["status"] == "unknown"
    assert playbook(graph, "hot-device")["runs"] == 0
    assert sorted(f[0] for f in failures(graph)) == ["missing", "unknown"]


def test_many_runs_at_once_lose_no_count_and_stop_the_playbook_once(graph):
    written(graph)
    results, start = [], threading.Barrier(8)

    def agent(n):
        own = connect().select_graph(graph.name)
        start.wait(timeout=30)
        results.append(ran(own, "hot-device", f"agent-{n}", f"e{n}", succeeded=False))

    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in [pool.submit(agent, n) for n in range(1, 9)]:
            future.result()
    assert [r["status"] for r in results] == ["recorded"] * 8
    assert (
        sorted(r["enabled"] for r in results) == [False] * 6 + [True] * 2
    )  # off from the third failure
    found = playbook(graph, "hot-device")
    assert (found["runs"], found["failed"], found["failed_in_a_row"], found["enabled"]) == (
        8,
        8,
        8,
        False,
    )
    check_playbooks(graph)


# --- finding the playbook for a situation ---------------------------------------------


def test_playbook_fits_when_the_situation_has_everything_its_trigger_names(graph):
    written(graph, "exact", trigger={"event": "hot", "site": "a"})
    written(graph, "broad", trigger={"event": "hot"})
    written(graph, "other", trigger={"event": "cold"})
    written(graph, "typed", trigger={"event": "hot", "level": 3})

    def names(situation):
        return sorted(pb["name"] for pb in playbooks_for(graph, situation))

    assert names({"event": "hot", "site": "a", "extra": "ignored"}) == ["broad", "exact"]
    assert names({"event": "hot", "site": "b"}) == ["broad"]
    assert names({"event": "hot", "level": 3}) == ["broad", "typed"]
    assert names({"event": "hot", "level": "3"}) == [
        "broad"
    ]  # the value must be the same, not alike
    assert names({"event": "cold"}) == ["other"]
    assert names({"site": "a"}) == [] and names({}) == []
    assert playbooks_for(graph, {"event": "hot", "site": "a"})[0]["steps"] == STEPS


def test_only_the_newest_version_that_is_switched_on_is_given_out(graph):
    written(graph, steps=[{"do": "old way"}])
    written(graph, steps=[{"do": "new way"}])
    found = playbooks_for(graph, TRIGGER)
    assert [(pb["id"], pb["steps"]) for pb in found] == [("hot-device#2", [{"do": "new way"}])]
    switch(graph, "hot-device", "admin", on=False)
    assert playbooks_for(graph, TRIGGER) == []  # the old version does not come back


def test_playbook_with_the_better_record_comes_first(graph):
    for name in ("untried", "good", "poor", "busy"):
        written(graph, name, trigger={"event": "hot"})
    ran(graph, "good", "desk", "e1", succeeded=True)
    ran(graph, "good", "desk", "e2", succeeded=True)
    ran(graph, "poor", "desk", "e1", succeeded=False)
    ran(graph, "busy", "desk", "e1", succeeded=True)
    ran(graph, "busy", "desk", "e2", succeeded=False)
    assert [pb["name"] for pb in playbooks_for(graph, {"event": "hot"})] == [
        "good",
        "busy",
        "untried",
        "poor",
    ]


def test_long_list_of_playbooks_is_complete(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.read.PAGE", 3)
    for n in range(8):
        written(graph, f"p{n}", trigger={"event": "hot"})
    assert len(playbooks_for(graph, {"event": "hot"})) == 8


def test_handoff_can_point_at_a_playbook(graph):
    written(graph)
    receipt = hand_off(
        graph, "h1", by="reviewer", to="desk", points_to=[("Playbook", "hot-device#1")]
    )
    assert receipt["status"] == "given"


# --- what is refused ------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, "", 7, "a\x00b", " padded "])
def test_names_must_be_text(graph, bad):
    written(graph)
    for call in (
        lambda: write_playbook(graph, bad, "r", TRIGGER, STEPS, ["e1", "e2", "e3"]),
        lambda: write_playbook(graph, "p", bad, TRIGGER, STEPS, ["e1", "e2", "e3"]),
        lambda: switch(graph, bad, "r", on=False),
        lambda: switch(graph, "hot-device", bad, on=False),
        lambda: ran(graph, bad, "r", "e1"),
        lambda: ran(graph, "hot-device", bad, "e1"),
        lambda: ran(graph, "hot-device", "r", bad),
        lambda: playbook(graph, bad),
    ):
        with pytest.raises(ValueError, match="must be text"):
            call()
    assert count(graph, "(pb:Playbook)") == 1 and playbook(graph, "hot-device")["enabled"] is True


@pytest.mark.parametrize("flag", [None, 1, 0, "yes"])
def test_switch_and_result_must_be_true_or_false(graph, flag):
    written(graph)
    with pytest.raises(TypeError, match="on must be"):
        switch(graph, "hot-device", "admin", on=flag)
    if flag is not None:
        with pytest.raises(TypeError, match="succeeded"):
            ran(graph, "hot-device", "desk", "e1", succeeded=flag)
    assert playbook(graph, "hot-device")["runs"] == 0


@pytest.mark.parametrize("stop_after", [0, -1, 1.5, "3", None, True])
def test_number_of_failures_of_a_wrong_form_is_refused(graph, stop_after):
    written(graph)
    with pytest.raises(ValueError, match="stop_after"):
        ran(graph, "hot-device", "desk", "e1", succeeded=False, stop_after=stop_after)


def test_read_of_a_wrong_form_is_refused(graph):
    with pytest.raises(ValueError, match="version"):
        playbook(graph, "hot-device", version="1")
    for situation in (["event"], "hot", {"a b": 1}, {"a": {"b": 1}}):
        with pytest.raises((TypeError, ValueError)):
            playbooks_for(graph, situation)
