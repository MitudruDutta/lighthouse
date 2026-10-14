"""The write rule: rows become versions, relation edges get windows, batches keep one
entity per query."""

import random

import pytest
from devices import (
    DEVICE,
    PERSON,
    ROOM,
    check_invariants,
    count,
    failures,
    row,
    shape,
    when,
    windows,
    write,
)
from oracle import as_row, assert_matches_the_oracle, random_timelines

from lighthouse import (
    Kind,
    as_of,
    ensure_schema,
    history,
    open_episode,
    record,
    related,
    remember,
)


def test_first_row_becomes_an_entity_a_state_and_relation_edges(graph):
    first = row(room="r1", teams=["red", "blue"], firmware=3, last_seen=when(-5))
    assert remember(graph, DEVICE, [first], by="inventory") == [{"key": "d1", "status": "created"}]
    nodes, edges = shape(graph)
    assert nodes == {"Device": 1, "State": 1, "Room": 1, "Team": 2}
    assert edges == {"HAS_STATE": 1, "LOCATED_IN": 1, "USED_BY": 2}
    device = graph.ro_query("MATCH (d:Device) RETURN d").result_set[0][0].properties
    assert device == {"serial": "d1", "status": "ok", "firmware": 3, "last_seen": when(-5)}
    (state,) = history(graph, DEVICE, "d1")
    assert {k: v for k, v in state.items() if k not in ("fp", "recorded_at")} == {
        "status": "ok",
        "firmware": 3,
        "last_seen": when(-5),
        "valid_from": when(0),
        "by": "inventory",
    }
    assert windows(graph, "LOCATED_IN") == [("r1", when(0), None)]
    assert windows(graph, "USED_BY") == [("blue", when(0), None), ("red", when(0), None)]
    by = graph.ro_query("MATCH (:Device)-[o:LOCATED_IN|USED_BY]->() RETURN DISTINCT o.by")
    assert by.result_set == [["inventory"]]
    check_invariants(graph)


def test_same_row_again_writes_nothing(graph):
    write(graph, row())
    before = shape(graph)
    assert write(graph, row()) == ["unchanged"]
    assert shape(graph) == before


def test_later_row_with_the_same_content_writes_nothing(graph):
    write(graph, row(minute=0, teams=["red", "blue"]))
    before = shape(graph)
    assert write(graph, row(minute=30, teams=["blue", "red", "red"])) == ["unchanged"]
    assert shape(graph) == before and "valid_to" not in history(graph, DEVICE, "d1")[0]


def test_null_value_and_missing_value_are_the_same(graph):
    write(graph, row(minute=0, note=None, room=None, teams=[]))
    plain = {"key": "d1", "t": when(5), "values": {"status": "ok"}}
    assert write(graph, plain) == ["unchanged"]
    assert windows(graph, "LOCATED_IN") == [] and windows(graph, "USED_BY") == []


def test_values_of_every_storable_type_come_back_unchanged(graph):
    values = {"text": 'quote " and \\ and \n newline ☃', "whole": -7, "real": 2.5, "flag": False}
    values |= {"many": [1, 2, 3], "tags": ["a", "b"], "empty": ""}
    write(graph, row(**values))
    state = history(graph, DEVICE, "d1")[0]
    assert {k: state[k] for k in values} == values


def test_declared_time_is_stored_as_a_time_and_other_text_stays_text(graph):
    write(graph, row(last_seen="2026-01-01T02:00:00+02:00", installed="2026-01-01T02:00:00"))
    state = history(graph, DEVICE, "d1")[0]
    assert state["last_seen"] == when(0) and state["installed"] == "2026-01-01T02:00:00"
    newer = count(graph, "(d:Device) WHERE d.last_seen > localdatetime('2025-12-31T00:00:00')")
    assert newer == 1


def test_change_of_only_a_time_value_is_a_new_state(graph):
    statuses = write(graph, row(minute=0, last_seen=when(0)), row(minute=5, last_seen=when(4)))
    assert statuses == ["created", "changed"]
    assert [s["last_seen"] for s in history(graph, DEVICE, "d1")] == [when(0), when(4)]
    assert write(graph, row(minute=9, last_seen="2026-01-01T00:04:00.900Z")) == ["unchanged"]


