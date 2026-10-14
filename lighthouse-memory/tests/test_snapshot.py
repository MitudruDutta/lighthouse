"""Algorithms at one time: over the relations that held then, each checked against a plain
implementation on what the test wrote for that time."""

import random

import pytest
from devices import DEVICE, PERSON, row, when, write
from plain import fewest_steps, linked_sets, page_rank, paths_through

from lighthouse import (
    SELF,
    Kind,
    algorithms,
    between,
    connection,
    ensure_schema,
    groups,
    important,
    open_episode,
    remember,
    snapshot,
)


@pytest.fixture
def graph(graph):
    ensure_schema(graph, [PERSON])
    return graph


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


def sets(found) -> set[frozenset]:
    return {frozenset(key for _, key in item["members"]) for item in found}


def history(graph, seed=5, size=30, times=(0, 10, 20)):
    """Random persons who know others, rewritten at each time. Returns, by time, the
    persons that existed then and who knew whom then."""
    rng = random.Random(seed)
    names = [f"p{n:02}" for n in range(size)]
    written, knows, at = set(), {}, {}
    for minute in times:
        lists = {name: rng.sample(names, rng.randint(0, 3)) for name in rng.sample(names, 20)}
        rows = [{"key": k, "t": when(minute), "relations": {"KNOWS": v}} for k, v in lists.items()]
        assert {r["status"] for r in remember(graph, PERSON, rows, by="test")} <= {
            "created",
            "changed",
            "unchanged",
        }
        written |= set(lists)
        knows |= lists
        pairs = {(a, b) for a, known in knows.items() for b in known}
        at[minute] = (written | {b for _, b in pairs}, pairs)
    return at


# --- what belongs together ------------------------------------------------------------


def test_groups_at_a_time_see_the_relations_that_held_then(devices):
    found = groups(devices, [DEVICE], ["LOCATED_IN"], at_least=1, at=when(6))
    assert sets(found) == {
        frozenset({"d1", "r9"}),
        frozenset({"d2", "r1"}),
        frozenset({"d3", "r2"}),
        frozenset({"d4", "r3"}),
    }
    later = groups(devices, [DEVICE], ["LOCATED_IN"], at_least=1, at=when(8))
    assert frozenset({"d2", "r8"}) in sets(later)
    assert all("r1" not in members for members in sets(later))  # nothing was in r1 then
    assert sets(groups(devices, [DEVICE], ["LOCATED_IN"], at=when(10))) == {
        frozenset({"d1", "r1"}),
        frozenset({"d2", "r8"}),
        frozenset({"d3", "r2"}),
        frozenset({"d4", "r3"}),
    }


def test_groups_at_a_time_match_a_plain_search(graph):
    for minute, (nodes, pairs) in history(graph).items():
        for moment in (minute, minute + 5):
            found = groups(graph, [PERSON], at_least=1, limit=1_000, show=1_000, at=when(moment))
            assert sets(found) == linked_sets(nodes, pairs), moment
            sizes = [item["size"] for item in found]
            assert sizes == sorted(sizes, reverse=True)


def test_groups_at_a_time_keep_to_the_size_limit_and_members_asked_for(devices):
    write(devices, row(key="d6", room=None, teams=[]))  # linked to nothing
    alone = groups(devices, [DEVICE], ["LOCATED_IN"], at_least=1, at=when(6))
    assert frozenset({"d6"}) in sets(alone)
    pairs = groups(devices, [DEVICE], ["LOCATED_IN"], at=when(6))
    assert {item["size"] for item in pairs} == {2} and len(pairs) == 4
    assert len(groups(devices, [DEVICE], ["LOCATED_IN"], limit=1, at=when(6))) == 1
    (shown,) = groups(devices, [DEVICE], ["LOCATED_IN"], limit=1, show=1, at=when(6))
    assert shown["size"] == 2 and len(shown["members"]) == 1


def test_entity_counts_from_its_first_state(devices):
    write(devices, row(key="d5", minute=20, room="r5"))
    assert all("d5" not in members for members in sets(groups(devices, [DEVICE], at=when(10))))
    assert frozenset({"d5", "r5"}) in sets(groups(devices, [DEVICE], ["LOCATED_IN"], at=when(20)))
    assert groups(devices, [DEVICE], at=when(-10)) == []  # before anything


def test_row_that_came_late_changes_the_answer_at_its_time(graph):
    write(graph, row(minute=0, room="r1"), row(minute=20, room="r2"))
    before = sets(groups(graph, [DEVICE], ["LOCATED_IN"], at=when(15)))
    assert before == {frozenset({"d1", "r1"})}
    # The late row says what the next State says: no node and no edge more, only times.
    assert write(graph, row(minute=10, room="r2")) == ["inserted"]
    assert sets(groups(graph, [DEVICE], ["LOCATED_IN"], at=when(15))) == {frozenset({"d1", "r2"})}


