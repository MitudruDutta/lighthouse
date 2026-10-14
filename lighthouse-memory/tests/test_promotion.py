"""Promotion: what repeats in episodes that ended becomes lessons and playbooks, by a rule
of the application, and nothing is written twice."""

import pytest
from devices import DEVICE, count, row, when, write

from lighthouse import (
    close_episode,
    lesson,
    open_episode,
    playbook,
    playbooks_for,
    promote,
    ran,
    record,
    retire,
    switch,
)

FAN = {"do": "check the fan"}
DOOR = {"do": "open the door"}


@pytest.fixture
def graph(graph):
    write(graph, row(key="d1"), row(key="d2"))
    return graph


def overheat(graph, name, cause, fixed_by=None, device="d1", minute=1, used=None) -> str:
    """One episode that ended: a device was hot, `cause` was found, and `fixed_by` (a
    step) fixed it or nothing did. `used` names a playbook that ran in it."""
    open_episode(graph, name, by="watcher", about=[(DEVICE, device)], at=when(minute))
    record(graph, name, "observation", by="watcher", values={"status": "hot"}, at=when(minute))
    if used:
        record(graph, name, "action", by="watcher", values={"playbook": used}, at=when(minute))
    outcome = {"cause": cause, "fixed": fixed_by is not None, "device": device}
    if fixed_by:
        outcome["step"] = fixed_by["do"]
    close_episode(graph, name, by="reviewer", outcome=outcome, at=when(minute + 1))
    return name


def rule(found: dict) -> list[dict]:
    """The rule of this test application: a lesson about the cause, a playbook of what
    fixed it, and the result of a playbook that ran."""
    outcome = found["entries"][-1]
    device, claims = outcome["device"], []
    claims.append(
        {
            "lesson": f"{device}-fan",
            "statement": f"{device} gets hot because of its fan",
            "about": [(DEVICE, device)],
            "agrees": outcome["cause"] == "fan",
        }
    )
    if outcome["fixed"]:
        steps = [{"do": outcome["step"]}]
        claims.append(
            {
                "playbook": f"cool-{device}",
                "trigger": {"status": "hot", "device": device},
                "steps": steps,
            }
        )
    for entry in found["entries"]:
        if entry["type"] == "action":
            claims.append({"ran": entry["playbook"], "succeeded": outcome["fixed"]})
    return claims


# --- lessons ------------------------------------------------------------------------------


def test_lesson_waits_for_enough_episodes_and_is_then_learned_from_them(graph):
    overheat(graph, "e1", "fan", minute=1)
    overheat(graph, "e2", "fan", minute=3)
    done = promote(graph, "reviewer", rule)
    assert done["episodes"] == 2
    assert done["lessons"] == [{"id": "d1-fan", "status": "waiting", "for": 2}]
    assert lesson(graph, "d1-fan") is None
    overheat(graph, "e3", "fan", minute=5)
    done = promote(graph, "reviewer", rule)
    assert done["lessons"] == [{"id": "d1-fan", "status": "learned", "new": 0}]
    learned = lesson(graph, "d1-fan")
    assert (learned["statement"], learned["by"], learned["weight"]) == (
        "d1 gets hot because of its fan",
        "reviewer",
        3,
    )
    assert learned["supported_by"] == ["e1", "e2", "e3"] and learned["about"] == [("Device", "d1")]


def test_episodes_that_disagree_weigh_against_the_lesson(graph):
    overheat(graph, "e0", "dust", minute=0)  # before the lesson is learned
    for n in range(1, 4):
        overheat(graph, f"e{n}", "fan", minute=2 * n)
    assert promote(graph, "reviewer", rule)["lessons"] == [
        {"id": "d1-fan", "status": "learned", "new": 1}
    ]
    assert (lesson(graph, "d1-fan")["contradicted_by"], lesson(graph, "d1-fan")["weight"]) == (
        ["e0"],
        2,
    )
    overheat(graph, "e9", "dust", minute=20)  # after it
    assert promote(graph, "reviewer", rule)["lessons"] == [
        {"id": "d1-fan", "status": "weighed", "new": 1}
    ]
    found = lesson(graph, "d1-fan")
    assert (found["contradicted_by"], found["supported_by"], found["weight"]) == (
        ["e0", "e9"],
        ["e1", "e2", "e3"],
        1,
    )


