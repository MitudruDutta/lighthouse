"""Algorithms over the graph, each checked against a plain implementation written here."""

import random
from itertools import pairwise

import pytest
from devices import DEVICE, PERSON, ROOM, count, row, shape, when, write
from plain import fewest_steps, linked_sets, page_rank, paths_through

from lighthouse import (
    SELF,
    Kind,
    algorithms,
    between,
    close_episode,
    connection,
    ensure_schema,
    groups,
    important,
    open_episode,
    record,
    remember,
)

SHELF = Kind("Shelf", key="code", relations={"LOCATED_IN": ROOM})
# Two relations between the same persons.
MEMBER = Kind("Person", key="email", relations={"KNOWS": SELF, "LEADS": SELF})


def lead(graph, minute=0, **rows):
    """Persons with whom each knows and whom each leads, from `minute` on: (knows, leads)."""
    rows = [
        {"key": key, "t": when(minute), "relations": {"KNOWS": knows, "LEADS": leads}}
        for key, (knows, leads) in rows.items()
    ]
    assert {r["status"] for r in remember(graph, MEMBER, rows, by="test")} <= {"created", "changed"}


@pytest.fixture
def graph(graph):
    ensure_schema(graph, [PERSON, SHELF])
    return graph


def know(graph, minute=0, **lists):
    """Persons and whom each knows, from `minute` on."""
    rows = [{"key": k, "t": when(minute), "relations": {"KNOWS": v}} for k, v in lists.items()]
    done = {receipt["status"] for receipt in remember(graph, PERSON, rows, by="test")}
    assert done <= {"created", "changed", "unchanged"}