# --- what is central ------------------------------------------------------------------


def test_rank_at_a_time_matches_a_plain_computation(graph):
    for minute, (nodes, pairs) in history(graph).items():
        found = important(graph, [PERSON], limit=1_000, at=when(minute + 1))
        expected = page_rank(sorted(nodes), pairs)
        got = {key: item["score"] for item in found for _, key in [item["entity"]]}
        assert got.keys() == set(nodes)
        assert all(got[n] == pytest.approx(expected[n], abs=1e-6) for n in nodes), minute
        scores = [item["score"] for item in found]
        assert scores == sorted(scores, reverse=True)


def test_rank_at_a_time_lists_the_kinds_asked_for_up_to_the_limit(devices):
    remember(devices, PERSON, [{"key": "ann", "t": when(0), "relations": {"KNOWS": "bob"}}], by="t")
    found = important(devices, [DEVICE], limit=100, at=when(1))
    labels = {item["entity"][0] for item in found}
    assert labels == {"Device", "Room", "Team"}  # no Person, though persons are ranked too
    assert len(important(devices, [DEVICE], limit=2, at=when(1))) == 2


def test_rank_at_a_time_over_one_relation(graph):
    member = Kind("Person", key="email", relations={"KNOWS": SELF, "LEADS": SELF})
    rows = [
        {"key": "a", "t": when(0), "relations": {"KNOWS": ["b", "c"], "LEADS": ["c"]}},
        {"key": "b", "t": when(0), "relations": {"KNOWS": ["c"], "LEADS": ["a"]}},
        {"key": "c", "t": when(0), "relations": {"KNOWS": [], "LEADS": ["a"]}},
    ]
    remember(graph, member, rows, by="t")
    leads = {("a", "c"), ("b", "a"), ("c", "a")}
    expected = page_rank(["a", "b", "c"], leads)
    found = important(graph, [member], relation="LEADS", at=when(1))
    assert {key: item["score"] for item in found for _, key in [item["entity"]]} == pytest.approx(
        expected, abs=1e-6
    )


def test_rank_now_agrees_with_the_rank_of_the_database(graph):
    history(graph, times=(0,))  # nothing has ended: every relation holds
    live = {item["entity"]: item["score"] for item in important(graph, [PERSON], limit=1_000)}
    then = {
        item["entity"]: item["score"]
        for item in important(graph, [PERSON], limit=1_000, at=when(1))
    }
    assert live.keys() == then.keys()
    assert all(then[e] == pytest.approx(live[e], abs=1e-3) for e in live)


def test_paths_through_at_a_time_match_a_plain_count(graph):
    for minute, (nodes, pairs) in history(graph).items():
        found = between(graph, [PERSON], limit=1_000, at=when(minute + 1))
        expected = paths_through(sorted(nodes), pairs)
        got = {key: item["score"] for item in found for _, key in [item["entity"]]}
        assert all(got[n] == pytest.approx(expected[n]) for n in nodes), minute


def test_paths_through_now_agree_with_the_database(graph):
    history(graph, times=(0,))
    live = {item["entity"]: item["score"] for item in between(graph, [PERSON], limit=1_000)}
    then = {
        item["entity"]: item["score"] for item in between(graph, [PERSON], limit=1_000, at=when(1))
    }
    assert all(then.get(e, 0.0) == pytest.approx(score) for e, score in live.items())


def test_paths_through_from_a_sample_are_scaled_to_the_whole(graph, monkeypatch):
    history(graph, times=(0,))
    exact = between(graph, [PERSON], limit=1_000, at=when(1))
    sampled = between(graph, [PERSON], limit=1_000, sample=10, at=when(1))
    total = sum(item["score"] for item in exact)
    assert sum(item["score"] for item in sampled) == pytest.approx(total, rel=0.6)
    assert sampled == between(graph, [PERSON], limit=1_000, sample=10, at=when(1))  # same seed
    monkeypatch.setattr(snapshot, "WORK", 1)  # the work allows the fewest sources only
    monkeypatch.setattr(algorithms, "SAMPLE", 5)
    assert between(graph, [PERSON], limit=1_000, at=when(1)) != exact


# --- how two things were connected ----------------------------------------------------


