"""Causal blast radius and entry invalidation."""

import pytest
from devices import DEVICE, ROOM, failures, row, when, write

from lighthouse import (
    accept,
    close_episode,
    hand_off,
    impact_of_entry,
    impact_of_state,
    invalidate_entry,
    learn,
    open_episode,
    record,
    remember,
    write_playbook,
)


@pytest.fixture
def causal_graph(graph):
    """A graph where a late row between minute 5 and 20 invalidates an observation,
    a downstream forecast, a derived state, a waiting handoff, a lesson, and a playbook.
    """
    write(graph, row(key="d1", minute=0, status="ok", room="r1"))
    write(graph, row(key="d1", minute=20, status="hot", room="r2"))
    write(graph, row(key="d2", minute=0, status="ok", room="r1"))

    open_episode(graph, "ep1", by="watcher", about=[(DEVICE, "d1")], at=when(8))
    obs = record(
        graph,
        "ep1",
        "observation",
        by="watcher",
        values={"saw": "nominal"},
        cites=[(DEVICE, "d1")],
        at=when(10),
    )["id"]
    fc = record(
        graph,
        "ep1",
        "forecast",
        by="forecaster",
        values={"fails": False},
        cites=[obs],
        at=when(12),
    )["id"]
    close_episode(graph, "ep1", by="reviewer", outcome={"ok": True}, cites=[fc], at=when(15))

    for n in (2, 3):
        open_episode(graph, f"ep{n}", by="watcher", about=[(DEVICE, "d1")], at=when(20 + n))
        close_episode(graph, f"ep{n}", by="reviewer", outcome={"ok": True}, at=when(25 + n))

    # d2 state derived from ep1/2
    remember(
        graph,
        DEVICE,
        [row(key="d2", minute=14, status="synced") | {"entry": fc}],
        by="forecaster",
    )

    # Waiting handoff pointing at ep1/2, and accepted handoff that should be ignored
    hand_off(graph, "h_wait", by="forecaster", to="desk", points_to=[fc], at=when(13))
    hand_off(graph, "h_done", by="forecaster", to="desk", points_to=[obs], at=when(13))
    accept(graph, "h_done", by="desk")

    learn(
        graph,
        "l1",
        by="reviewer",
        statement="d1 stays nominal in r1",
        supported_by=["ep1"],
        about=[(DEVICE, "d1")],
    )
    write_playbook(
        graph,
        "pb1",
        by="reviewer",
        trigger={"status": "ok"},
        steps=[{"do": "nothing"}],
        supported_by=["ep1", "ep2", "ep3"],
    )
    return graph


def test_impact_of_state_finds_full_forward_blast_radius(causal_graph):
    # Late row arrives at minute 5, rewriting [when(5), when(20))
    assert write(causal_graph, row(key="d1", minute=5, status="fault", room="r9")) == ["inserted"]
    impact = impact_of_state(causal_graph, DEVICE, "d1", when(5), when(20))
    assert impact["entity"] == ("Device", "d1")
    assert impact["direct_entries"] == ["ep1/1"]
    assert impact["downstream_entries"] == ["ep1/2", "ep1/3"]
    assert impact["episodes"] == ["ep1"]
    assert impact["handoffs"] == ["h_wait"]
    assert impact["derived_states"] == [
        {"label": "Device", "valid_from": when(14), "from_entry": "ep1/2"}
    ]
    assert impact["lessons"] == [{"id": "l1", "support": 1, "tainted_support": 1, "at_risk": True}]
    assert impact["playbooks"] == [
        {
            "id": "pb1#1",
            "name": "pb1",
            "version": 1,
            "support": 3,
            "tainted_support": 1,
            "at_risk": True,
        }
    ]


def test_impact_of_state_with_no_citations_in_window_is_empty(causal_graph):
    impact = impact_of_state(causal_graph, DEVICE, "d1", when(0), when(5))
    assert impact["direct_entries"] == []
    assert impact["downstream_entries"] == []
    assert impact["lessons"] == []
    assert impact["playbooks"] == []


def test_invalidate_entry_marks_retracted_and_returns_impact(causal_graph):
    receipt = invalidate_entry(
        causal_graph, "ep1/1", by="auditor", reason="sensor was stuck", at=when(30)
    )
    assert receipt["id"] == "ep1/1" and receipt["status"] == "invalidated"
    impact = receipt["impact"]
    assert impact["invalidated"] is True
    assert impact["downstream_entries"] == ["ep1/2", "ep1/3"]
    assert impact["handoffs"] == ["h_wait"]
    assert impact["lessons"][0]["at_risk"] is True
    assert impact["playbooks"][0]["at_risk"] is True

    # Calling again is idempotent
    again = invalidate_entry(causal_graph, "ep1/1", by="other", reason="duplicate", at=when(35))
    assert again == {"id": "ep1/1", "status": "exists"}


def test_impact_of_unknown_entry_is_none(causal_graph):
    assert impact_of_entry(causal_graph, "nope/1") is None


def test_invalid_or_unknown_invalidation_is_refused_and_stored(causal_graph):
    unknown = invalidate_entry(causal_graph, "nope/1", by="auditor", reason="bad")
    assert unknown["status"] == "unknown"

    bad_reason = invalidate_entry(causal_graph, "ep1/1", by="auditor", reason="   ")
    assert bad_reason["status"] == "invalid"

    future = invalidate_entry(
        causal_graph,
        "ep1/1",
        by="auditor",
        reason="bad",
        at="2999-01-01T00:00:00Z",
    )
    assert future["status"] == "invalid"
    assert [f[0] for f in failures(causal_graph)] == ["invalid", "invalid", "unknown"]


def test_impact_validation_rejects_bad_arguments(causal_graph):
    with pytest.raises(TypeError, match="Kind"):
        impact_of_state(causal_graph, "Device", "d1", when(0), when(5))
    with pytest.raises(ValueError, match="key"):
        impact_of_state(causal_graph, DEVICE, "", when(0), when(5))
    with pytest.raises(ValueError, match="earlier"):
        impact_of_state(causal_graph, DEVICE, "d1", when(10), when(5))
    with pytest.raises(ValueError, match="since"):
        impact_of_state(causal_graph, DEVICE, "d1", None, when(5))
    with pytest.raises(ValueError, match="until"):
        impact_of_state(causal_graph, DEVICE, "d1", when(0), None)
    assert ROOM.label == "Room"
