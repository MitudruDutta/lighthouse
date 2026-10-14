"""Declaring kinds: names are checked once, because they go into query text."""

import pytest
from devices import DEVICE, PERSON, ROOM

from lighthouse import Kind


@pytest.mark.parametrize(
    "arguments",
    [
        {"label": "Bad Label"},
        {"label": "x`y"},
        {"label": ""},
        {"label": "State"},
        {"label": "WriteFailure"},
        {"label": "Task"},
        {"label": "Agent"},
        {"label": "Episode"},
        {"label": "Entry"},
        {"label": "Handoff"},
        {"label": "Lesson"},
        {"label": "Playbook"},
        {"label": "Step"},
        {"label": "Trigger"},
        {"label": "Entity"},
        {"label": "Stamp"},
        {"label": "Session"},
        {"label": "Message"},
        {"label": "Reference"},
        {"label": "Device", "times": "last_seen"},
        {"label": "Device", "text": "title"},
        {"label": "Device", "text": ("note",), "dimensions": -1},
        {"label": "Device", "text": ("note",), "dimensions": 4097},
        {"label": "Device", "text": ("note",), "dimensions": 8.0},
        {"label": "Device", "text": ("note",), "dimensions": True},
        {"label": "Device", "dimensions": 8},
        {"label": "DeviceVector"},
        {"label": "Vector"},
        {"label": "Device", "text": ("bad name",)},
        {"label": "Device", "text": ("valid_to",)},
        {"label": "Device", "text": ("words",)},
        {"label": "Device", "times": ("seen",), "text": ("seen",)},
        {"label": "Device", "relations": ["Room"]},
        {"label": "Device", "key": "serial number"},
        {"label": "Device", "key": "valid_from"},
        {"label": "Device", "times": ("valid_to",)},
        {"label": "Device", "times": ("seen at",)},
        {"label": "Device", "key": "seen", "times": ("seen",)},
        {"label": "Device", "relations": {"IN ROOM": ROOM}},
        {"label": "Device", "relations": {"HAS_STATE": ROOM}},
        {"label": "Device", "relations": {"NEXT": ROOM}},
        {"label": "Device", "relations": {"IN": "Room"}},
        {"label": 7},
    ],
)
def test_kind_with_a_name_that_is_unsafe_or_reserved_is_rejected(arguments):
    with pytest.raises((TypeError, ValueError)):
        Kind(**arguments)


def test_relation_to_self_points_at_the_kind_itself():
    assert PERSON.relations["KNOWS"] is PERSON


def test_kind_cannot_change_after_it_is_made():
    # A name added later would reach a query without the check.
    with pytest.raises(TypeError):
        DEVICE.relations["BAD NAME"] = ROOM
    with pytest.raises(AttributeError):
        DEVICE.label = "Other"
    given = {"IN": ROOM}
    kind = Kind("Shelf", times=["checked"], relations=given)
    given["BAD NAME"] = ROOM
    assert kind.times == ("checked",) and set(kind.relations) == {"IN"}
