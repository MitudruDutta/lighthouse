"""Late rows: a row that comes late goes into the history at its time, or is refused and
stored, never placed wrong."""

import random
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import connect
from devices import (
    DEVICE,
    check_invariants,
    count,
    failures,
    row,
    when,
    windows,
    write,
)
from oracle import as_row, assert_matches_the_oracle, history_of, random_timelines

from lighthouse import (
    as_of,
    history,
    related,
    remember,
)
from lighthouse.write.late import insert
from lighthouse.write.rows import checked


def stamp(graph) -> str:
    return graph.ro_query("MATCH (s:Stamp) RETURN s.id").result_set[0][0]


def test_late_row_is_put_into_the_history_at_its_time(graph):
    write(graph, row(minute=0, status="ok"), row(minute=20, status="hot"))
    first = stamp(graph)
    assert write(graph, row(minute=10, status="cold", room="r9")) == ["inserted"]
    assert [
        (s["valid_from"], s.get("valid_to"), s["status"]) for s in history(graph, DEVICE, "d1")
    ] == [
        (when(0), when(10), "ok"),
        (when(10), when(20), "cold"),
        (when(20), None, "hot"),
    ]
    # r1 held before and after the row; the row says r9 for that stretch.
    assert windows(graph, "LOCATED_IN") == [
        ("r1", when(0), when(10)),
        ("r9", when(10), when(20)),
        ("r1", when(20), None),
    ]
    assert windows(graph, "USED_BY") == [("red", when(0), None)]  # it said red all along
    assert as_of(graph, DEVICE, "d1", when(15))["status"] == "cold"
    assert related(graph, DEVICE, "d1", "LOCATED_IN", when(15)) == ["r9"]
    assert related(graph, DEVICE, "d1", "LOCATED_IN") == ["r1"]
    assert count(graph, "(d:Device {serial: 'd1', status: 'hot'})") == 1  # now is as it was
    assert count(graph, "(r:Room:Entity {code: 'r9'})") == 1
    assert failures(graph) == [] and stamp(graph) != first  # a NEXT edge was replaced
    check_invariants(graph)


def test_late_row_from_before_the_first_state_starts_the_history_earlier(graph):
    write(graph, row(minute=10))
    first = stamp(graph)
    assert write(graph, row(minute=5, status="other", room="r2")) == ["inserted"]
    assert [
        (s["valid_from"], s.get("valid_to"), s["status"]) for s in history(graph, DEVICE, "d1")
    ] == [
        (when(5), when(10), "other"),
        (when(10), None, "ok"),
    ]
    assert windows(graph, "LOCATED_IN") == [("r2", when(5), when(10)), ("r1", when(10), None)]
    assert windows(graph, "USED_BY") == [("red", when(5), None)]  # the same team: one stay
    assert stamp(graph) == first  # nothing was deleted
    check_invariants(graph)


def test_late_row_that_says_what_the_next_state_says_makes_it_start_earlier(graph):
    write(graph, row(minute=0, room="r1"), row(minute=10, room="r2"), row(minute=20, room="r3"))
    first = stamp(graph)
    assert write(graph, row(minute=15, room="r3")) == ["inserted"]
    assert [(s["valid_from"], s.get("valid_to")) for s in history(graph, DEVICE, "d1")] == [
        (when(0), when(10)),
        (when(10), when(15)),
        (when(15), None),
    ]
    assert windows(graph, "LOCATED_IN") == [
        ("r1", when(0), when(10)),
        ("r2", when(10), when(15)),
        ("r3", when(15), None),
    ]
    assert write(graph, row(minute=2, room="r1")) == ["unchanged"]  # already true then
    assert stamp(graph) == first and failures(graph) == []
    check_invariants(graph)


def test_late_row_keeps_its_times_and_writer(graph):
    write(graph, row(minute=0), row(minute=30, status="hot"))
    receipts = remember(
        graph, DEVICE, [row(minute=10, status="cold", last_seen=when(9))], by="late"
    )
    assert [r["status"] for r in receipts] == ["inserted"]
    late = history(graph, DEVICE, "d1")[1]
    assert (late["status"], late["last_seen"], late["by"]) == ("cold", when(9), "late")
    edges = graph.ro_query(
        "MATCH (:Device)-[o:LOCATED_IN]->() RETURN o.valid_from, o.valid_to, o.by ORDER BY o.valid_from"
    ).result_set
    assert edges == [[when(0), None, "test"]]  # the room did not change: its edge is untouched


