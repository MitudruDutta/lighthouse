"""The one time format."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from lighthouse import (
    now,
    stamp,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-12T11:50:11.000Z", "2026-10-12T11:50:11"),
        ("2026-10-12T11:50:11.943Z", "2026-10-12T11:50:11"),  # whole seconds, rounded down
        ("2026-10-12T11:50:11Z", "2026-10-12T11:50:11"),
        ("2026-10-12T14:50:11+03:00", "2026-10-12T11:50:11"),  # other offsets become UTC
        ("2026-10-12T11:50:11", "2026-10-12T11:50:11"),  # no offset is taken as UTC
        (" 2026-10-12T11:50:11Z ", "2026-10-12T11:50:11"),
        (datetime(2026, 10, 12, 11, 50, 11, 999999, tzinfo=UTC), "2026-10-12T11:50:11"),
        (
            datetime(2026, 10, 12, 14, 50, 11, tzinfo=timezone(timedelta(hours=3))),
            "2026-10-12T11:50:11",
        ),
        (datetime(2026, 10, 12, 11, 50, 11), "2026-10-12T11:50:11"),
        ("", None),
        ("  ", None),
        (None, None),
    ],
)
def test_stamp(value, expected):
    assert stamp(value) == expected


@pytest.mark.parametrize("value", ["yesterday", 1760000000, 3.5, ["2026-01-01"], {"t": 1}, True])
def test_stamp_rejects_what_is_not_a_time(value):
    with pytest.raises((TypeError, ValueError)):
        stamp(value)


def test_stamp_round_trips_through_the_database(graph):
    text = "2026-10-12T11:50:11"
    stored = graph.query("CREATE (n:T {at: localdatetime($t)}) RETURN n.at", {"t": text})
    assert stamp(stored.result_set[0][0]) == text
    assert abs(datetime.now(UTC) - datetime.fromisoformat(now() + "+00:00")) < timedelta(seconds=5)
