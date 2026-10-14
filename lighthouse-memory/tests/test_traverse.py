"""Recall by the graph: what points at a thing, and what shares the surroundings of a thing."""

import pytest
from devices import DEVICE, count, row, when, write

from lighthouse import pointing_at, related, similar


@pytest.fixture
def graph(graph):
    """Five devices. d1 moved from r1 to r9 at minute 10, and lost team blue then."""
    write(
        graph,
        row(key="d1", room="r1", teams=["red", "blue"]),
        row(key="d2", room="r1", teams=["red"]),
        row(key="d3", room="r1", teams=["green"]),
        row(key="d4", room="r2", teams=["blue", "red"]),
        row(key="d5", room="r3", teams=[]),
        row(key="d1", minute=10, room="r9", teams=["red"]),
    )
    return graph


# --- what points at a target ----------------------------------------------------------


def test_pointing_at_is_the_reverse_of_related(graph):
    assert pointing_at(graph, DEVICE, "LOCATED_IN", "r1") == ["d2", "d3"]
    assert pointing_at(graph, DEVICE, "USED_BY", "red") == ["d1", "d2", "d4"]
    assert pointing_at(graph, DEVICE, "USED_BY", "blue") == ["d4"]
    assert pointing_at(graph, DEVICE, "LOCATED_IN", "nowhere") == []
    for device in ("d1", "d2", "d3", "d4", "d5"):
        for room in related(graph, DEVICE, device, "LOCATED_IN"):
            assert device in pointing_at(graph, DEVICE, "LOCATED_IN", room)


def test_pointing_at_answers_for_any_time(graph):
    assert pointing_at(graph, DEVICE, "LOCATED_IN", "r1", when(-1)) == []
    assert pointing_at(graph, DEVICE, "LOCATED_IN", "r1", when(0)) == ["d1", "d2", "d3"]
    assert pointing_at(graph, DEVICE, "LOCATED_IN", "r1", when(9)) == ["d1", "d2", "d3"]
    assert pointing_at(graph, DEVICE, "LOCATED_IN", "r1", when(10)) == ["d2", "d3"]
    assert pointing_at(graph, DEVICE, "LOCATED_IN", "r9", when(10)) == ["d1"]
    assert pointing_at(graph, DEVICE, "USED_BY", "blue", when(5)) == ["d1", "d4"]


def test_entity_that_came_back_is_listed_once(graph):
    write(graph, row(key="d1", minute=20, room="r1", teams=["red"]))  # back in r1: a second edge
    assert count(graph, "(:Device {serial: 'd1'})-[o:LOCATED_IN]->(:Room {code: 'r1'})", "o") == 2
    assert pointing_at(graph, DEVICE, "LOCATED_IN", "r1") == ["d1", "d2", "d3"]