def people(graph, seed=3, size=40, most=3):
    """Random persons who know up to `most` others, written twice: the second time drops
    relations and adds others. Returns (names in the graph, every pair ever written, pairs
    now)."""
    rng = random.Random(seed)
    names = [f"p{n:02}" for n in range(size)]
    now, ever = {}, set()
    for minute in (0, 10):
        lists = {}
        for name in rng.sample(names, size * 2 // 3):
            lists[name] = rng.sample(names, rng.randint(0, most))  # may know itself
        know(graph, minute, **lists)
        now |= lists
        ever |= {(a, b) for a, known in lists.items() for b in known}
    current = {(a, b) for a, known in now.items() for b in known}
    assert ever - current, "the second time must drop a relation"
    return sorted(set(now) | {b for _, b in ever}), ever, current


@pytest.fixture
def devices(graph):
    """d1 left r1 at minute 5 and came back at minute 9. d2 left r1 at minute 7."""
    write(
        graph,
        row(key="d1", room="r1", teams=["red"]),
        row(key="d2", room="r1", teams=["blue"]),
        row(key="d3", room="r2", teams=["blue"]),
        row(key="d4", room="r3", teams=[]),
        row(key="d1", minute=5, room="r9", teams=["red"]),
        row(key="d2", minute=7, room="r8", teams=["blue"]),
        row(key="d1", minute=9, room="r1", teams=["red"]),
    )
    return graph


def scores(found) -> dict:
    return {entity: item["score"] for item in found for entity in [item["entity"]]}


def sent(graph, monkeypatch) -> list[str]:
    """The queries that go to the graph from now on. The list fills as they are sent."""
    seen, send = [], graph.ro_query

    def spy(query, *args, **kwargs):
        seen.append(query)
        return send(query, *args, **kwargs)

    monkeypatch.setattr(graph, "ro_query", spy)
    return seen


def searches(queries: list[str]) -> int:
    """How many of the queries ran an algorithm, and not only a count."""
    return sum("CALL algo." in query for query in queries)


# --- what belongs together ------------------------------------------------------------


def test_groups_are_the_sets_that_relations_join(devices):
    large, small = groups(devices, [DEVICE])
    assert small == {"size": 2, "members": [("Device", "d4"), ("Room", "r3")]}
    assert large["size"] == 9 and len(large["members"]) == 9
    # Oldest first. What one write creates besides its rows has no fixed order.
    assert large["members"][:3] == [("Device", "d1"), ("Device", "d2"), ("Device", "d3")]
    assert set(large["members"][3:7]) == {
        ("Room", "r1"),
        ("Room", "r2"),
        ("Team", "red"),
        ("Team", "blue"),
    }
    assert set(large["members"][7:]) == {("Room", "r9"), ("Room", "r8")}  # the second write


def test_groups_match_a_plain_search_on_random_relations(graph):
    names, ever, _ = people(graph, seed=4, size=90, most=1)
    found = groups(graph, [PERSON], at_least=1, limit=1_000, show=1_000)
    assert all(group["size"] == len(group["members"]) for group in found)
    assert [group["size"] for group in found] == sorted((g["size"] for g in found), reverse=True)
    assert {frozenset(key for _, key in group["members"]) for group in found} == linked_sets(
        names, ever
    )
    assert {label for group in found for label, _ in group["members"]} == {"Person"}
    assert len(found) > 3 and found[0]["size"] > 5  # the case has sets of several sizes


def test_groups_see_every_relation_that_was_ever_true(graph):
    know(graph, 0, a=["b"], c=["d"])
    know(graph, 5, a=[], b=["c"])  # a knows nobody now
    assert [set(g["members"]) for g in groups(graph, [PERSON])] == [
        {("Person", "a"), ("Person", "b"), ("Person", "c"), ("Person", "d")}
    ]


def test_smallest_group_that_is_listed_can_be_set(devices):
    assert [g["size"] for g in groups(devices, [DEVICE], at_least=3)] == [9]
    assert [g["size"] for g in groups(devices, [DEVICE], at_least=9)] == [9]
    assert groups(devices, [DEVICE], at_least=10) == []
    write(devices, row(key="d7", room=None, teams=[]))  # linked to nothing
    assert [g["size"] for g in groups(devices, [DEVICE])] == [9, 2]
    assert groups(devices, [DEVICE], at_least=1)[2:] == [{"size": 1, "members": [("Device", "d7")]}]


def test_groups_list_the_largest_up_to_the_limit_and_show_the_oldest_members(devices):
    assert [g["size"] for g in groups(devices, [DEVICE], limit=1)] == [9]
    shown = groups(devices, [DEVICE], show=2)
    assert shown == [
        {"size": 9, "members": [("Device", "d1"), ("Device", "d2")]},
        {"size": 2, "members": [("Device", "d4"), ("Room", "r3")]},
    ]


def test_groups_of_one_size_come_oldest_first(graph):
    know(graph, 0, z=["y"])
    know(graph, 1, b=["a"], n=["m"])
    assert [g["members"][0] for g in groups(graph, [PERSON])] == [
        ("Person", "z"),
        ("Person", "b"),
        ("Person", "n"),
    ]


def test_groups_follow_only_the_relations_that_are_named(devices):
    by_room = groups(devices, [DEVICE], ["LOCATED_IN"])
    assert [g["size"] for g in by_room] == [5, 2, 2]  # d1, d2 and their rooms; d3; d4
    assert set(by_room[0]["members"]) == {
        ("Device", "d1"),
        ("Device", "d2"),
        ("Room", "r1"),
        ("Room", "r9"),
        ("Room", "r8"),
    }
    by_team = groups(devices, [DEVICE], ["USED_BY"])
    assert [set(g["members"]) for g in by_team] == [
        {("Device", "d2"), ("Device", "d3"), ("Team", "blue")},
        {("Device", "d1"), ("Team", "red")},
    ]


def test_groups_keep_to_the_kinds_that_are_named(devices):
    know(devices, 0, a=["b"])
    assert [g["size"] for g in groups(devices, [DEVICE])] == [9, 2]
    assert [g["members"] for g in groups(devices, [PERSON])] == [[("Person", "a"), ("Person", "b")]]
    assert [g["size"] for g in groups(devices, [DEVICE, PERSON])] == [9, 2, 2]
    # A kind that is only pointed at has no relation of its own to follow.
    with pytest.raises(ValueError, match="no relation to follow"):
        groups(devices, [ROOM])


def test_episodes_about_the_same_entities_are_one_group(devices):
    open_episode(devices, "e1", by="test", about=[(DEVICE, "d1")])
    open_episode(devices, "e2", by="test", about=[(DEVICE, "d1"), (DEVICE, "d4")])
    open_episode(devices, "e3", by="test", about=[(DEVICE, "d3")])
    open_episode(devices, "e4", by="test", about=[(DEVICE, "d3")])
    open_episode(devices, "e5", by="test")
    found = groups(devices, [DEVICE], ["ABOUT"], records=["Episode"])
    assert [set(g["members"]) for g in found] == [
        {("Episode", "e1"), ("Episode", "e2"), ("Device", "d1"), ("Device", "d4")},
        {("Episode", "e3"), ("Episode", "e4"), ("Device", "d3")},
    ]
    # Without the records, an edge of a record joins nothing.
    assert groups(devices, [DEVICE], ["ABOUT"]) == []
    # With records and no relations named, the relations of the kinds join as well.
    assert [g["size"] for g in groups(devices, [DEVICE], records=["Episode"])] == [15]


def test_entries_and_what_they_cite_can_take_part(devices):
    open_episode(devices, "e1", by="test")
    record(devices, "e1", "note", by="test", values={"text": "seen"}, cites=[(DEVICE, "d4")])
    close_episode(devices, "e1", by="test")
    found = groups(devices, [DEVICE], ["HAS", "CITES"], records=["Episode", "Entry"])
    assert [g["size"] for g in found] == [4]  # the episode, its two entries, and d4
    assert {label for label, _ in found[0]["members"]} == {"Episode", "Entry", "Device"}


# --- what is important ----------------------------------------------------------------


def test_rank_of_two_entities_is_what_the_equations_give(graph):
    know(graph, 0, a=["b"])
    # a = 0.075 + 0.425 b and a + b = 1: b points at nothing, so it shares among both.
    found = important(graph, [PERSON])
    assert [item["entity"] for item in found] == [("Person", "b"), ("Person", "a")]
    assert found[0]["score"] == pytest.approx(0.649123, abs=5e-4)
    assert found[1]["score"] == pytest.approx(0.350877, abs=5e-4)


def test_rank_matches_a_plain_computation_on_random_relations(devices):
    names, ever, _ = people(devices)
    rooms = {"d1": ["r1", "r9"], "d2": ["r1", "r8"], "d3": ["r2"], "d4": ["r3"]}
    teams = {"d1": ["red"], "d2": ["blue"], "d3": ["blue"]}
    nodes = [("Person", name) for name in names] + [("Device", key) for key in rooms]
    nodes += [("Room", f"r{n}") for n in (1, 2, 3, 8, 9)] + [("Team", "red"), ("Team", "blue")]
    edges = {(("Person", a), ("Person", b)) for a, b in ever}
    edges |= {(("Device", d), ("Room", r)) for d, found in rooms.items() for r in found}
    edges |= {(("Device", d), ("Team", t)) for d, found in teams.items() for t in found}
    assert count(devices, "(e:Entity)") == len(nodes)

    found = scores(important(devices, [PERSON, DEVICE], limit=1_000))
    expected = page_rank(nodes, edges)
    assert found.keys() == expected.keys()
    assert sum(found.values()) == pytest.approx(1, abs=1e-5)
    assert max(abs(found[node] - expected[node]) for node in nodes) < 5e-4
    assert max(expected.values()) > 3 * min(expected.values())  # the case tells ranks apart

    # One relation: the other entities take part, with no edge.
    found = scores(important(devices, [PERSON, DEVICE], "KNOWS", limit=1_000))
    expected = page_rank(nodes, {(a, b) for a, b in edges if a[0] == "Person"})
    assert max(abs(found[node] - expected[node]) for node in nodes) < 5e-4
    assert found[("Room", "r1")] == pytest.approx(found[("Device", "d4")], abs=1e-9)


def test_rank_is_highest_first_and_follows_who_points_at_whom(graph):
    know(graph, 0, a=["hub"], b=["hub"], c=["hub"], hub=["next"], d=["a"])
    found = important(graph, [PERSON])
    assert [item["entity"][1] for item in found[:2]] == ["next", "hub"]  # all of hub goes on
    ranked = [item["score"] for item in found]
    assert ranked == sorted(ranked, reverse=True)
    by_key = {item["entity"][1]: item["score"] for item in found}
    assert by_key["a"] > by_key["b"] == pytest.approx(by_key["c"]) == pytest.approx(by_key["d"])
    assert [item["entity"][1] for item in found[3:]] == ["b", "c", "d"]  # equal: oldest first
    assert [item["entity"][1] for item in important(graph, [PERSON], limit=2)] == ["next", "hub"]


def test_rank_sees_every_relation_that_was_ever_true(graph):
    know(graph, 0, a=["old"], b=["old"], c=["old"])
    know(graph, 5, a=["new"], b=[], c=[])
    by_key = {item["entity"][1]: item["score"] for item in important(graph, [PERSON])}
    assert by_key["old"] > by_key["new"] > by_key["a"]


def test_rank_lists_the_kinds_that_are_named_and_counts_them_all(devices):
    know(devices, 0, a=["b"])
    everything = scores(important(devices, [DEVICE, PERSON], limit=1_000))
    only = scores(important(devices, [PERSON], limit=1_000))
    assert only.keys() == {("Person", "a"), ("Person", "b")}
    assert only == {entity: everything[entity] for entity in only}
    assert {label for label, _ in scores(important(devices, [DEVICE], limit=1_000))} == {
        "Device",
        "Room",
        "Team",
    }
    assert important(devices, [ROOM], limit=1)[0]["entity"][0] == "Room"


def test_rank_over_one_relation_ignores_the_others(devices):
    by_room = scores(important(devices, [DEVICE], "LOCATED_IN", limit=1_000))
    by_team = scores(important(devices, [DEVICE], "USED_BY", limit=1_000))
    assert by_room[("Room", "r3")] > by_room[("Team", "blue")]
    assert by_team[("Team", "blue")] > by_team[("Room", "r3")]
    assert by_team[("Room", "r1")] == pytest.approx(by_team[("Room", "r3")])


def test_rank_without_any_edge_is_equal_for_all(graph):
    know(graph, 0, a=[], b=[], c=[])
    assert important(graph, [PERSON]) == [
        {"entity": ("Person", key), "score": pytest.approx(1 / 3)} for key in "abc"
    ]
    assert [item["entity"][1] for item in important(graph, [PERSON], limit=2)] == ["a", "b"]


# --- what lies between ----------------------------------------------------------------


def test_between_counts_the_paths_that_run_through(graph):
    know(graph, 0, a=["b"], b=["c"], c=["d"])
    assert between(graph, [PERSON]) == [
        {"entity": ("Person", "b"), "score": 2.0},  # a to c, a to d
        {"entity": ("Person", "c"), "score": 2.0},  # a to d, b to d
        {"entity": ("Person", "a"), "score": 0.0},
        {"entity": ("Person", "d"), "score": 0.0},
    ]


def test_two_shortest_paths_count_half_each(graph):
    know(graph, 0, a=["b", "c"], b=["d"], c=["d"])
    assert scores(between(graph, [PERSON])) == {
        ("Person", "a"): 0.0,
        ("Person", "b"): 0.5,
        ("Person", "c"): 0.5,
        ("Person", "d"): 0.0,
    }


def test_between_matches_a_plain_computation_on_random_relations(devices):
    names, ever, _ = people(devices)
    found = scores(between(devices, [PERSON], limit=1_000))
    expected = paths_through(names, ever)
    assert found.keys() == {("Person", name) for name in names}
    assert max(abs(found[("Person", name)] - expected[name]) for name in names) < 1e-9
    assert sum(1 for value in expected.values() if value > 0) > 10  # the case has paths
    ranked = between(devices, [PERSON], limit=5)
    assert [item["score"] for item in ranked] == pytest.approx(
        sorted(expected.values(), reverse=True)[:5]
    )


def test_between_follows_the_direction_of_the_relations(devices):
    # Devices point at rooms and teams, and nothing points on from there.
    found = between(devices, [DEVICE], limit=1_000)
    assert len(found) == 11 and {item["score"] for item in found} == {0.0}
    assert [item["entity"] for item in found[:4]] == [  # equal: oldest first
        ("Device", "d1"),
        ("Device", "d2"),
        ("Device", "d3"),
        ("Device", "d4"),
    ]
    # Of equal scores, the limit keeps the oldest.
    assert [item["entity"] for item in between(devices, [DEVICE], limit=2)] == [
        ("Device", "d1"),
        ("Device", "d2"),
    ]


def test_between_follows_only_the_relations_that_are_named(graph):
    write(graph, row(key="d1", room="r1", teams=["red"]))
    assert {item["score"] for item in between(graph, [DEVICE], ["USED_BY"])} == {0.0}
    know(graph, 0, a=["b"], b=["c"])
    assert between(graph, [PERSON], ["KNOWS"], limit=1) == [
        {"entity": ("Person", "b"), "score": 1.0}
    ]


def test_between_counts_paths_over_the_relations_that_are_named(graph):
    lead(graph, 0, a=(["b"], []), b=([], ["c"]), c=([], []))
    assert between(graph, [MEMBER], limit=1) == [{"entity": ("Person", "b"), "score": 1.0}]
    assert {item["score"] for item in between(graph, [MEMBER], ["KNOWS"])} == {0.0}
    assert {item["score"] for item in between(graph, [MEMBER], ["LEADS"])} == {0.0}
    assert between(graph, [MEMBER], ["LEADS", "KNOWS"], limit=1)[0]["score"] == 1.0


def test_work_of_between_is_for_all_the_relations_it_follows(graph, monkeypatch):
    chain = "abcdefgh"
    lead(graph, 0, **{key: ([], [after]) for key, after in pairwise(chain)}, h=(["a"], []))
    assert count(graph, "()-[k:KNOWS]->()", "k") == 1 and count(graph, "()-[l:LEADS]->()", "l") == 7
    monkeypatch.setattr(algorithms, "SAMPLE", 1)
    monkeypatch.setattr(algorithms, "WORK", 8 * 3)  # 8 relations, from 3 persons

    def raw(sample):
        rows = graph.ro_query(
            "CALL algo.betweenness({nodeLabels: ['Person'], relationshipTypes: $types, "
            "samplingSize: $sample, samplingSeed: 1}) YIELD node, score RETURN node.email, score",
            {"sample": sample, "types": ["KNOWS", "LEADS"]},
        ).result_set
        return {("Person", name): pytest.approx(score * 8 / sample) for name, score in rows}

    found = scores(between(graph, [MEMBER], limit=1_000))
    assert found == raw(3) and found != raw(8)


def test_sample_of_between_is_scaled_to_the_whole(devices):
    names, ever, _ = people(devices)
    exact = sum(paths_through(names, ever).values())
    for sample in (len(names), len(names) + 1, 1_000):  # as many as there are: exact
        found = scores(between(devices, [PERSON], sample=sample, seed=3, limit=1_000))
        assert sum(found.values()) == pytest.approx(exact, abs=1e-9)

    once = between(devices, [PERSON], sample=10, seed=7, limit=1_000)
    assert once == between(devices, [PERSON], sample=10, seed=7, limit=1_000)
    assert once != between(devices, [PERSON], sample=10, seed=8, limit=1_000)
    # What FalkorDB gives for these ten, times the persons that each of the ten stands for.
    raw = devices.ro_query(
        "CALL algo.betweenness({nodeLabels: ['Person'], relationshipTypes: ['KNOWS'], "
        "samplingSize: 10, samplingSeed: 7}) YIELD node, score RETURN node.email, score"
    ).result_set
    assert scores(once) == {
        ("Person", name): pytest.approx(score * len(names) / 10) for name, score in raw
    }
    # Over many samples, the scaled sum comes to the exact one.
    totals = [
        sum(scores(between(devices, [PERSON], sample=10, seed=seed, limit=1_000)).values())
        for seed in range(1, 41)
    ]
    assert sum(totals) / len(totals) == pytest.approx(exact, rel=0.15)


def test_between_counts_from_as_many_as_the_work_allows(devices, monkeypatch):
    names, ever, _ = people(devices)
    relations = count(devices, "(:Person)-[k:KNOWS]->(:Person)", "k")
    exact = paths_through(names, ever)

    def raw(sample):  # what FalkorDB gives for a sample of that size, scaled to all
        rows = devices.ro_query(
            "CALL algo.betweenness({nodeLabels: ['Person'], relationshipTypes: ['KNOWS'], "
            "samplingSize: $sample, samplingSeed: 1}) YIELD node, score RETURN node.email, score",
            {"sample": sample},
        ).result_set
        return {
            ("Person", name): pytest.approx(score * len(names) / sample) for name, score in rows
        }

    def found():
        algorithms._ANSWERS.clear()
        return scores(between(devices, [PERSON], limit=1_000))

    # The work allows all of them: exact.
    assert found() == {("Person", name): pytest.approx(exact[name], abs=1e-9) for name in names}
    monkeypatch.setattr(algorithms, "WORK", relations * len(names))
    assert found() == {("Person", name): pytest.approx(exact[name], abs=1e-9) for name in names}
    # The work allows 12, and no less than SAMPLE.
    monkeypatch.setattr(algorithms, "WORK", relations * 12 + relations - 1)
    monkeypatch.setattr(algorithms, "SAMPLE", 5)
    assert found() == raw(12) != raw(5)
    monkeypatch.setattr(algorithms, "SAMPLE", 20)
    assert found() == raw(20)
    monkeypatch.setattr(algorithms, "WORK", 0)
    assert found() == raw(20)
    # A sample that is asked for is taken, whatever the work is.
    assert scores(between(devices, [PERSON], sample=7, limit=1_000)) == raw(7)


# --- how two things are connected -----------------------------------------------------


def test_connection_is_the_chain_of_relations_with_what_holds_now(devices):
    assert connection(devices, (DEVICE, "d1"), (DEVICE, "d3")) == [
        {
            "from": ("Device", "d1"),
            "relation": "LOCATED_IN",
            "to": ("Room", "r1"),
            "forward": True,
            "current": True,  # d1 came back: the last time started at minute 9
            "since": when(9),
            "until": None,
        },
        {
            "from": ("Room", "r1"),
            "relation": "LOCATED_IN",
            "to": ("Device", "d2"),
            "forward": False,
            "current": False,  # d2 left at minute 7
            "since": when(0),
            "until": when(7),
        },
        {
            "from": ("Device", "d2"),
            "relation": "USED_BY",
            "to": ("Team", "blue"),
            "forward": True,
            "current": True,
            "since": when(0),
            "until": None,
        },
        {
            "from": ("Team", "blue"),
            "relation": "USED_BY",
            "to": ("Device", "d3"),
            "forward": False,
            "current": True,
            "since": when(0),
            "until": None,
        },
    ]


def test_connection_of_a_relation_that_ended_twice_gives_the_last_time(devices):
    write(devices, row(key="d1", minute=12, room="r2", teams=["red"]))  # left r1 again
    [step] = connection(devices, (DEVICE, "d1"), (ROOM, "r1"))
    assert (step["current"], step["since"], step["until"]) == (False, when(9), when(12))
    assert count(devices, "(:Device {serial: 'd1'})-[o:LOCATED_IN]->(:Room {code: 'r1'})", "o") == 2


def test_step_tells_only_of_the_relation_it_names(graph):
    lead(graph, 0, a=(["b"], ["b"]), b=([], []))
    lead(graph, 5, a=([], ["b"]))  # a leads b still, and knows b no more
    [knows] = connection(graph, (MEMBER, "a"), (MEMBER, "b"), relations=["KNOWS"])
    assert (knows["relation"], knows["current"], knows["until"]) == ("KNOWS", False, when(5))
    [leads] = connection(graph, (MEMBER, "a"), (MEMBER, "b"), relations=["LEADS"])
    assert (leads["relation"], leads["current"], leads["until"]) == ("LEADS", True, None)
    assert connection(graph, (MEMBER, "a"), (MEMBER, "b")) == [leads]  # both: the one that holds
    # The other way holds nothing, though the two are joined.
    [back] = connection(graph, (MEMBER, "b"), (MEMBER, "a"), relations=["KNOWS"])
    assert (back["forward"], back["current"], back["since"]) == (False, False, when(0))


def test_connection_reads_the_same_from_either_end(devices):
    there = connection(devices, (DEVICE, "d1"), (DEVICE, "d3"))
    back = connection(devices, (DEVICE, "d3"), (DEVICE, "d1"))
    assert [(s["to"], s["relation"], s["from"], not s["forward"]) for s in reversed(back)] == [
        (s["from"], s["relation"], s["to"], s["forward"]) for s in there
    ]
    assert [s["current"] for s in reversed(back)] == [s["current"] for s in there]


def test_connection_matches_a_plain_search_on_random_relations(graph):
    names, ever, current = people(graph)
    rng = random.Random(11)
    lengths = set()
    for _ in range(80):
        start, end = rng.sample(names, 2)
        expected = fewest_steps(ever, start, end)
        steps = connection(graph, (PERSON, start), (PERSON, end), max_hops=10)
        lengths.add(expected)
        if expected is None or expected > 10:
            assert steps is None
            continue
        assert len(steps) == expected
        assert steps[0]["from"] == ("Person", start) and steps[-1]["to"] == ("Person", end)
        for step, after in pairwise(steps):
            assert step["to"] == after["from"]
        for step in steps:
            pair = (step["from"][1], step["to"][1])
            assert step["current"] == (pair in current or pair[::-1] in current)
            pair = pair if step["forward"] else pair[::-1]
            assert pair in ever and step["relation"] == "KNOWS"
            assert step["current"] == (pair in current)
            assert (step["until"] is None) == step["current"] and step["since"] is not None
    assert None in lengths and len(lengths) > 4  # the case has pairs near, far, and apart


def test_connection_stops_at_the_number_of_steps_allowed(graph):
    know(graph, 0, a=["b"], b=["c"], c=["d"], d=["e"])
    assert len(connection(graph, (PERSON, "a"), (PERSON, "e"))) == 4
    assert len(connection(graph, (PERSON, "a"), (PERSON, "e"), max_hops=4)) == 4
    assert connection(graph, (PERSON, "a"), (PERSON, "e"), max_hops=3) is None
    assert len(connection(graph, (PERSON, "a"), (PERSON, "b"), max_hops=1)) == 1


def test_connection_takes_the_shortest_chain(graph):
    know(graph, 0, a=["b", "x"], b=["c"], c=["d"], x=["d"])
    assert [step["to"][1] for step in connection(graph, (PERSON, "a"), (PERSON, "d"))] == ["x", "d"]


def test_things_that_nothing_joins_have_no_connection(devices):
    assert connection(devices, (DEVICE, "d1"), (DEVICE, "d4")) is None
    assert connection(devices, (DEVICE, "d1"), (DEVICE, "nope")) is None
    assert connection(devices, (DEVICE, "nope"), (DEVICE, "d1")) is None
    assert connection(devices, (DEVICE, "d1"), (DEVICE, "d1")) == []


def test_connection_follows_only_the_relations_that_are_named(devices):
    assert connection(devices, (DEVICE, "d2"), (DEVICE, "d3"), relations=["LOCATED_IN"]) is None
    by_team = connection(devices, (DEVICE, "d2"), (DEVICE, "d3"), relations=["USED_BY"])
    assert [step["to"] for step in by_team] == [("Team", "blue"), ("Device", "d3")]


def test_connection_needs_the_kind_that_points_at_both(devices):
    # A room points at nothing. The devices that are in rooms join them.
    with pytest.raises(ValueError, match="no relation to follow"):
        connection(devices, (ROOM, "r1"), (ROOM, "r9"))
    steps = connection(devices, (ROOM, "r1"), (ROOM, "r9"), kinds=[DEVICE])
    assert [(s["from"], s["forward"], s["to"]) for s in steps] == [
        (("Room", "r1"), False, ("Device", "d1")),
        (("Device", "d1"), True, ("Room", "r9")),
    ]
    assert [(s["current"], s["until"]) for s in steps] == [(True, None), (False, when(9))]


def test_connection_can_go_through_records(devices):
    open_episode(devices, "e1", by="test", about=[(DEVICE, "d1"), (DEVICE, "d4")])
    assert connection(devices, (DEVICE, "d1"), (DEVICE, "d4")) is None  # not by default
    steps = connection(devices, (DEVICE, "d1"), (DEVICE, "d4"), relations=["ABOUT"])
    assert steps == [
        {
            "from": ("Device", "d1"),
            "relation": "ABOUT",
            "to": ("Episode", "e1"),
            "forward": False,
            "current": True,
            "since": None,
            "until": None,
        },
        {
            "from": ("Episode", "e1"),
            "relation": "ABOUT",
            "to": ("Device", "d4"),
            "forward": True,
            "current": True,
            "since": None,
            "until": None,
        },
    ]
    from_record = connection(
        devices, ("Episode", "e1"), (ROOM, "r3"), kinds=[DEVICE], relations=["ABOUT", "LOCATED_IN"]
    )
    assert [step["to"] for step in from_record] == [("Device", "d4"), ("Room", "r3")]


def test_entity_of_a_kind_that_was_not_given_has_no_key(devices):
    remember(
        devices,
        SHELF,
        [{"key": "s1", "t": when(0), "relations": {"LOCATED_IN": ["r3", "r2"]}}],
        by="test",
    )
    steps = connection(devices, (DEVICE, "d4"), (DEVICE, "d3"), relations=["LOCATED_IN"])
    assert [step["to"] for step in steps] == [
        ("Room", "r3"),
        ("Shelf", None),
        ("Room", "r2"),
        ("Device", "d3"),
    ]
    steps = connection(devices, (DEVICE, "d4"), (DEVICE, "d3"), [SHELF], ["LOCATED_IN"])
    assert steps[1]["to"] == ("Shelf", "s1") and steps[2]["from"] == ("Shelf", "s1")


def test_kind_that_is_first_written_after_other_entities_is_named_by_its_label(devices):
    # The schema does not know this kind, so its label is made after the label that all
    # entities share. FalkorDB then lists the shared label first.
    crate = Kind("Crate", key="code", relations={"LOCATED_IN": ROOM, "INSIDE": SELF})
    rows = [
        {"key": "c1", "t": when(0), "relations": {"LOCATED_IN": ["r3"], "INSIDE": ["c2"]}},
        {"key": "c2", "t": when(0), "relations": {"LOCATED_IN": [], "INSIDE": ["c3"]}},
    ]
    assert {r["status"] for r in remember(devices, crate, rows, by="test")} == {"created"}
    [[labels]] = devices.ro_query("MATCH (c:Crate {code: 'c1'}) RETURN labels(c)").result_set
    assert labels == ["Entity", "Crate"]  # the case: the label of the kind is not the first

    found = groups(devices, [crate], ["INSIDE"])
    assert found == [{"size": 3, "members": [("Crate", "c1"), ("Crate", "c2"), ("Crate", "c3")]}]
    assert between(devices, [crate], ["INSIDE"], limit=1) == [
        {"entity": ("Crate", "c2"), "score": 1.0}
    ]
    assert important(devices, [crate], "INSIDE", limit=1)[0]["entity"] == ("Crate", "c3")
    steps = connection(devices, (DEVICE, "d4"), (crate, "c3"), relations=["LOCATED_IN", "INSIDE"])
    assert [step["to"] for step in steps] == [
        ("Room", "r3"),
        ("Crate", "c1"),
        ("Crate", "c2"),
        ("Crate", "c3"),
    ]


def test_same_key_of_two_kinds_is_two_things(graph):
    write(graph, row(key="same", room="same", teams=[]))
    [step] = connection(graph, (DEVICE, "same"), (ROOM, "same"))
    assert (step["from"], step["to"]) == (("Device", "same"), ("Room", "same"))
    assert connection(graph, (ROOM, "same"), (ROOM, "same"), kinds=[DEVICE]) == []


def test_step_tells_of_a_relation_that_holds_now_before_one_that_ended(graph):
    know(graph, 0, b=["a"])
    know(graph, 3, a=["b"])
    know(graph, 5, a=[])  # a knew b from minute 3 to minute 5; b knows a from minute 0 on
    holds = {"relation": "KNOWS", "current": True, "since": when(0), "until": None}
    [there] = connection(graph, (PERSON, "a"), (PERSON, "b"))
    [back] = connection(graph, (PERSON, "b"), (PERSON, "a"))
    assert there == holds | {"from": ("Person", "a"), "to": ("Person", "b"), "forward": False}
    assert back == holds | {"from": ("Person", "b"), "to": ("Person", "a"), "forward": True}
    # Both ended: the one that ended last.
    know(graph, 9, b=[])
    [there] = connection(graph, (PERSON, "a"), (PERSON, "b"))
    assert (there["forward"], there["current"], there["since"], there["until"]) == (
        False,
        False,
        when(0),
        when(9),
    )
    know(graph, 12, a=["b"])
    know(graph, 15, a=[])  # now a knew b last, to minute 15
    [there] = connection(graph, (PERSON, "a"), (PERSON, "b"))
    assert (there["forward"], there["since"], there["until"]) == (True, when(12), when(15))


def test_step_of_two_relations_that_hold_tells_of_the_first_by_name(graph):
    lead(graph, 0, a=(["b"], ["b"]), b=([], ["a"]))
    [there] = connection(graph, (MEMBER, "a"), (MEMBER, "b"))
    assert (there["relation"], there["forward"]) == ("KNOWS", True)
    [there] = connection(graph, (MEMBER, "a"), (MEMBER, "b"), relations=["LEADS"])
    assert (there["relation"], there["forward"]) == ("LEADS", True)  # along the walk
    [back] = connection(graph, (MEMBER, "b"), (MEMBER, "a"), relations=["LEADS"])
    assert (back["relation"], back["forward"]) == ("LEADS", True)


# --- an empty graph, and no writes -----------------------------------------------------


def test_graph_without_entities_gives_nothing(graph):
    assert groups(graph, [DEVICE]) == [] and important(graph, [DEVICE]) == []
    assert between(graph, [PERSON]) == []
    assert connection(graph, (DEVICE, "d1"), (DEVICE, "d2")) is None


def test_relation_that_was_never_written_joins_nothing(graph):
    write(graph, row(key="d1", room=None, teams=[]), row(key="d2", room=None, teams=[]))
    assert groups(graph, [DEVICE]) == []
    assert [g["size"] for g in groups(graph, [DEVICE], at_least=1)] == [1, 1]
    assert {item["score"] for item in between(graph, [DEVICE])} == {0.0}
    assert [item["score"] for item in important(graph, [DEVICE], "USED_BY")] == [0.5, 0.5]
    assert connection(graph, (DEVICE, "d1"), (DEVICE, "d2")) is None


def test_algorithms_change_nothing(devices):
    names, _, _ = people(devices)
    open_episode(devices, "e1", by="test", about=[(DEVICE, "d1")])
    before = shape(devices)
    groups(devices, [DEVICE, PERSON], records=["Episode"])
    important(devices, [DEVICE, PERSON])
    between(devices, [PERSON], sample=5)
    connection(devices, (PERSON, names[0]), (PERSON, names[1]))
    assert shape(devices) == before


# --- answers that are kept -------------------------------------------------------------

KEPT = {
    "groups": lambda graph: groups(graph, [DEVICE, PERSON]),
    "important": lambda graph: important(graph, [DEVICE, PERSON], "KNOWS"),
    "between": lambda graph: between(graph, [PERSON]),
}


@pytest.mark.parametrize("call", KEPT)
def test_answer_is_kept_while_the_graph_does_not_grow(devices, monkeypatch, call):
    know(devices, 0, a=["b"], b=["c"])
    queries = sent(devices, monkeypatch)
    first = KEPT[call](devices)
    assert searches(queries) == 1
    asked = len(queries)
    for _ in range(3):
        assert KEPT[call](devices) == first
    # Each time: is it the same graph, and has it as many nodes and edges as before?
    assert (
        queries[asked:]
        == [
            "MATCH (s:Stamp) RETURN s.id",
            "MATCH (n) RETURN count(n)",
            "MATCH ()-[e]->() RETURN count(e)",
        ]
        * 3
    )


@pytest.mark.parametrize("call", KEPT)
def test_answer_is_new_when_the_graph_grew_where_the_call_reads_it(devices, monkeypatch, call):
    know(devices, 0, a=["b"], b=["c"])
    first = KEPT[call](devices)
    queries = sent(devices, monkeypatch)
    know(devices, 5, c=["d"], d=["a"])  # one new person, two new relations
    second = KEPT[call](devices)
    assert searches(queries) == 1 and second != first
    algorithms._ANSWERS.clear()
    assert KEPT[call](devices) == second  # the same as an answer that was never kept


def test_answer_is_new_after_one_more_relation_between_the_same_entities(graph, monkeypatch):
    know(graph, 0, a=["b"], b=["c"], c=[])
    assert scores(between(graph, [PERSON])) == {
        ("Person", "a"): 0.0,
        ("Person", "b"): 1.0,
        ("Person", "c"): 0.0,
    }
    assert [g["size"] for g in groups(graph, [PERSON], at_least=1)] == [3]
    know(graph, 5, c=["a"])  # no new person: a ring now
    assert set(scores(between(graph, [PERSON])).values()) == {1.0}
    know(graph, 6, c=[])
    know(graph, 7, c=["a"])  # the same relation again: the graph is the same, the answer too
    queries = sent(graph, monkeypatch)
    assert set(scores(between(graph, [PERSON])).values()) == {1.0}
    assert searches(queries) == 1  # computed again all the same: an edge was added


@pytest.mark.parametrize("call", KEPT)
def test_growth_that_the_call_does_not_read_keeps_the_answer(devices, monkeypatch, call):
    know(devices, 0, a=["b"], b=["c"])
    first = KEPT[call](devices)
    queries = sent(devices, monkeypatch)
    # New values make a new State. An episode makes records and their edges.
    write(devices, row(key="d4", minute=30, room="r3", teams=[], status="down"))
    open_episode(devices, "e1", by="test", about=[(DEVICE, "d1"), (PERSON, "a")])
    record(devices, "e1", "note", by="test", values={"text": "seen"})
    assert KEPT[call](devices) == first
    assert searches(queries) == 0 and len(queries) > 2  # it looked closer, and did not search
    before = len(queries)
    assert KEPT[call](devices) == first
    assert len(queries) == before + 3  # the whole graph is as it was: no closer look


def test_rank_over_every_relation_is_new_after_any_new_edge(devices, monkeypatch):
    first = important(devices, [DEVICE])
    queries = sent(devices, monkeypatch)
    write(devices, row(key="d4", minute=30, room="r3", teams=[], status="down"))
    assert important(devices, [DEVICE]) == first  # the same rank, computed again
    assert searches(queries) == 1
    assert important(devices, [DEVICE]) == first and searches(queries) == 1
    # One more relation between entities that were there: as many entities, another rank.
    write(devices, row(key="d4", minute=40, room="r1", teams=[], status="down"))
    second = scores(important(devices, [DEVICE], limit=1_000))
    assert searches(queries) == 2
    assert second[("Room", "r1")] > scores(first)[("Room", "r1")]
    assert second[("Room", "r3")] < scores(first)[("Room", "r3")]


def test_entity_that_nothing_links_is_in_the_next_answer(devices, monkeypatch):
    assert [g["size"] for g in groups(devices, [DEVICE], at_least=1)] == [9, 2]
    assert len(between(devices, [DEVICE], limit=1_000)) == 11
    assert len(important(devices, [DEVICE], "USED_BY", limit=1_000)) == 11
    write(devices, row(key="d7", room=None, teams=[]))  # no relation: only the entity is new
    assert groups(devices, [DEVICE], at_least=1)[2] == {"size": 1, "members": [("Device", "d7")]}
    assert ("Device", "d7") in scores(between(devices, [DEVICE], limit=1_000))
    ranked = scores(important(devices, [DEVICE], "USED_BY", limit=1_000))
    assert ("Device", "d7") in ranked and sum(ranked.values()) == pytest.approx(1)


def test_answer_that_is_kept_cannot_be_changed_by_who_gets_it(devices):
    know(devices, 0, a=["b"], b=["c"])
    for call in KEPT.values():
        first = call(devices)
        again = call(devices)
        assert again == first and again is not first and again[0] is not first[0]
        again[0].clear()
        again.clear()
        assert call(devices) == first
    found = groups(devices, [DEVICE])
    found[0]["members"].append(("Device", "made up"))
    found[0]["members"][0] = None
    assert groups(devices, [DEVICE])[0]["members"][0] == ("Device", "d1")
    assert ("Device", "made up") not in groups(devices, [DEVICE])[0]["members"]


def test_each_call_has_an_answer_of_its_own(devices, monkeypatch):
    know(devices, 0, a=["b"], b=["c"])
    queries = sent(devices, monkeypatch)
    calls = [
        lambda: groups(devices, [DEVICE]),
        lambda: groups(devices, [DEVICE], limit=1),
        lambda: groups(devices, [DEVICE], show=1),
        lambda: groups(devices, [DEVICE], at_least=3),
        lambda: groups(devices, [DEVICE], ["USED_BY"]),
        lambda: groups(devices, [DEVICE, PERSON]),
        lambda: groups(devices, [DEVICE], records=["Episode"]),
        lambda: important(devices, [DEVICE]),
        lambda: important(devices, [DEVICE], limit=1),
        lambda: important(devices, [DEVICE], "USED_BY"),
        lambda: important(devices, [PERSON]),
        lambda: between(devices, [PERSON]),
        lambda: between(devices, [PERSON], limit=1),
        lambda: between(devices, [PERSON], sample=2),
        lambda: between(devices, [PERSON], sample=2, seed=2),
        lambda: between(devices, [DEVICE, PERSON]),
        lambda: between(devices, [DEVICE, PERSON], ["KNOWS"]),
    ]
    answers = [call() for call in calls]
    assert searches(queries) == len(calls)
    assert [call() for call in calls] == answers and searches(queries) == len(calls)
    assert len(answers[0]) == 2 and len(answers[1]) == 1 and len(answers[3]) == 1
    assert len(answers[0][0]["members"]) == 9 and len(answers[2][0]["members"]) == 1


def test_two_functions_never_share_an_answer(graph):
    know(graph, 0, a=["b"], b=["c"])
    # The same kinds, relations, and numbers, in the same places of the two calls.
    sets = groups(graph, [PERSON], at_least=2, limit=100, show=100)
    ranked = between(graph, [PERSON], limit=2, sample=100, seed=100)
    assert sets == [{"size": 3, "members": [("Person", "a"), ("Person", "b"), ("Person", "c")]}]
    assert ranked == [
        {"entity": ("Person", "b"), "score": 1.0},
        {"entity": ("Person", "a"), "score": 0.0},
    ]


def test_kind_with_another_key_has_an_answer_of_its_own(devices):
    by_serial = groups(devices, [DEVICE], show=1)
    by_status = Kind("Device", key="status", relations=dict(DEVICE.relations))
    assert by_serial[0]["members"] == [("Device", "d1")]
    assert groups(devices, [by_status], show=1)[0]["members"] == [("Device", "ok")]
    assert groups(devices, [DEVICE], show=1) == by_serial


def test_answers_of_one_graph_are_not_given_for_another(devices, db, monkeypatch):
    other = db.select_graph(f"{devices.name}_other")
    try:
        ensure_schema(other, [PERSON])
        know(devices, 0, a=["b"], b=["c"])
        know(other, 0, x=["y"], y=["z"])  # the same numbers of nodes and edges of the kind
        assert [item["entity"][1] for item in between(devices, [PERSON])] == ["b", "a", "c"]
        assert [item["entity"][1] for item in between(other, [PERSON])] == ["y", "x", "z"]
        assert [g["members"][0][1] for g in groups(other, [PERSON])] == ["x"]
        # Each graph has its own answer: to ask one does not lose the answer of the other.
        seen = sent(devices, monkeypatch), sent(other, monkeypatch)
        for _ in range(2):
            assert [item["entity"][1] for item in between(devices, [PERSON])] == ["b", "a", "c"]
            assert [item["entity"][1] for item in between(other, [PERSON])] == ["y", "x", "z"]
        assert searches(seen[0]) == searches(seen[1]) == 0
    finally:
        other.delete()


def test_graph_that_was_made_again_gets_new_answers(db):
    name = "test_made_again"
    for keys in ("abc", "xyz", "abc"):
        graph = db.select_graph(name)
        try:
            ensure_schema(graph, [PERSON])
            first, second, third = keys
            know(graph, 0, **{first: [second]})
            assert groups(graph, [PERSON]) == [
                {"size": 2, "members": [("Person", first), ("Person", second)]}
            ]
            know(graph, 1, **{second: [third]})
            assert [item["entity"][1] for item in between(graph, [PERSON], limit=1)] == [second]
        finally:
            graph.delete()


def test_only_so_many_answers_are_kept(devices, monkeypatch):
    know(devices, 0, a=["b"], b=["c"])
    monkeypatch.setattr(algorithms, "MAX_ANSWERS", 2)
    algorithms._ANSWERS.clear()
    queries = sent(devices, monkeypatch)
    one, two, three = (lambda n=n: between(devices, [PERSON], limit=n) for n in (1, 2, 3))
    one(), two()
    assert searches(queries) == 2
    two(), one()  # used again: nothing is dropped, and `two` is now used longest ago
    assert searches(queries) == 2
    three()
    assert searches(queries) == 3 and len(algorithms._ANSWERS[devices.client]) == 2
    one(), three()
    assert searches(queries) == 3
    two()
    assert searches(queries) == 4 and len(algorithms._ANSWERS[devices.client]) == 2


def test_large_answer_is_not_kept(devices, monkeypatch):
    monkeypatch.setattr(algorithms, "MAX_KEPT", 12)  # 11 members and 2 groups: 13
    queries = sent(devices, monkeypatch)
    first = groups(devices, [DEVICE])
    assert groups(devices, [DEVICE]) == first and searches(queries) == 2
    groups(devices, [DEVICE], show=4), groups(devices, [DEVICE], show=4)  # 6 members: 8
    assert searches(queries) == 3
    monkeypatch.setattr(algorithms, "MAX_KEPT", 13)
    groups(devices, [DEVICE]), groups(devices, [DEVICE])
    assert searches(queries) == 4


def test_graph_without_a_stamp_gets_a_new_answer_every_time(db, monkeypatch):
    # Made by writes alone, with no ensure_schema(): nothing tells this graph from another
    # that is made under its name later.
    graph = db.select_graph("test_no_stamp")
    try:
        know(graph, 0, a=["b"], b=["c"])
        queries = sent(graph, monkeypatch)
        for done in (1, 2, 3):
            assert [item["entity"][1] for item in between(graph, [PERSON], limit=1)] == ["b"]
            assert [g["size"] for g in groups(graph, [PERSON])] == [3]
            assert important(graph, [PERSON], limit=1)[0]["entity"] == ("Person", "c")
            assert searches(queries) == 3 * done
        ensure_schema(graph, [PERSON])  # stamped from here on
        for _ in range(3):
            assert [g["size"] for g in groups(graph, [PERSON])] == [3]
        assert searches(queries) == 10
    finally:
        graph.delete()


def test_answer_of_a_graph_that_lost_its_stamp_is_not_given(graph, monkeypatch):
    know(graph, 0, a=["b"], b=["c"])
    first = between(graph, [PERSON])
    graph.query("MATCH (s:Stamp) SET s.id = 'another'")
    queries = sent(graph, monkeypatch)
    assert between(graph, [PERSON]) == first and searches(queries) == 1
    assert between(graph, [PERSON]) == first and searches(queries) == 1


def test_kept_answers_go_when_the_client_goes():
    class Client:
        pass

    client = Client()
    algorithms._ANSWERS[client] = {"key": "answer"}
    assert client in algorithms._ANSWERS
    del client
    assert not [c for c in algorithms._ANSWERS if isinstance(c, Client)]


def test_person_who_knows_itself_is_a_group_and_lies_between_nothing(graph):
    alone = Kind("Person", key="email", relations={"KNOWS": SELF})
    know(graph, 0, a=["a"], b=["b", "c"])
    assert [g["members"] for g in groups(graph, [alone], at_least=1)] == [
        [("Person", "b"), ("Person", "c")],
        [("Person", "a")],
    ]
    assert {item["score"] for item in between(graph, [alone])} == {0.0}
    assert connection(graph, (alone, "a"), (alone, "b")) is None


# --- what is refused ------------------------------------------------------------------

CALLS = {
    "groups": lambda graph, kinds, relations: groups(graph, kinds, relations),
    "between": lambda graph, kinds, relations: between(graph, kinds, relations),
    "important": lambda graph, kinds, relations: important(
        graph, kinds, relations[0] if isinstance(relations, list) and relations else relations
    ),
    "connection": lambda graph, kinds, relations: connection(
        graph, (DEVICE, "d1"), (DEVICE, "d2"), kinds, relations
    ),
}


@pytest.mark.parametrize("call", ["groups", "between", "important", "connection"])
@pytest.mark.parametrize("kinds", ["Device", DEVICE, None, 7, ["Device"], [DEVICE, None], {}])
def test_kinds_of_a_wrong_form_are_refused(devices, call, kinds):
    with pytest.raises(TypeError, match="kinds must be a list of Kind"):
        CALLS[call](devices, kinds, None)


@pytest.mark.parametrize("call", ["groups", "between", "important"])
def test_no_kind_at_all_is_refused(devices, call):
    # With no label to keep to, FalkorDB would take every node of the graph.
    with pytest.raises(ValueError, match="at least one kind"):
        CALLS[call](devices, [], None)


@pytest.mark.parametrize("call", ["groups", "between", "important", "connection"])
@pytest.mark.parametrize(
    "relation",
    ["OWNS", "HAS_STATE", "NEXT", "WROTE", "", None, 7, ["USED_BY"], "USED_BY|HAS_STATE"]
    + ["USED_BY*..9]-() DETACH DELETE b //", "USED_BY']}) YIELD node DETACH DELETE node //"],
)
def test_relation_that_is_not_one_of_the_kinds_is_refused(devices, call, relation):
    if call == "important" and relation is None:
        return  # it takes one relation, and none means every relation
    before = shape(devices)
    with pytest.raises(ValueError, match="not a relation of these kinds"):
        CALLS[call](devices, [DEVICE], [relation])
    assert shape(devices) == before


@pytest.mark.parametrize("call", ["groups", "between", "connection"])
@pytest.mark.parametrize("relations", ["USED_BY", {"USED_BY": 1}, 7, ["USED_BY"] * 201])
def test_list_of_relations_of_a_wrong_form_is_refused(devices, call, relations):
    with pytest.raises(ValueError, match="relations must be a list"):
        CALLS[call](devices, [DEVICE], relations)


@pytest.mark.parametrize("call", ["groups", "between", "connection"])
def test_empty_list_of_relations_is_refused(devices, call):
    # With no type to keep to, FalkorDB would follow every edge of the graph.
    with pytest.raises(ValueError, match="no relation to follow"):
        CALLS[call](devices, [DEVICE], [])


@pytest.mark.parametrize("records", ["Episode", {"Episode": 1}, None, 7])
def test_records_of_a_wrong_form_are_refused(devices, records):
    with pytest.raises(TypeError, match="records must be a list"):
        groups(devices, [DEVICE], records=records)


@pytest.mark.parametrize("label", ["State", "Agent", "Task", "Handoff", "Device", "", None, 7])
def test_record_that_is_not_one_is_refused(devices, label):
    with pytest.raises(ValueError, match="not a record"):
        groups(devices, [DEVICE], records=[label])


@pytest.mark.parametrize("number", [0, -1, 1.5, "10", None, True, 10**9])
def test_number_of_a_wrong_form_is_refused(devices, number):
    for name, call in (
        ("at_least", lambda: groups(devices, [DEVICE], at_least=number)),
        ("limit", lambda: groups(devices, [DEVICE], limit=number)),
        ("show", lambda: groups(devices, [DEVICE], show=number)),
        ("limit", lambda: important(devices, [DEVICE], limit=number)),
        ("limit", lambda: between(devices, [DEVICE], limit=number)),
        ("sample", lambda: between(devices, [DEVICE], sample=number or 0)),  # None: the default
        ("max_hops", lambda: connection(devices, (DEVICE, "d1"), (DEVICE, "d3"), max_hops=number)),
    ):
        with pytest.raises(ValueError, match=f"{name} must be a whole number"):
            call()


def test_numbers_have_an_upper_limit(devices):
    assert groups(devices, [DEVICE], at_least=1_000_000, limit=1_000, show=1_000) == []
    assert len(important(devices, [DEVICE], limit=1_000)) == 11
    assert len(between(devices, [DEVICE], limit=1_000, sample=1_000, seed=2**31 - 1)) == 11
    assert len(connection(devices, (DEVICE, "d1"), (DEVICE, "d3"), max_hops=10)) == 4
    for call in (
        lambda: groups(devices, [DEVICE], limit=1_001),
        lambda: groups(devices, [DEVICE], show=1_001),
        lambda: important(devices, [DEVICE], limit=1_001),
        lambda: between(devices, [DEVICE], sample=1_001),
        lambda: between(devices, [DEVICE], seed=0),
        lambda: between(devices, [DEVICE], seed=2**31),
        lambda: connection(devices, (DEVICE, "d1"), (DEVICE, "d3"), max_hops=11),
    ):
        with pytest.raises(ValueError, match="whole number"):
            call()


@pytest.mark.parametrize(
    "reference",
    [None, 7, (DEVICE,), (DEVICE, "d1", "d2"), ("Device", "d1"), (DEVICE, None), (DEVICE, 1.5)]
    + [(DEVICE, "a\x00b"), (DEVICE, ""), ("State", "s1"), ("Agent", "a1"), [DEVICE, "d1"]],
)
def test_reference_of_a_wrong_form_is_refused(devices, reference):
    with pytest.raises(ValueError, match="start: not a reference"):
        connection(devices, reference, (DEVICE, "d1"))
    with pytest.raises(ValueError, match="end: not a reference"):
        connection(devices, (DEVICE, "d1"), reference)