def test_lesson_that_episodes_only_contradict_is_never_learned(graph):
    for n in range(4):
        overheat(graph, f"e{n}", "dust", minute=2 * n)
    assert promote(graph, "reviewer", rule)["lessons"] == [
        {"id": "d1-fan", "status": "waiting", "for": 0}
    ]
    assert lesson(graph, "d1-fan") is None


def test_lessons_of_two_entities_are_apart(graph):
    for n in range(3):
        overheat(graph, f"a{n}", "fan", device="d1", minute=2 * n)
        overheat(graph, f"b{n}", "dust", device="d2", minute=2 * n + 1)
    done = promote(graph, "reviewer", rule)
    assert sorted((item["id"], item["status"]) for item in done["lessons"]) == [
        ("d1-fan", "learned"),
        ("d2-fan", "waiting"),
    ]


def test_lesson_about_something_that_does_not_exist_is_refused_and_the_rest_goes_on(graph):
    for n in range(3):
        overheat(graph, f"e{n}", "fan", minute=2 * n)

    def also_a_ghost(found):
        ghost = {
            "lesson": "ghost",
            "statement": "a ghost",
            "about": [(DEVICE, "nope")],
            "agrees": True,
        }
        return [ghost, *rule(found)]

    done = promote(graph, "reviewer", also_a_ghost)
    by_id = {item["id"]: item for item in done["lessons"]}
    assert by_id["d1-fan"]["status"] == "learned"
    assert (by_id["ghost"]["status"], by_id["ghost"]["reason"]) == (
        "missing",
        "an episode it rests on does not exist or has not ended",
    )
    assert lesson(graph, "ghost") is None


# --- playbooks ----------------------------------------------------------------------------


def test_playbook_is_written_when_enough_episodes_show_the_same_steps(graph):
    overheat(graph, "e1", "fan", fixed_by=FAN, minute=1)
    overheat(graph, "e2", "fan", fixed_by=FAN, minute=3)
    overheat(graph, "e3", "fan", minute=5)  # not fixed: it shows no steps
    assert promote(graph, "reviewer", rule)["playbooks"] == [
        {"id": "cool-d1", "status": "waiting", "for": 2}
    ]
    overheat(graph, "e4", "fan", fixed_by=FAN, minute=7)
    assert promote(graph, "reviewer", rule)["playbooks"] == [
        {"id": "cool-d1#1", "version": 1, "status": "written"}
    ]
    written = playbook(graph, "cool-d1")
    assert (written["trigger"], written["steps"], written["supported_by"]) == (
        {"status": "hot", "device": "d1"},
        [FAN],
        ["e1", "e2", "e4"],
    )
    assert [found["id"] for found in playbooks_for(graph, {"status": "hot", "device": "d1"})] == [
        "cool-d1#1"
    ]


def test_playbook_gets_a_new_version_when_more_episodes_show_other_steps(graph):
    for n in range(3):
        overheat(graph, f"f{n}", "fan", fixed_by=FAN, minute=2 * n)
    promote(graph, "reviewer", rule)
    for n in range(3):
        overheat(graph, f"g{n}", "door", fixed_by=DOOR, minute=10 + 2 * n)
    # Three and three: the first in the order of their text stays.
    assert promote(graph, "reviewer", rule)["playbooks"] == [
        {"id": "cool-d1#1", "status": "unchanged"}
    ]
    overheat(graph, "g3", "door", fixed_by=DOOR, minute=20)
    assert promote(graph, "reviewer", rule)["playbooks"] == [
        {"id": "cool-d1#2", "version": 2, "status": "written"}
    ]
    newest = playbook(graph, "cool-d1")
    assert (newest["steps"], newest["supported_by"], newest["enabled"]) == (
        [DOOR],
        ["g0", "g1", "g2", "g3"],
        True,
    )
    assert playbook(graph, "cool-d1", version=1)["enabled"] is False
    assert promote(graph, "reviewer", rule)["playbooks"] == [
        {"id": "cool-d1#2", "status": "unchanged"}
    ]