def test_edges_that_a_late_row_cuts_and_adds_name_their_writers(graph):
    write(graph, row(minute=0), row(minute=30, status="hot"))
    (first,) = graph.ro_query("MATCH (:Device)-[o:LOCATED_IN]->() RETURN o.recorded_at").result_set
    assert (
        remember(graph, DEVICE, [row(minute=10, room="r2")], by="late")[0]["status"] == "inserted"
    )
    edges = graph.ro_query(
        "MATCH (:Device)-[o:LOCATED_IN]->(r) "
        "RETURN r.code, o.valid_from, o.valid_to, o.by, o.recorded_at ORDER BY o.valid_from"
    ).result_set
    assert [edge[:4] for edge in edges] == [
        ["r1", when(0), when(10), "test"],
        ["r2", when(10), when(30), "late"],
        ["r1", when(30), None, "test"],  # what held before the late row goes on after it
    ]
    assert edges[2][4] == first[0]  # and keeps the time it was recorded


def test_other_content_at_the_start_of_the_current_state_is_a_conflict(graph):
    write(graph, row(minute=0))
    assert write(graph, row(minute=0, status="other")) == ["conflict"]
    assert len(history(graph, DEVICE, "d1")) == 1


def test_other_content_at_the_same_second_is_a_conflict(graph):
    write(graph, row(minute=0), row(minute=20))
    assert write(graph, row(minute=0, status="other")) == ["conflict"]
    assert write(graph, row(minute=0, room="other")) == ["conflict"]
    assert write(graph, row(minute=20, status="other")) == ["conflict"]
    assert len(history(graph, DEVICE, "d1")) == 1 and count(graph, "(r:Room {code: 'other'})") == 0
    found = failures(graph)
    assert [(reason, kind, key) for reason, kind, key, _ in found] == [
        ("conflict", "Device", "d1")
    ] * 3
    assert any('"status": "other"' in detail for *_, detail in found)
    check_invariants(graph)


def test_late_row_that_the_database_refuses_is_stored_as_a_failure(graph, monkeypatch):
    write(graph, row(minute=0), row(minute=20, status="hot"))
    with monkeypatch.context() as patch:
        patch.setattr(
            "lighthouse.write.late._insert_query", lambda kind: "RETURN no_such_function()"
        )
        (receipt,) = remember(graph, DEVICE, [row(minute=10, status="cold")], by="test")
    assert receipt["status"] == "failed" and "no_such_function" in receipt["reason"]
    ((reason, _, key, detail),) = failures(graph)
    assert (reason, key) == ("failed", None) and "keys=['d1']" in detail
    assert len(history(graph, DEVICE, "d1")) == 2


def test_late_row_after_a_repeat_is_refused_and_never_placed_wrong(graph):
    write(graph, row(minute=0, room="r1"), row(minute=30, room="r1"))  # 30 repeats 0
    first = history(graph, DEVICE, "d1")
    assert first[0]["seen_last"] == when(30)
    # Where would r2 from minute 10 end? Before 30, when r1 was seen again, but when
    # exactly is not kept. So the row is refused, and kept as a failure.
    assert write(graph, row(minute=10, room="r2")) == ["stale"]
    assert write(graph, row(minute=30, room="r9")) == ["conflict"]  # r1 was seen then
    assert history(graph, DEVICE, "d1") == first
    assert [reason for reason, *_ in failures(graph)] == ["conflict", "stale"]
    assert write(graph, row(minute=40, room="r2")) == ["changed"]  # after the repeat: fine
    assert write(graph, row(minute=35, room="r3")) == ["inserted"]
    check_invariants(graph)


def test_late_repeat_of_a_closed_state_is_kept(graph):
    write(graph, row(minute=0, room="r1"), row(minute=20, room="r2"))
    assert write(graph, row(minute=10, room="r1")) == ["unchanged"]
    assert history(graph, DEVICE, "d1")[0]["seen_last"] == when(10)
    assert write(graph, row(minute=5, room="r1")) == ["unchanged"]
    assert history(graph, DEVICE, "d1")[0]["seen_last"] == when(10)  # the last one stays
    assert write(graph, row(minute=7, room="r3")) == ["stale"]
    assert write(graph, row(minute=15, room="r3")) == ["inserted"]


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_rows_in_any_order_give_the_history_of_their_times(graph, seed):
    """Whatever order rows come in, the history is the one that the rows that were not
    refused give in the order of their times."""
    rng = random.Random(seed)
    feed, _ = random_timelines(rng, devices=10, snapshots=20)
    rng.shuffle(feed)  # late, early, and again, in any order
    statuses = []
    order = list(feed)
    while feed:
        size = rng.randint(1, 30)
        batch, feed = feed[:size], feed[size:]
        statuses += write(graph, *(as_row(*item) for item in batch))
    kept = [
        item
        for item, status in zip(order, statuses, strict=True)
        if status not in ("stale", "conflict")
    ]
    assert set(statuses) <= {"created", "changed", "inserted", "unchanged", "stale", "conflict"}
    assert statuses.count("inserted") > 10 and len(kept) > len(order) * 0.7
    expected = history_of(kept)
    assert_matches_the_oracle(graph, expected)
    check_invariants(graph)
    refused = statuses.count("stale") + statuses.count("conflict")
    assert len(failures(graph)) == refused
    for key, versions in expected.items():
        for minute, v in versions:
            assert as_of(graph, DEVICE, key, when(minute))["level"] == v["level"]
            assert related(graph, DEVICE, key, "USED_BY", when(minute)) == sorted(v["teams"])