def test_integer_and_text_keys(graph):
    numbered = Kind("Ticket", key="number", relations={"FOR": ROOM})
    ensure_schema(graph, [numbered])
    rows = [{"key": 7, "t": when(0), "relations": {"FOR": "r1"}}, {"key": 8, "t": when(0)}]
    assert write(graph, *rows, kind=numbered) == ["created", "created"]
    assert related(graph, numbered, 7, "FOR") == ["r1"] and history(graph, numbered, 8) != []


def test_replay_of_a_known_sequence_gives_exact_history(graph):
    sequence = [
        row(minute=0, room="r1", teams=["red"], status="ok"),
        row(minute=10, room="r1", teams=["red"], status="ok"),  # nothing changed
        row(minute=20, room="r1", teams=["red"], status="hot"),  # a value changed
        row(minute=45, room="r2", teams=["red"], status="hot"),  # moved
        row(minute=50, room="r2", teams=["red"], status="hot"),  # nothing changed
        row(minute=70, room="r2", teams=["red", "blue"], status="hot"),  # second team
        row(minute=90, room=None, teams=["blue"], status="off"),  # left the room
    ]
    receipts = [write(graph, r)[0] for r in sequence]
    assert receipts == [
        "created",
        "unchanged",
        "changed",
        "changed",
        "unchanged",
        "changed",
        "changed",
    ]
    states = history(graph, DEVICE, "d1")
    assert [(s["valid_from"], s.get("valid_to"), s["status"]) for s in states] == [
        (when(0), when(20), "ok"),
        (when(20), when(45), "hot"),
        (when(45), when(70), "hot"),
        (when(70), when(90), "hot"),
        (when(90), None, "off"),
    ]
    # The chain in the graph has the same order as the validity windows.
    chain = graph.ro_query(
        "MATCH p = (first:State)-[:NEXT*0..]->(s:State) WHERE NOT ()-[:NEXT]->(first) "
        "RETURN s.valid_from ORDER BY length(p)"
    ).result_set
    assert [r[0] for r in chain] == [s["valid_from"] for s in states]
    # Each relation has its own windows. A change elsewhere does not close an edge.
    assert windows(graph, "LOCATED_IN") == [("r1", when(0), when(45)), ("r2", when(45), when(90))]
    assert windows(graph, "USED_BY") == [("red", when(0), when(90)), ("blue", when(70), None)]
    check_invariants(graph)


def test_removed_value_leaves_the_entity_and_stays_in_the_old_state(graph):
    write(graph, row(minute=0, firmware=3, last_seen=when(0)), row(minute=5))
    old, new = history(graph, DEVICE, "d1")
    assert old["firmware"] == 3 and old["last_seen"] == when(0)
    assert "firmware" not in new and "last_seen" not in new
    device = graph.ro_query("MATCH (d:Device) RETURN d").result_set[0][0].properties
    assert device == {"serial": "d1", "status": "ok"}
    check_invariants(graph)


def test_value_that_goes_back_is_a_new_state(graph):
    write(graph, *(row(minute=m, status=s) for m, s in ((0, "a"), (5, "b"), (9, "a"))))
    assert [s["status"] for s in history(graph, DEVICE, "d1")] == ["a", "b", "a"]
    check_invariants(graph)


def test_relation_that_comes_back_is_a_second_edge(graph):
    write(graph, *(row(minute=m, room=r) for m, r in ((0, "r1"), (5, "r2"), (9, "r1"))))
    assert windows(graph, "LOCATED_IN") == [
        ("r1", when(0), when(5)),
        ("r2", when(5), when(9)),
        ("r1", when(9), None),
    ]
    assert count(graph, "(r:Room)") == 2
    check_invariants(graph)


def test_target_that_is_remembered_later_keeps_its_edges(graph):
    write(graph, row(room="r1"))  # the room exists only as a target so far
    assert graph.ro_query("MATCH (r:Room) RETURN properties(r)").result_set == [[{"code": "r1"}]]
    receipts = remember(graph, ROOM, [{"key": "r1", "t": when(3), "values": {"floor": 2}}], by="x")
    assert receipts == [{"key": "r1", "status": "created"}]
    assert count(graph, "(:Device)-[o:LOCATED_IN]->(:Room {code: 'r1', floor: 2})", "o") == 1
    check_invariants(graph)


