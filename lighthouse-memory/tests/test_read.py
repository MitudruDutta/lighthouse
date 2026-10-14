"""Reads of what was true at any time."""

import pytest
from devices import DEVICE, row, when, write

from lighthouse import as_of, history, related


def test_as_of_and_related_answer_for_any_time(graph):
    write(graph, row(minute=0, room="r1", status="ok"), row(minute=20, room="r2", status="hot"))
    assert as_of(graph, DEVICE, "d1", when(-1)) is None
    assert as_of(graph, DEVICE, "d1", when(0))["status"] == "ok"
    assert as_of(graph, DEVICE, "d1", when(19))["status"] == "ok"
    assert (
        as_of(graph, DEVICE, "d1", when(20))["status"] == "hot"
    )  # a window starts at its first second
    assert as_of(graph, DEVICE, "d1", when(10_000))["status"] == "hot"
    assert as_of(graph, DEVICE, "missing", when(0)) is None
    assert related(graph, DEVICE, "d1", "LOCATED_IN", when(-1)) == []
    assert related(graph, DEVICE, "d1", "LOCATED_IN", when(0)) == ["r1"]
    assert related(graph, DEVICE, "d1", "LOCATED_IN", when(19)) == ["r1"]
    assert related(graph, DEVICE, "d1", "LOCATED_IN", when(20)) == ["r2"]
    assert related(graph, DEVICE, "d1", "LOCATED_IN") == ["r2"]
    assert related(graph, DEVICE, "missing", "LOCATED_IN") == []


def test_entity_that_is_not_known_has_no_history(graph):
    assert history(graph, DEVICE, "missing") == []


@pytest.mark.parametrize("when", [None, "", "  "])
def test_read_at_a_time_needs_the_time(graph, when):
    write(graph, row())
    with pytest.raises(ValueError, match="when"):
        as_of(graph, DEVICE, "d1", when)
    if when is not None:  # for related(), no time means now
        with pytest.raises(ValueError, match="when"):
            related(graph, DEVICE, "d1", "LOCATED_IN", when)


def test_relation_that_is_not_declared_cannot_be_read(graph):
    with pytest.raises(ValueError, match="no relation 'OWNS'"):
        related(graph, DEVICE, "d1", "OWNS")