def test_long_list_of_what_points_at_a_target_is_complete(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.read.PAGE", 3)
    write(graph, *(row(key=f"x{n}", room="hall") for n in range(8)))
    assert pointing_at(graph, DEVICE, "LOCATED_IN", "hall") == [f"x{n}" for n in range(8)]


# --- what is like an entity -----------------------------------------------------------


def test_similar_ranks_by_what_is_shared_and_says_what_that_is(graph):
    # d4 now: room r2, teams blue and red.
    assert similar(graph, DEVICE, "d4") == [
        {"key": "d1", "shared": 2, "through": [("USED_BY", "blue"), ("USED_BY", "red")]},
        {"key": "d2", "shared": 1, "through": [("USED_BY", "red")]},
    ]


def test_similar_compares_what_is_true_now_with_what_was_ever_true_of_the_others(graph):
    # d2 is in r1 now. d1 was in r1 once: the past of the others counts.
    found = {s["key"]: s["through"] for s in similar(graph, DEVICE, "d2")}
    assert found == {
        "d1": [("LOCATED_IN", "r1"), ("USED_BY", "red")],
        "d3": [("LOCATED_IN", "r1")],
        "d4": [("USED_BY", "red")],
    }
    # d1 is in r9 now. Its own past in r1 does not count for itself.
    assert {s["key"]: s["through"] for s in similar(graph, DEVICE, "d1")} == {
        "d2": [("USED_BY", "red")],
        "d4": [("USED_BY", "red")],
    }


def test_similar_can_count_one_relation_only(graph):
    assert [s["key"] for s in similar(graph, DEVICE, "d2", relations=["LOCATED_IN"])] == [
        "d1",
        "d3",
    ]
    assert [s["key"] for s in similar(graph, DEVICE, "d2", relations=["USED_BY"])] == ["d1", "d4"]


def test_similar_gives_the_best_first_up_to_the_limit(graph):
    assert [s["key"] for s in similar(graph, DEVICE, "d2", limit=1)] == ["d1"]
    assert [(s["key"], s["shared"]) for s in similar(graph, DEVICE, "d2", limit=2)] == [
        ("d1", 2),
        ("d3", 1),
    ]


def test_most_shared_comes_first_whatever_the_keys_are(graph):
    write(graph, row(key="a0", room="r1", teams=[]), row(key="z9", room="r1", teams=["red"]))
    ranked = [(s["key"], s["shared"]) for s in similar(graph, DEVICE, "d2")]
    assert ranked[:2] == [("d1", 2), ("z9", 2)] and ("a0", 1) in ranked[2:]
    assert [key for key, _ in ranked[2:]] == sorted(key for key, _ in ranked[2:])  # ties by key


def test_similar_counts_a_shared_target_once_however_many_edges_there_are(graph):
    write(graph, row(key="d1", minute=20, room="r1", teams=["red"]))  # d1 has two edges to r1 now
    assert "d1" not in [s["key"] for s in similar(graph, DEVICE, "d1")]  # never like itself
    by_key = {s["key"]: s for s in similar(graph, DEVICE, "d2")}
    assert by_key["d1"] == {
        "key": "d1",
        "shared": 2,
        "through": [("LOCATED_IN", "r1"), ("USED_BY", "red")],
    }


def test_entity_with_nothing_shared_or_not_known_has_nothing_similar(graph):
    assert similar(graph, DEVICE, "d5") == [] and similar(graph, DEVICE, "nope") == []


# --- what is refused ------------------------------------------------------------------


@pytest.mark.parametrize("key", [None, {"a": 1}, ["d1"], 1.5, "", "a\x00b", "x" * 201])
def test_key_of_a_wrong_form_is_refused(graph, key):
    for call in (
        lambda: pointing_at(graph, DEVICE, "LOCATED_IN", key),
        lambda: similar(graph, DEVICE, key),
    ):
        with pytest.raises(ValueError, match="key"):
            call()


@pytest.mark.parametrize(
    "relation", ["OWNS", "HAS_STATE", "NEXT", "", None, 7, "LOCATED_IN]->() DETACH DELETE x //"]
)
def test_relation_that_is_not_declared_is_refused(graph, relation):
    with pytest.raises(ValueError, match="no relation"):
        pointing_at(graph, DEVICE, relation, "r1")
    with pytest.raises(ValueError, match="no relation"):
        similar(graph, DEVICE, "d1", relations=[relation])
    assert count(graph, "(d:Device)") == 5


@pytest.mark.parametrize("relations", [[], "LOCATED_IN", {"LOCATED_IN": 1}, ["LOCATED_IN"] * 201])
def test_list_of_relations_of_a_wrong_form_is_refused(graph, relations):
    with pytest.raises(ValueError, match="relation"):
        similar(graph, DEVICE, "d1", relations=relations)


@pytest.mark.parametrize("limit", [0, -1, 1001, 1.5, "10", None, True])
def test_limit_of_a_wrong_form_is_refused(graph, limit):
    with pytest.raises(ValueError, match="limit"):
        similar(graph, DEVICE, "d1", limit=limit)


def test_read_at_a_time_needs_a_real_time(graph):
    for bad in ("", "soon"):
        with pytest.raises(ValueError):
            pointing_at(graph, DEVICE, "LOCATED_IN", "r1", bad)