def test_rows_that_change_each_time_are_rarely_refused_in_any_order(graph):
    """Rows that each say something new, as a source of changes sends them. One is refused
    only when a row with the same content as an earlier one came first: then where the
    State between them ends is not known."""
    rng = random.Random(11)
    _, expected = random_timelines(rng, devices=8, snapshots=25)
    changes = [
        (minute, key, dict(v, teams=tuple(v["teams"])))
        for key, versions in expected.items()
        for minute, v in versions
    ]
    rng.shuffle(changes)
    statuses = write(graph, *(as_row(*item) for item in changes))
    kept = [item for item, status in zip(changes, statuses, strict=True) if status != "stale"]
    assert set(statuses) <= {"created", "changed", "inserted", "unchanged", "stale"}
    assert len(kept) > len(changes) * 0.8 and "inserted" in statuses
    assert_matches_the_oracle(graph, history_of(kept))
    check_invariants(graph)
    assert len(failures(graph)) == statuses.count("stale")


def test_late_row_that_repeats_the_next_state_keeps_its_old_start_as_a_repeat(graph):
    write(graph, row(minute=60, status="a"))  # this came first
    assert write(graph, row(minute=10, status="a")) == ["inserted"]  # the same, earlier
    (state,) = history(graph, DEVICE, "d1")
    assert (state["valid_from"], state["seen_last"]) == (when(10), when(60))
    # Between 10 and 60 a row said "a" again at 60: a row from 20 cannot be placed.
    assert write(graph, row(minute=20, status="b")) == ["stale"]


def test_late_row_that_repeats_a_state_seen_again_keeps_the_last_repeat(graph):
    write(graph, row(minute=0, status="x"), row(minute=60, status="a"), row(minute=90, status="a"))
    assert write(graph, row(minute=10, status="a")) == ["inserted"]
    states = history(graph, DEVICE, "d1")
    assert [(s["valid_from"], s.get("seen_last")) for s in states] == [
        (when(0), None),
        (when(10), when(90)),
    ]


def test_late_row_query_decides_again_from_what_it_finds(graph):
    """Late rows go to a query of their own after their batch. Another writer may write in
    between, so that query decides again, whatever the batch query said."""
    write(graph, row(minute=10, status="a"), row(minute=60, status="b"))

    def late(minute, status):
        rows = [checked(DEVICE, row(minute=minute, status=status))]
        return insert(graph, DEVICE, rows, "x")[0]["status"]

    assert late(30, "a") == "unchanged"  # what holds at 30
    assert history(graph, DEVICE, "d1")[0]["seen_last"] == when(30)
    assert late(10, "a") == "unchanged"  # what starts at 10
    assert late(10, "c") == "conflict"
    assert late(70, "c") == "stale"  # no State after it: this query never adds a current one
    assert len(history(graph, DEVICE, "d1")) == 2
    check_invariants(graph)


def test_concurrent_writers_of_the_same_rows_keep_one_history(graph):
    # Four writers replay the same rows at once, each on its own connection. Without an
    # atomic "read current State, add next State", two would append the same version.
    rng = random.Random(7)
    feed, expected = random_timelines(rng, devices=6, snapshots=20)
    feed.sort(key=lambda item: item[0])
    statuses = []

    def writer(order):
        own = connect().select_graph(graph.name)
        for item in order:
            statuses.extend(write(own, as_row(*item)))

    # Two writers in time order, and two in orders of their own.
    orders = [feed, feed, rng.sample(feed, len(feed)), rng.sample(feed, len(feed))]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in [pool.submit(writer, order) for order in orders]:
            future.result()  # raises what the writer raised
    assert set(statuses) <= {"created", "changed", "inserted", "unchanged"}
    assert_matches_the_oracle(graph, expected)
    check_invariants(graph)
    assert failures(graph) == []
