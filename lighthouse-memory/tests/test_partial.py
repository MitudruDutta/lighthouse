"""Partial updates: the values and relations an update names change, the rest stays, and an
update never writes over a change it did not see."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import connect
from devices import DEVICE, failures, row, when, write

from lighthouse import as_of, history, open_episode, record, related, remember, update
from lighthouse.write import partial


def current(graph) -> dict:
    return history(graph, DEVICE, "d1")[-1]


def test_one_value_changes_and_the_rest_stays(graph):
    write(graph, row(minute=0, firmware=3, last_seen=when(-5)))
    receipt = update(graph, DEVICE, "d1", when(10), "agent", values={"status": "hot"})
    assert receipt == {"key": "d1", "status": "changed"}
    now = current(graph)
    assert (now["status"], now["firmware"], now["last_seen"]) == ("hot", 3, when(-5))
    assert (now["valid_from"], now["by"]) == (when(10), "agent")
    assert related(graph, DEVICE, "d1", "LOCATED_IN") == ["r1"]
    assert related(graph, DEVICE, "d1", "USED_BY") == ["red"]
    assert as_of(graph, DEVICE, "d1", when(5))["status"] == "ok"  # the past is as it was


def test_a_value_of_none_is_removed(graph):
    write(graph, row(minute=0, firmware=3))
    assert update(graph, DEVICE, "d1", when(10), "agent", values={"firmware": None})["status"] == (
        "changed"
    )
    assert "firmware" not in current(graph) and current(graph)["status"] == "ok"


def test_one_relation_changes_and_the_others_keep_their_edges(graph):
    write(graph, row(minute=0, teams=("red", "blue")))
    receipt = update(graph, DEVICE, "d1", when(10), "agent", relations={"LOCATED_IN": "r2"})
    assert receipt["status"] == "changed"
    assert related(graph, DEVICE, "d1", "LOCATED_IN") == ["r2"]
    assert related(graph, DEVICE, "d1", "USED_BY") == ["blue", "red"]
    teams = graph.ro_query("MATCH (:Device)-[o:USED_BY]->() RETURN count(o)").result_set
    assert teams == [[2]]  # the edges of the teams go on: no edge was closed and opened
    update(graph, DEVICE, "d1", when(20), "agent", relations={"USED_BY": []})
    assert related(graph, DEVICE, "d1", "USED_BY") == []
    assert related(graph, DEVICE, "d1", "LOCATED_IN") == ["r2"]


def test_update_that_changes_nothing_is_unchanged(graph):
    write(graph, row(minute=0))
    assert update(graph, DEVICE, "d1", when(10), "agent", values={"status": "ok"}) == {
        "key": "d1",
        "status": "unchanged",
    }
    assert len(history(graph, DEVICE, "d1")) == 1


def test_entity_that_does_not_exist_starts_with_what_the_update_names(graph):
    receipt = update(graph, DEVICE, "d9", when(0), "agent", values={"status": "new"})
    assert receipt == {"key": "d9", "status": "created"}
    (state,) = history(graph, DEVICE, "d9")
    assert state["status"] == "new" and related(graph, DEVICE, "d9", "USED_BY") == []


def test_update_before_the_current_state_is_refused(graph):
    write(graph, row(minute=0), row(minute=20, status="hot"))
    receipt = update(graph, DEVICE, "d1", when(10), "agent", values={"status": "cold"})
    assert receipt["status"] == "stale" and "2026-01-01T00:20:00" in receipt["reason"]
    assert len(history(graph, DEVICE, "d1")) == 2
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("stale", "Device", "d1") and "cold" in detail


def test_update_at_the_start_of_the_current_state_is_a_conflict(graph):
    write(graph, row(minute=0))
    receipt = update(graph, DEVICE, "d1", when(0), "agent", values={"status": "cold"})
    assert receipt["status"] == "conflict"
    assert len(history(graph, DEVICE, "d1")) == 1


def test_update_names_its_evidence(graph):
    write(graph, row(minute=0))
    open_episode(graph, "look", "eye")
    entry = record(graph, "look", "observation", "eye", {"saw": "smoke"})["id"]
    update(graph, DEVICE, "d1", when(10), "eye", values={"status": "hot"}, entry=entry)
    assert current(graph)["entry"] == entry
    missing = update(graph, DEVICE, "d1", when(20), "eye", values={"status": "x"}, entry="look/9")
    assert missing["status"] == "missing"


def test_update_never_writes_over_a_change_it_did_not_see(graph, monkeypatch):
    write(graph, row(minute=0))
    reads = []
    read = partial._current

    def read_then_another_writer(*args):
        found = read(*args)
        if not reads:  # between this read and the write, another writer adds a State
            remember(graph, DEVICE, [row(minute=5, room="r2")], by="other")
        reads.append(found)
        return found

    monkeypatch.setattr(partial, "_current", read_then_another_writer)
    receipt = update(graph, DEVICE, "d1", when(10), "agent", values={"status": "hot"})
    assert receipt["status"] == "changed" and len(reads) == 2  # it read again
    assert current(graph)["status"] == "hot"
    assert related(graph, DEVICE, "d1", "LOCATED_IN") == ["r2"]  # the other change stays
    assert failures(graph) == []


def test_update_of_a_new_entity_never_writes_over_one_made_meanwhile(graph, monkeypatch):
    read = partial._current

    def read_then_another_writer(*args):
        found = read(*args)
        if found[2]["from"] is None:  # it does not exist yet; another writer makes it
            remember(graph, DEVICE, [row(minute=5, key="d9", room="r2")], by="other")
        return found

    monkeypatch.setattr(partial, "_current", read_then_another_writer)
    receipt = update(graph, DEVICE, "d9", when(10), "agent", values={"status": "hot"})
    assert receipt["status"] == "changed"
    assert related(graph, DEVICE, "d9", "LOCATED_IN") == ["r2"]  # what the other wrote stays
    assert history(graph, DEVICE, "d9")[-1]["status"] == "hot"


def test_update_that_never_sees_a_still_entity_is_refused_as_busy(graph, monkeypatch):
    write(graph, row(minute=0))
    read = partial._current
    minutes = iter(range(1, 100))

    def always_another_writer(*args):
        found = read(*args)
        remember(graph, DEVICE, [row(minute=next(minutes), level=next(minutes))], by="other")
        return found

    monkeypatch.setattr(partial, "_current", always_another_writer)
    receipt = update(graph, DEVICE, "d1", when(500), "agent", values={"status": "hot"})
    assert receipt["status"] == "busy"
    assert [reason for reason, *_ in failures(graph)] == ["busy"]
    assert "hot" not in [state.get("status") for state in history(graph, DEVICE, "d1")]


def test_concurrent_updates_lose_no_change(graph):
    write(graph, row(minute=0))

    def change(n):
        own = connect().select_graph(graph.name)
        return update(own, DEVICE, "d1", when(10 + n), f"agent{n}", values={f"v{n}": n})

    with ThreadPoolExecutor(8) as pool:
        receipts = list(pool.map(change, range(16)))
    applied = [n for n, receipt in enumerate(receipts) if receipt["status"] == "changed"]
    assert {receipt["status"] for receipt in receipts} <= {"changed", "stale"} and applied
    # Each update that was written was made from the State before it: none is lost.
    assert {f"v{n}" for n in applied} <= set(current(graph))
    assert len(history(graph, DEVICE, "d1")) == len(applied) + 1


INVALID = {
    "key of a wrong type": {"key": 1.5},
    "values not a map": {"values": ["hot"]},
    "relation not declared": {"relations": {"OWNS": "x"}},
    "relations not a map": {"relations": "r2"},
    "no time": {"t": None},
    "time in the future": {"t": "2999-01-01T00:00:00"},
    "value that cannot be stored": {"values": {"note": {"a": 1}}},
    "value of the engine": {"values": {"valid_to": 1}},
}


@pytest.mark.parametrize("name", INVALID)
def test_update_that_cannot_be_stored_is_refused_and_kept(graph, name):
    write(graph, row(minute=0))
    arguments = {"key": "d1", "t": when(10), "values": None, "relations": None} | INVALID[name]
    receipt = update(graph, DEVICE, by="agent", **arguments)
    assert receipt["status"] == "invalid" and receipt["reason"]
    assert [reason for reason, *_ in failures(graph)] == ["invalid"]
    assert len(history(graph, DEVICE, "d1")) == 1


@pytest.mark.parametrize("by", [None, "", 7])
def test_update_without_a_writer_is_refused(graph, by):
    with pytest.raises(ValueError):
        update(graph, DEVICE, "d1", when(10), by, values={"status": "hot"})
