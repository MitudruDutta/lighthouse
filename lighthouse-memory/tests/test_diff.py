"""Temporal world diffing and zero-write counterfactual simulation."""

import pytest
from devices import DEVICE, row, shape, when, write

from lighthouse import close_episode, diff_between, open_episode, what_if, write_playbook


@pytest.fixture
def timeline_graph(graph):
    write(
        graph,
        row(key="d1", minute=0, status="ok", room="r1", teams=["red"]),
        row(key="d2", minute=0, status="ok", room="r1", teams=["blue"]),
    )
    write(
        graph,
        row(key="d1", minute=10, status="hot", room="r2", teams=["red"]),
        row(key="d3", minute=12, status="new", room="r2", teams=["green"]),
    )
    open_episode(graph, "ep1", by="watcher", about=[(DEVICE, "d1")], at=when(5))
    close_episode(graph, "ep1", by="reviewer", outcome={"ok": True}, at=when(15))
    for n in (2, 3):
        open_episode(graph, f"ep{n}", by="watcher", about=[(DEVICE, "d1")], at=when(n))
        close_episode(graph, f"ep{n}", by="reviewer", outcome={"ok": True}, at=when(n + 1))
    write_playbook(
        graph,
        "cool-device",
        by="reviewer",
        trigger={"status": "hot"},
        steps=[{"do": "check fan"}],
        supported_by=["ep1", "ep2", "ep3"],
    )
    return graph


def test_diff_between_captures_entities_values_relations_and_episodes(timeline_graph):
    delta = diff_between(timeline_graph, [DEVICE], when(1), when(20))
    assert delta["entities_added"] == [{"entity": ("Device", "d3"), "values": {"status": "new"}}]
    assert delta["values_changed"] == [
        {
            "entity": ("Device", "d1"),
            "before": {"status": "ok"},
            "after": {"status": "hot"},
            "changed_keys": ["status"],
        }
    ]
    assert {(r["from"], r["relation"], r["to"]) for r in delta["relations_opened"]} == {
        (("Device", "d1"), "LOCATED_IN", ("Room", "r2")),
        (("Device", "d3"), "LOCATED_IN", ("Room", "r2")),
        (("Device", "d3"), "USED_BY", ("Team", "green")),
    }
    assert [(r["from"], r["relation"], r["to"]) for r in delta["relations_closed"]] == [
        (("Device", "d1"), "LOCATED_IN", ("Room", "r1"))
    ]
    assert delta["episodes_opened"] == ["ep1", "ep2", "ep3"]
    assert delta["episodes_closed"] == ["ep1", "ep2", "ep3"]
    later = diff_between(timeline_graph, [DEVICE], when(4), when(20))
    # ep2 opened at 2 and closed at 3, ep3 opened at 3 and closed at 4: before the window.
    assert (later["episodes_opened"], later["episodes_closed"]) == (["ep1"], ["ep1"])


def test_what_if_simulates_topology_changes_without_mutating_graph(timeline_graph):
    before_shape = shape(timeline_graph)
    hypothetical = [
        (
            DEVICE,
            [
                {
                    "key": "d2",
                    "relations": {"LOCATED_IN": "r2", "USED_BY": ["red"]},
                },
                {
                    "key": "d9",
                    "relations": {"LOCATED_IN": "r2", "USED_BY": ["red"]},
                },
            ],
        )
    ]
    sim = what_if(
        timeline_graph,
        [DEVICE],
        hypothetical,
        at=when(20),
        situation={"status": "hot", "room": "r2"},
    )
    # Database was not modified at all
    assert shape(timeline_graph) == before_shape
    # Before: two disconnected components; after: merged into one component
    assert len(sim["groups_before"]) == 2
    assert len(sim["groups_after"]) == 1
    assert sim["rank_shifts"][0]["delta"] != 0.0
    assert [pb["id"] for pb in sim["playbooks"]] == ["cool-device#1"]


def test_diff_and_what_if_reject_invalid_inputs(timeline_graph):
    with pytest.raises(TypeError, match="Kind"):
        diff_between(timeline_graph, ["Device"], when(0), when(10))
    with pytest.raises(ValueError, match="at least one kind"):
        diff_between(timeline_graph, [], when(0), when(10))
    with pytest.raises(ValueError, match="not be later"):
        diff_between(timeline_graph, [DEVICE], when(10), when(5))
    with pytest.raises(TypeError, match="hypothetical_rows"):
        what_if(timeline_graph, [DEVICE], "bad")
    with pytest.raises(ValueError, match="hypothetical_rows"):
        what_if(timeline_graph, [DEVICE], [(DEVICE, ["not-a-dict"])])