def test_relation_to_the_same_kind(graph):
    ensure_schema(graph, [PERSON])
    ann = {"key": "ann@x", "t": when(0), "relations": {"KNOWS": ["bob@x", "ann@x"]}}
    assert write(graph, ann, kind=PERSON) == ["created"]
    assert related(graph, PERSON, "ann@x", "KNOWS") == ["ann@x", "bob@x"]
    assert count(graph, "(p:Person)") == 2
    check_invariants(graph)


def observation(graph, saw: str) -> str:
    """The id of a new entry that a row can name as where it comes from."""
    open_episode(graph, "look", "eye")
    return record(graph, "look", "observation", "eye", {"saw": saw})["id"]


def test_state_points_at_the_entry_it_came_from(graph):
    first, second = observation(graph, "ok"), observation(graph, "hot")
    rows = [dict(row(minute=0), entry=first), dict(row(minute=30, status="hot"), entry=second)]
    assert write(graph, *rows) == ["created", "changed"]
    assert [s.get("entry") for s in history(graph, DEVICE, "d1")] == [first, second]
    assert as_of(graph, DEVICE, "d1", when(10))["entry"] == first
    edges = graph.ro_query("MATCH (s:State)-[:FROM]->(n:Entry) RETURN s.valid_from, n.id")
    assert sorted(edges.result_set) == [[when(0), first], [when(30), second]]


def test_entry_is_evidence_not_content(graph):
    first, second = observation(graph, "ok"), observation(graph, "ok again")
    write(graph, dict(row(minute=0), entry=first))
    # The same content from another entry is no change, and the State keeps its evidence.
    assert write(graph, dict(row(minute=10), entry=second)) == ["unchanged"]
    assert [s.get("entry") for s in history(graph, DEVICE, "d1")] == [first]
    assert write(graph, row(minute=20, status="hot")) == ["changed"]  # a row without one
    assert "entry" not in history(graph, DEVICE, "d1")[1]


def test_row_from_an_entry_that_does_not_exist_is_refused(graph):
    known = observation(graph, "ok")
    rows = [dict(row(key="d1"), entry="look/99"), dict(row(key="d2"), entry=known)]
    receipts = remember(graph, DEVICE, rows, by="eye")
    assert [r["status"] for r in receipts] == ["missing", "created"]
    assert "look/99" in receipts[0]["reason"]
    assert count(graph, "(d:Device {serial: 'd1'})") == 0  # not even an empty entity
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("missing", "Device", "d1") and "look/99" in detail


def test_late_row_points_at_its_entry(graph):
    late = observation(graph, "cold")
    write(graph, row(minute=0), row(minute=30, status="hot"))
    assert write(graph, dict(row(minute=10, status="cold"), entry=late)) == ["inserted"]
    assert [s.get("entry") for s in history(graph, DEVICE, "d1")] == [None, late, None]


def test_replay_of_old_rows_is_unchanged_not_a_failure(graph):
    sequence = [
        row(minute=0, room="r1"),
        row(minute=7, room="r1"),
        row(minute=20, room="r2", teams=["red", "blue"]),
        row(minute=30, room="r2", teams=["blue"], status="hot"),
    ]
    write(graph, *sequence)
    before = (shape(graph), windows(graph, "USED_BY"))
    assert write(graph, *sequence) == ["unchanged"] * 4
    assert write(graph, *reversed(sequence)) == ["unchanged"] * 4
    assert (shape(graph), windows(graph, "USED_BY")) == before and failures(graph) == []


def test_database_error_is_stored_and_reported(graph, monkeypatch):
    with monkeypatch.context() as patch:
        broken = "UNWIND $rows AS r RETURN r.key, no_such_function()"
        patch.setattr("lighthouse.write.batches._remember_query", lambda kind: broken)
        receipts = remember(graph, DEVICE, [row(key="d8"), row(key="d9")], by="test")
    assert [r["status"] for r in receipts] == ["failed", "failed"]
    assert all("no_such_function" in r["reason"] for r in receipts)
    assert count(graph, "(d:Device)") == 0
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("failed", "Device", None) and "keys=['d8', 'd9']" in detail
    assert write(graph, row(key="d8"), row(key="d9")) == ["created", "created"]