def test_connection_at_a_time_is_the_chain_that_held_then(devices):
    steps = connection(devices, (DEVICE, "d1"), (DEVICE, "d2"), at=when(6))
    assert steps is None  # d1 was in r9, d2 in r1: no room and no team joined them
    steps = connection(
        devices, (DEVICE, "d1"), (DEVICE, "d2"), relations=["LOCATED_IN"], at=when(3)
    )
    assert [(s["from"], s["relation"], s["to"], s["forward"]) for s in steps] == [
        (("Device", "d1"), "LOCATED_IN", ("Room", "r1"), True),
        (("Room", "r1"), "LOCATED_IN", ("Device", "d2"), False),
    ]
    assert steps[0]["since"] == when(0) and steps[0]["until"] == when(5)
    assert steps[0]["current"] is False and steps[1]["until"] == when(7)
    assert connection(devices, (DEVICE, "d1"), (DEVICE, "d1"), at=when(3)) == []
    assert connection(devices, (DEVICE, "d1"), (DEVICE, "nobody"), at=when(3)) is None


def test_connection_at_a_time_takes_the_fewest_steps(graph):
    for minute, (nodes, pairs) in history(graph).items():
        ordered = sorted(nodes)
        for start, end in zip(ordered[::3], ordered[1::3], strict=False):
            steps = connection(
                graph, (PERSON, start), (PERSON, end), max_hops=10, at=when(minute + 1)
            )
            expected = fewest_steps(pairs, start, end)
            expected = expected if expected is not None and expected <= 10 else None
            assert (None if steps is None else len(steps)) == expected, (minute, start, end)
            if steps:
                assert steps[0]["from"] == ("Person", start) and steps[-1]["to"] == ("Person", end)


def test_step_at_a_time_tells_of_the_first_relation_by_name(graph):
    member = Kind("Person", key="email", relations={"KNOWS": SELF, "LEADS": SELF})
    rows = [
        {"key": "a", "t": when(0), "relations": {"LEADS": ["b"]}},
        {"key": "b", "t": when(0), "relations": {"KNOWS": ["a"]}},
    ]
    remember(graph, member, rows, by="t")
    (step,) = connection(graph, (member, "a"), (member, "b"), at=when(1))
    assert (step["relation"], step["forward"]) == ("KNOWS", False)


def test_connection_at_a_time_stops_at_the_steps_allowed(graph):
    remember(
        graph,
        PERSON,
        [
            {"key": k, "t": when(0), "relations": {"KNOWS": v}}
            for k, v in {"a": "b", "b": "c", "c": "d"}.items()
        ],
        by="test",
    )
    assert len(connection(graph, (PERSON, "a"), (PERSON, "d"), at=when(1))) == 3
    assert connection(graph, (PERSON, "a"), (PERSON, "d"), max_hops=2, at=when(1)) is None


# --- what is refused ------------------------------------------------------------------


def test_records_have_no_time(devices):
    open_episode(devices, "look", "eye", about=[(DEVICE, "d1")])
    with pytest.raises(ValueError, match="records"):
        groups(devices, [DEVICE], records=["Episode"], at=when(1))
    with pytest.raises(ValueError, match="records"):
        groups(devices, [DEVICE], ["ABOUT"], at=when(1))
    with pytest.raises(ValueError, match="records"):
        groups(devices, [DEVICE], ["LOCATED_IN"], records=["Episode"], at=when(1))
    with pytest.raises(ValueError, match="records"):
        connection(devices, ("Episode", "look"), (DEVICE, "d1"), at=when(1))
    with pytest.raises(ValueError, match="records"):
        connection(devices, ("Episode", "look"), (DEVICE, "d1"), relations=["ABOUT"], at=when(1))
    with pytest.raises(ValueError, match="records"):
        connection(devices, (DEVICE, "d2"), (DEVICE, "d1"), relations=["ABOUT"], at=when(1))


@pytest.mark.parametrize("at", ["", "yesterday", 5])
def test_time_of_a_wrong_form_is_refused(devices, at):
    with pytest.raises((ValueError, TypeError)):
        groups(devices, [DEVICE], at=at)


def test_more_than_one_answer_may_read_is_refused(devices, monkeypatch):
    monkeypatch.setattr(snapshot, "MOST", 3)
    with pytest.raises(ValueError, match="more than 3"):
        groups(devices, [DEVICE], at=when(1))
    with pytest.raises(ValueError, match="more than 3"):
        important(devices, [DEVICE], at=when(1))
    with pytest.raises(ValueError, match="more than 3"):  # d1, r1, d2, and on
        connection(devices, (DEVICE, "d1"), (DEVICE, "d3"), max_hops=10, at=when(1))


def test_answers_at_a_time_are_not_kept(devices, monkeypatch):
    calls = []
    read = snapshot._read
    monkeypatch.setattr(snapshot, "_read", lambda *a, **k: calls.append(1) or read(*a, **k))
    groups(devices, [DEVICE], at=when(1))
    groups(devices, [DEVICE], at=when(1))
    assert len(calls) == 2