def test_playbook_that_was_switched_off_is_not_written_again_with_the_same_steps(graph):
    for n in range(3):
        overheat(graph, f"f{n}", "fan", fixed_by=FAN, minute=2 * n)
    promote(graph, "reviewer", rule)
    switch(graph, "cool-d1", "operator", on=False)
    overheat(graph, "f3", "fan", fixed_by=FAN, minute=10)
    assert promote(graph, "reviewer", rule)["playbooks"] == [
        {"id": "cool-d1#1", "status": "unchanged"}
    ]
    assert playbook(graph, "cool-d1")["enabled"] is False


def test_steps_with_a_null_value_are_the_same_steps(graph):
    for n in range(3):
        overheat(graph, f"f{n}", "fan", fixed_by=FAN, minute=2 * n)

    def with_null(found):
        return [
            claim
            | {"trigger": claim["trigger"] | {"note": None}}
            | {"steps": [step | {"note": None} for step in claim["steps"]]}
            if "playbook" in claim
            else claim
            for claim in rule(found)
        ]

    promote(graph, "reviewer", rule)
    assert promote(graph, "reviewer", with_null)["playbooks"] == [
        {"id": "cool-d1#1", "status": "unchanged"}
    ]


# --- runs ---------------------------------------------------------------------------------


def test_run_of_a_playbook_is_judged_once(graph):
    for n in range(3):
        overheat(graph, f"f{n}", "fan", fixed_by=FAN, minute=2 * n)
    promote(graph, "reviewer", rule)
    overheat(graph, "r1", "fan", fixed_by=FAN, minute=10, used="cool-d1")
    ran(graph, "cool-d1", "watcher", "r1")  # the agent recorded the run; how it went is not known
    overheat(graph, "r2", "dust", minute=12, used="cool-d1")  # a run that nobody recorded
    runs = promote(graph, "reviewer", rule)["runs"]
    assert [(run["id"], run["status"]) for run in runs] == [
        ("cool-d1#1", "judged"),
        ("cool-d1#1", "recorded"),
    ]
    found = playbook(graph, "cool-d1")
    assert (found["runs"], found["succeeded"], found["failed"]) == (2, 1, 1)
    assert [run["status"] for run in promote(graph, "reviewer", rule)["runs"]] == [
        "exists",
        "exists",
    ]
    assert playbook(graph, "cool-d1")["runs"] == 2


def test_run_of_a_playbook_that_does_not_exist_is_refused(graph):
    overheat(graph, "r1", "fan", minute=1, used="nope")
    (refused,) = promote(graph, "reviewer", rule)["runs"]
    assert refused["status"] == "unknown"


def test_playbook_that_fails_again_and_again_switches_itself_off(graph):
    for n in range(3):
        overheat(graph, f"f{n}", "fan", fixed_by=FAN, minute=2 * n)
    promote(graph, "reviewer", rule)
    for n in range(3):
        overheat(graph, f"r{n}", "dust", minute=10 + 2 * n, used="cool-d1")
    promote(graph, "reviewer", rule)
    assert (playbook(graph, "cool-d1")["failed"], playbook(graph, "cool-d1")["enabled"]) == (
        3,
        False,
    )


# --- what is read, and how often ------------------------------------------------------------


def test_open_episodes_are_not_read(graph):
    for n, name in enumerate(("z", "a", "m")):
        overheat(graph, name, "fan", minute=2 * n)
    open_episode(graph, "open", by="watcher", about=[(DEVICE, "d1")])
    seen = []
    assert promote(graph, "reviewer", lambda found: seen.append(found["id"]) or [])["episodes"] == 3
    assert seen == ["z", "a", "m"]  # in the order they ended


def test_second_promotion_writes_nothing(graph):
    for n in range(4):
        overheat(graph, f"e{n}", "fan" if n else "dust", fixed_by=FAN if n else None, minute=2 * n)
    promote(graph, "reviewer", rule)
    edges = count(graph, "()-[e]->()", "e")
    nodes = count(graph, "(n)")
    again = promote(graph, "reviewer", rule)
    assert again["lessons"] == [{"id": "d1-fan", "status": "unchanged", "new": 0}]
    assert again["playbooks"] == [{"id": "cool-d1#1", "status": "unchanged"}]
    assert (count(graph, "(n)"), count(graph, "()-[e]->()", "e")) == (nodes, edges)