def test_several_rows_for_one_entity_in_one_call(graph):
    # Rows of one query cannot see each other's writes. remember() must split them.
    statuses = write(graph, *(row(minute=m, level=m, room=f"r{m}") for m in range(5)))
    assert statuses == ["created"] + ["changed"] * 4
    assert [s["level"] for s in history(graph, DEVICE, "d1")] == list(range(5))
    assert [w[0] for w in windows(graph, "LOCATED_IN")] == [f"r{m}" for m in range(5)]
    check_invariants(graph)


def test_entities_that_share_new_targets_in_one_call(graph):
    statuses = write(graph, *(row(key=f"d{i}", room="r1", teams=["red", "blue"]) for i in range(5)))
    assert statuses == ["created"] * 5
    nodes, edges = shape(graph)
    assert nodes == {"Device": 5, "State": 5, "Room": 1, "Team": 2}
    assert edges == {"HAS_STATE": 5, "LOCATED_IN": 5, "USED_BY": 10}
    check_invariants(graph)


def test_receipts_keep_the_order_of_the_rows(graph):
    keys = ["e", "c", "i", "c", "a", "e", "e"]
    rows = [row(key=key, minute=n, level=n) for n, key in enumerate(keys)]
    receipts = remember(graph, DEVICE, rows, by="test")
    assert [r["key"] for r in receipts] == keys
    assert [r["status"] for r in receipts] == [
        "created",
        "created",
        "created",
        "changed",
        "created",
        "changed",
        "changed",
    ]


def test_more_rows_than_one_query_holds(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.write.batches.BATCH", 7)
    sent, real = [], graph.query
    graph.query = lambda query, params=None, **more: (
        (sent.append(len(params["rows"])) if params and "rows" in params else None)
        or real(query, params, **more)
    )
    try:
        assert write(graph, *(row(key=f"d{i}") for i in range(30))) == ["created"] * 30
    finally:
        del graph.query
    assert sent == [7, 7, 7, 7, 2]
    assert count(graph, "(:Device)-[:HAS_STATE]->(:State)") == 30
    check_invariants(graph)


def test_no_rows(graph):
    assert remember(graph, DEVICE, [], by="test") == []


def test_rows_from_a_generator(graph):
    receipts = remember(graph, DEVICE, (row(key=f"d{i}") for i in range(3)), by="test")
    assert [r["status"] for r in receipts] == ["created"] * 3


@pytest.mark.parametrize("by", [None, "", 7])
def test_write_without_a_writer_is_refused(graph, by):
    with pytest.raises(ValueError, match="by"):
        remember(graph, DEVICE, [row()], by=by)
    assert count(graph, "(n) WHERE NOT n:Stamp") == 0


def test_random_rows_in_random_batches_match_the_oracle(graph):
    rng = random.Random(41)
    feed, expected = random_timelines(rng, devices=12, snapshots=25)
    feed.sort(key=lambda item: item[0])  # the order a poller would see
    statuses = []
    while feed:
        size = rng.randint(1, 40)
        batch, feed = feed[:size], feed[size:]
        statuses += write(graph, *(as_row(*item) for item in batch))
    assert set(statuses) <= {"created", "changed", "unchanged"}
    stored = sum(1 for status in statuses if status != "unchanged")
    assert stored == sum(len(versions) for versions in expected.values())
    assert_matches_the_oracle(graph, expected)
    check_invariants(graph)
    assert failures(graph) == []
    # Time travel agrees with the oracle at every minute a State starts, and just before.
    for key, versions in expected.items():
        for index, (minute, v) in enumerate(versions):
            assert as_of(graph, DEVICE, key, when(minute))["level"] == v["level"]
            assert related(graph, DEVICE, key, "USED_BY", when(minute)) == sorted(v["teams"])
            if index:
                before = versions[index - 1][1]
                assert as_of(graph, DEVICE, key, when(minute - 1))["level"] == before["level"]
                teams = related(graph, DEVICE, key, "USED_BY", when(minute - 1))
                assert teams == sorted(before["teams"])
