"""The free-text path: an extractor that the test passes in reads entries, and what it finds
is written by the write rule, with the entry as its evidence."""

import re

import pytest
from devices import DEVICE, failures, when

from lighthouse import Kind, ensure_schema, extract, history, open_episode, record, related

SEEN = re.compile(r"(d\d+) is (\w+) in (r\d+)")


def extractor(entry) -> list[dict]:
    """Finds 'd1 is hot in r2' in what an agent saw."""
    return [
        {"key": key, "values": {"status": status}, "relations": {"LOCATED_IN": room}}
        for key, status, room in SEEN.findall(entry.get("saw", ""))
    ]


def note(graph, saw, minute=0, kind="observation", **values) -> str:
    open_episode(graph, "watch", "eye")
    return record(graph, "watch", kind, "eye", {"saw": saw, **values}, at=when(minute))["id"]


def test_rows_found_in_entries_are_written_with_their_evidence(graph):
    first = note(graph, "d1 is ok in r1, and d2 is hot in r2", minute=0)
    second = note(graph, "d1 is hot in r3", minute=10)
    assert extract(graph, DEVICE, extractor, "reader") == {
        "read": 2,
        "rows": {"created": 2, "changed": 1},
        "waiting": 0,
    }
    states = history(graph, DEVICE, "d1")
    assert [(s["status"], s["valid_from"], s["entry"]) for s in states] == [
        ("ok", when(0), first),  # true from the time of the entry
        ("hot", when(10), second),
    ]
    assert related(graph, DEVICE, "d1", "LOCATED_IN") == ["r3"]
    marks = graph.ro_query(
        "MATCH (n:Entry)-[r:READ_BY]->(a:Agent) RETURN n.id, r.kind, r.rows, a.id ORDER BY n.id"
    ).result_set
    assert marks == [[first, "Device", 2, "reader"], [second, "Device", 1, "reader"]]
    assert extract(graph, DEVICE, extractor, "reader") == {"read": 0, "rows": {}, "waiting": 0}


def test_extractor_gets_the_entry_and_may_give_the_time(graph):
    seen = []

    def at_noon(entry):
        seen.append(entry)
        return [{"key": "d1", "t": when(30), "values": {"status": "ok"}}]

    entry = note(graph, "anything", minute=40, weather="dry")
    extract(graph, DEVICE, at_noon, "reader")
    assert seen[0]["id"] == entry and seen[0]["weather"] == "dry" and "words" not in seen[0]
    assert history(graph, DEVICE, "d1")[0]["valid_from"] == when(30)


def test_evidence_is_the_entry_that_was_read_whatever_the_extractor_says(graph):
    other = note(graph, "nothing here")
    entry = note(graph, "d1 is hot in r1", minute=1)

    def points_elsewhere(found):
        return [dict(row, entry=other) for row in extractor(found)]

    extract(graph, DEVICE, points_elsewhere, "reader")
    assert history(graph, DEVICE, "d1")[0]["entry"] == entry


def test_only_the_types_asked_for_are_read_and_the_rest_waits(graph):
    note(graph, "d1 is ok in r1", kind="observation")
    note(graph, "d2 is hot in r2", minute=1, kind="forecast")
    found = extract(graph, DEVICE, extractor, "reader", types=["observation"])
    assert (found["read"], found["waiting"]) == (1, 0)
    assert history(graph, DEVICE, "d2") == []
    assert extract(graph, DEVICE, extractor, "reader")["read"] == 1  # the forecast, now


def test_reading_stops_at_the_limit_and_says_what_waits(graph):
    for minute in range(3):
        note(graph, f"d{minute} is ok in r1", minute=minute)
    assert extract(graph, DEVICE, extractor, "reader", limit=2) == {
        "read": 2,
        "rows": {"created": 2},
        "waiting": 1,
    }
    assert [k for k in ("d0", "d1", "d2") if history(graph, DEVICE, k)] == ["d0", "d1"]  # oldest


def test_entry_is_read_once_for_each_kind(graph):
    sensor = Kind("Sensor", key="code")
    ensure_schema(graph, [DEVICE, sensor])
    note(graph, "d1 is ok in r1")
    extract(graph, DEVICE, extractor, "reader")
    assert extract(graph, sensor, lambda entry: [{"key": "s1"}], "reader")["read"] == 1
    assert history(graph, sensor, "s1")[0]["valid_from"] == when(0)


def test_entry_without_text_is_never_read(graph):
    open_episode(graph, "watch", "eye")
    record(graph, "watch", "observation", "eye", {"count": 3})
    called = []
    assert extract(graph, DEVICE, lambda e: called.append(e) or [], "reader")["read"] == 0
    assert called == []


def test_rows_that_cannot_be_stored_are_refused_and_the_entry_is_read(graph):
    note(graph, "anything")
    found = extract(graph, DEVICE, lambda entry: [{"key": "d1", "values": [1]}, "row"], "reader")
    assert found == {"read": 1, "rows": {"invalid": 2}, "waiting": 0}
    assert [reason for reason, *_ in failures(graph)] == ["invalid", "invalid"]


def test_extractor_that_raises_stops_and_its_entry_waits(graph):
    note(graph, "d1 is ok in r1", minute=0)
    note(graph, "broken", minute=1)

    def fails_on_broken(entry):
        if entry["saw"] == "broken":
            raise RuntimeError("the model is down")
        return extractor(entry)

    with pytest.raises(RuntimeError, match="model is down"):
        extract(graph, DEVICE, fails_on_broken, "reader")
    assert history(graph, DEVICE, "d1")  # the entry before it was done
    assert extract(graph, DEVICE, extractor, "reader")["read"] == 1  # the broken one waited


@pytest.mark.parametrize("answer", [None, "rows", {"key": "d1"}, [{"key": "d1"}] * 1_001])
def test_extractor_that_gives_no_list_of_rows_is_refused(graph, answer):
    note(graph, "anything")
    with pytest.raises(TypeError, match="list"):
        extract(graph, DEVICE, lambda entry: answer, "reader")
    assert history(graph, DEVICE, "d1") == []


def test_what_extract_is_given_is_checked(graph):
    with pytest.raises(TypeError, match="extractor"):
        extract(graph, DEVICE, "not a function", "reader")
    with pytest.raises(ValueError, match="types"):
        extract(graph, DEVICE, extractor, "reader", types="observation")
    with pytest.raises(ValueError, match="types"):
        extract(graph, DEVICE, extractor, "reader", types=[""])
    with pytest.raises(ValueError, match="limit"):
        extract(graph, DEVICE, extractor, "reader", limit=0)
    with pytest.raises(ValueError):
        extract(graph, DEVICE, extractor, "")
