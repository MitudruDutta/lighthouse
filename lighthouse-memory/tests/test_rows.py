"""Rows: what a caller gives is checked before anything is written."""

import pytest
from devices import (
    DEVICE,
    count,
    failures,
    row,
    when,
)

from lighthouse import (
    remember,
)

INVALID_ROWS = {
    "not a map": "a device",
    "no key": {"t": when(0)},
    "empty key": {"key": "", "t": when(0)},
    "key of a wrong type": {"key": 1.5, "t": when(0)},
    "boolean key": {"key": True, "t": when(0)},
    "no time": {"key": "d2"},
    "text that is not a time": {"key": "d2", "t": "yesterday"},
    "unknown field": {"key": "d2", "t": when(0), "extra": 1},
    "values not a map": {"key": "d2", "t": when(0), "values": ["a"]},
    "map as a value": {"key": "d2", "t": when(0), "values": {"a": {"b": 1}}},
    "list in a list": {"key": "d2", "t": when(0), "values": {"a": [[1]]}},
    "null in a list": {"key": "d2", "t": when(0), "values": {"a": [None]}},
    "not a number": {"key": "d2", "t": when(0), "values": {"a": float("nan")}},
    "infinity": {"key": "d2", "t": when(0), "values": {"a": float("inf")}},
    "integer too large": {"key": "d2", "t": when(0), "values": {"a": 2**63}},
    "unsafe value name": {"key": "d2", "t": when(0), "values": {"a b": 1}},
    "value name with a backtick": {"key": "d2", "t": when(0), "values": {"a`b": 1}},
    "value name of the engine": {"key": "d2", "t": when(0), "values": {"valid_to": 1}},
    "fingerprint as a value": {"key": "d2", "t": when(0), "values": {"fp": "x"}},
    "time of a repeat as a value": {"key": "d2", "t": when(0), "values": {"seen_last": 1}},
    "the key as a value": {"key": "d2", "t": when(0), "values": {"serial": "other"}},
    "declared time that is not a time": {"key": "d2", "t": when(0), "values": {"last_seen": 5}},
    "relation that is not declared": {"key": "d2", "t": when(0), "relations": {"OWNS": "x"}},
    "relations not a map": {"key": "d2", "t": when(0), "relations": ["r1"]},
    "values of an empty wrong type": {"key": "d2", "t": when(0), "values": 0},
    "relations of an empty wrong type": {"key": "d2", "t": when(0), "relations": ""},
    "relation key of a wrong type": {"key": "d2", "t": when(0), "relations": {"USED_BY": [1.5]}},
    "empty relation key": {"key": "d2", "t": when(0), "relations": {"USED_BY": [""]}},
    "entry that is not an id": {"key": "d2", "t": when(0), "entry": 5},
    "entry that is empty": {"key": "d2", "t": when(0), "entry": ""},
    "entry as a value": {"key": "d2", "t": when(0), "values": {"entry": "look/1"}},
    "words as a value": {"key": "d2", "t": when(0), "values": {"words": "x"}},
}


@pytest.mark.parametrize("name", INVALID_ROWS)
def test_invalid_row_is_stored_as_a_failure_and_does_not_block_valid_rows(graph, name):
    receipts = remember(graph, DEVICE, [row(key="d1"), INVALID_ROWS[name], row(key="d3")], by="t")
    assert [r["status"] for r in receipts] == ["created", "invalid", "created"]
    assert receipts[1]["reason"]
    if name == "no time":
        assert "is missing" in receipts[1]["reason"]
    assert count(graph, "(d:Device)") == 2
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, detail) == ("invalid", "Device", receipts[1]["reason"])
    assert key == receipts[1]["key"]