def test_more_episodes_than_a_lesson_can_rest_on(graph):
    for n in range(203):
        overheat(graph, f"e{n:03}", "fan", fixed_by=FAN, minute=n * 2)
    done = promote(graph, "reviewer", rule, at_least=150)
    assert done["lessons"] == [{"id": "d1-fan", "status": "learned", "new": 3}]
    assert done["playbooks"][0]["status"] == "written"
    assert lesson(graph, "d1-fan")["support"] == 203  # 200 at first, and 3 more
    assert len(playbook(graph, "cool-d1")["supported_by"]) == 200


def test_at_least_one_episode_can_be_enough(graph):
    overheat(graph, "e1", "fan", fixed_by=FAN)
    done = promote(graph, "reviewer", rule, at_least=1)
    assert done["lessons"][0]["status"] == "learned" and done["playbooks"][0]["status"] == "written"


# --- what is refused ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "claims",
    [
        None,
        {"lesson": "x"},
        "lesson",
        [None],
        [{}],
        [{"lesson": "x", "playbook": "y", "statement": "s", "agrees": True}],
        [{"lesson": "x", "statement": "s"}],
        [{"lesson": "x", "statement": "s", "agrees": "yes"}],
        [{"lesson": "x", "statement": "s", "agrees": True, "weight": 9}],
        [{"playbook": "p", "trigger": {"a": 1}}],
        [{"ran": "p", "succeeded": None}],
        [{"ran": "p", "succeeded": 1}],
        [{"ran": "p"}],
    ],
)
def test_rule_that_says_something_else_stops_the_promotion_before_it_writes(graph, claims):
    for n in range(3):
        overheat(graph, f"e{n}", "fan", fixed_by=FAN, minute=2 * n)
    nodes = count(graph, "(n)")

    def broken(found):
        return rule(found) if found["id"] != "e2" else claims  # the last one is wrong

    with pytest.raises((TypeError, ValueError), match="claim"):
        promote(graph, "reviewer", broken)
    assert count(graph, "(n)") == nodes and lesson(graph, "d1-fan") is None


def test_rule_that_fails_stops_the_promotion(graph):
    overheat(graph, "e1", "fan")

    def failing(found):
        raise KeyError("outcome")

    with pytest.raises(KeyError):
        promote(graph, "reviewer", failing)


@pytest.mark.parametrize("by", [None, "", 7, " r"])
def test_writer_must_be_named(graph, by):
    with pytest.raises(ValueError, match="by must be text"):
        promote(graph, by, rule)


@pytest.mark.parametrize("at_least", [0, -1, 201, 1.5, "3", True])
def test_number_of_episodes_needed_is_checked(graph, at_least):
    with pytest.raises(ValueError, match="at_least must be a whole number"):
        promote(graph, "reviewer", rule, at_least=at_least)


def test_rule_must_be_a_function(graph):
    with pytest.raises(TypeError, match="rule must be a function"):
        promote(graph, "reviewer", [])


def test_playbook_that_is_refused_says_which_it_was(graph):
    for n in range(3):
        overheat(graph, f"f{n}", "fan", fixed_by=FAN, minute=2 * n)

    def no_steps(found):
        return [claim | {"steps": []} if "playbook" in claim else claim for claim in rule(found)]

    (refused,) = promote(graph, "reviewer", no_steps)["playbooks"]
    assert (refused["id"], refused["status"]) == ("cool-d1", "invalid")
    assert playbook(graph, "cool-d1") is None


def test_lesson_that_is_retired_is_not_weighed_and_says_so(graph):
    for n in range(3):
        overheat(graph, f"e{n}", "fan", minute=2 * n)
    promote(graph, "reviewer", rule)
    retire(graph, "d1-fan", "operator", "the fan was replaced")
    overheat(graph, "e9", "fan", minute=20)
    (refused,) = promote(graph, "reviewer", rule)["lessons"]
    assert (refused["id"], refused["status"]) == ("d1-fan", "retired")
    assert lesson(graph, "d1-fan")["support"] == 3
