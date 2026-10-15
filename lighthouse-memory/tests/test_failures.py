"""Failures: a write that did not happen is stored, bounded, and can name its owner."""

from datetime import UTC, datetime, timedelta

from lighthouse import (
    record_failure,
)


def test_failure_record_is_stored(graph):
    record_failure(graph, "invalid", "Device", key=12, detail='text with "quotes" and \\')
    record_failure(graph, "failed")
    rows = graph.ro_query(
        "MATCH (f:WriteFailure) RETURN f.reason, f.kind, f.key, f.detail, f.at ORDER BY f.reason"
    ).result_set
    assert [r[:4] for r in rows] == [
        ["failed", None, None, None],
        ["invalid", "Device", 12, 'text with "quotes" and \\'],
    ]
    assert all(datetime.now(UTC) - r[4] < timedelta(seconds=5) for r in rows)


def test_failure_can_name_the_user_whose_content_it_holds(graph):
    record_failure(graph, "invalid", "Message", "main", "what was refused", owner="ann")
    record_failure(graph, "invalid", "Message", "main", "no owner")
    for hostile in ("", " ann", "a\x00b", "x" * 201, 7, ["ann"], {"a": 1}):
        record_failure(graph, "invalid", "Message", "main", "hostile owner", owner=hostile)
    found = graph.ro_query("MATCH (f:WriteFailure) RETURN f.owner, sum(f.times) ORDER BY f.owner")
    assert found.result_set == [["ann", 1], [None, 8]]


def test_the_same_refusal_again_is_counted_not_stored_again(graph):
    for _ in range(3):
        record_failure(graph, "invalid", "Device", "d1", "a bad row")
    record_failure(graph, "invalid", "Device", "d1", "another bad row")
    record_failure(graph, "invalid", "Device", "d2", "a bad row")
    found = graph.ro_query(
        "MATCH (f:WriteFailure) RETURN f.key, f.detail, f.times, f.last_at >= f.at "
        "ORDER BY f.key, f.detail"
    ).result_set
    assert found == [
        ["d1", "a bad row", 3, True],
        ["d1", "another bad row", 1, True],
        ["d2", "a bad row", 1, True],
    ]
