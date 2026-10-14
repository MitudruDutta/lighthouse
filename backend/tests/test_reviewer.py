"""The Reviewer: overloads that ended become lessons and playbooks, the Watcher uses them at
the next overload, and the next review says whether they were right."""

import json

import lighthouse
import pytest
from feed import poll, record, when
from lighthouse import close_episode, episode, handoffs_for, lesson, open_episode, playbook
from lighthouse.episodes import ended

from app.portcalls import BERTH
from app.reviewer import review, rule
from app.watcher import SITUATION, watch

VC2, VA8, VB1 = "FIHEL/VUOS/VC2", "FIHEL/VUOS/VA8", "FIHEL/VUOS/VB1"
TAKES = f"{SITUATION}:{VC2}:takes-them"
TURNS = f"{SITUATION}:{VC2}:turns-them-away"
MOVE = f"{SITUATION}:{VC2}:move-to:{VA8}"


def call(id, minute, berth="VC2", **times) -> dict:
    return record(id=id, minute=minute, imo=9000000 + id, berth=berth, **times)


def overload(graph, n, ending="VA8") -> str:
    """Overload number n at VC2: two port calls, seen by the Watcher, then the second one
    moves to the berth `ending`, or both arrive when `ending` is None. Returns its episode."""
    minute, start, first, second = 10 * n, 10_000 * n + 600, 100 * n + 1, 100 * n + 2
    poll(graph, minute, call(first, minute, eta=start, etd=start + 300))
    poll(graph, minute, call(second, minute, eta=start + 100, etd=start + 400))
    (seen,) = watch(graph, when(minute + 1))
    assert seen["did"] == "opened"
    if ending is None:  # both come now and leave soon: the berth takes them
        for key, eta in ((first, start), (second, start + 100)):
            late = {"eta": eta, "ata": minute + 2, "etd": minute + 300}
            poll(graph, minute + 2, call(key, minute + 2, **late))
    else:
        poll(
            graph,
            minute + 2,
            call(second, minute + 2, eta=start + 100, etd=start + 400, berth=ending),
        )
    (cleared,) = watch(graph, when(minute + 3))
    assert (cleared["did"], cleared["episode"]) == ("cleared", seen["episode"])
    return seen["episode"]


def statuses(found: dict, kind: str) -> dict:
    return {receipt["id"]: receipt["status"] for receipt in found[kind]}


def test_outcome_of_an_overload_says_where_its_port_calls_went(graph):
    name = overload(graph, 0)
    outcome = episode(graph, name)["entries"][-1]
    assert (outcome["held"], outcome["moved_to"]) == (False, [VA8])
    held = overload(graph, 1, ending=None)
    outcome = episode(graph, held)["entries"][-1]
    assert (outcome["held"], outcome["moved_to"]) == (True, [])


def test_three_overloads_that_ended_alike_become_a_lesson_and_a_playbook(graph):
    for n in range(2):
        overload(graph, n)
    found = review(graph)
    assert found["episodes"] == 2
    assert statuses(found, "lessons") == {TAKES: "waiting", TURNS: "waiting"}
    assert statuses(found, "playbooks") == {MOVE: "waiting"}
    overload(graph, 2)
    found = review(graph)
    assert statuses(found, "lessons") == {TAKES: "waiting", TURNS: "learned"}
    assert statuses(found, "playbooks") == {f"{MOVE}#1": "written"}
    learned = lesson(graph, TURNS)
    assert learned["statement"] == (
        f"When more ships are expected at {VC2} than were seen there together, "
        "not all of them come: port calls are moved or retimed."
    )
    assert (learned["weight"], learned["about"]) == (3, [("Berth", VC2)])
    written = playbook(graph, MOVE)
    assert written["trigger"] == {"situation": SITUATION, "berth": VC2}
    assert written["steps"] == [{"do": "propose another berth", "berth": VA8}]
    assert (written["by"], len(written["supported_by"])) == ("reviewer", 3)


def test_next_overload_follows_the_playbook_and_the_review_says_it_was_right(graph):
    for n in range(3):
        overload(graph, n)
    review(graph)
    name = overload(graph, 3)  # the port moves it to VA8 again
    entries = episode(graph, name)["entries"]
    assert [entry["type"] for entry in entries] == [
        "observation",
        "recall",
        "action",
        "action",
        "outcome",
    ]
    recalled, proposed = entries[1], entries[2]
    assert (recalled["lesson"], recalled["weight"]) == (TURNS, 3)
    assert proposed["playbook"] == f"{MOVE}#1"
    assert json.loads(proposed["does"]) == {"do": "propose another berth", "berth": VA8}
    asks = [handoff["ask"] for handoff in handoffs_for(graph, "desk")]
    assert asks[-1].endswith(f"says: berth {VA8}, do propose another berth")
    found = review(graph)
    assert [(run["id"], run["status"]) for run in found["runs"]] == [(f"{MOVE}#1", "judged")]
    assert statuses(found, "lessons") == {TAKES: "waiting", TURNS: "weighed"}
    used = playbook(graph, MOVE)
    assert (used["runs"], used["succeeded"], used["failed"]) == (1, 1, 0)
    # Four episodes support it. It was used once; whether that helped is not said.
    assert (lesson(graph, TURNS)["support"], lesson(graph, TURNS)["used"]) == (4, 1)
    assert review(graph)["runs"][0]["status"] == "exists"


def test_playbook_that_proposed_the_wrong_berth_is_judged_to_have_failed(graph):
    for n in range(3):
        overload(graph, n)
    review(graph)
    overload(graph, 3, ending="VB1")  # this time the port moved it elsewhere
    found = review(graph)
    assert [run["status"] for run in found["runs"]] == ["judged"]
    assert (playbook(graph, MOVE)["succeeded"], playbook(graph, MOVE)["failed"]) == (0, 1)
    assert statuses(found, "playbooks") == {
        f"{MOVE}#1": "unchanged",
        f"{SITUATION}:{VC2}:move-to:{VB1}": "waiting",
    }


def test_berth_that_takes_them_contradicts_what_was_learned(graph):
    for n in range(3):
        overload(graph, n)
    review(graph)
    overload(graph, 3, ending=None)
    found = review(graph)
    assert statuses(found, "lessons") == {TAKES: "waiting", TURNS: "weighed"}
    assert lesson(graph, TURNS)["contradicted_by"] == [episode_of(graph, 3)]


def episode_of(graph, n) -> str:
    """The episode of overload number n: the Watcher opened it at minute 10 n + 1."""
    (found,) = [name for name in ended(graph) if name.endswith(f"T10:{10 * n + 1:02}:00")]
    return found


# --- the rule ---------------------------------------------------------------------------


def ended_overload(graph, outcome: dict, name=f"{SITUATION}:{VC2}:x") -> dict:
    poll(graph, 0, call(1, 0, eta=600, etd=900))
    open_episode(graph, name, by="watcher", about=[(BERTH, VC2)])
    lighthouse.record(graph, name, "observation", by="watcher", values={"berth": VC2})
    close_episode(graph, name, by="watcher", outcome=outcome)
    return episode(graph, name)


def test_rule_reads_only_overloads_that_ended_with_an_outcome_it_knows(graph):
    other = ended_overload(graph, {"held": False, "moved_to": [VA8]}, name="inspection:VC2")
    assert rule(other) == []
    assert rule(ended_overload(graph, {"cleared": True}, name=f"{SITUATION}:a")) == []
    assert rule(ended_overload(graph, {"held": "no"}, name=f"{SITUATION}:b")) == []
    claims = rule(ended_overload(graph, {"held": True}, name=f"{SITUATION}:c"))
    assert [(claim["lesson"], claim["agrees"]) for claim in claims] == [
        (TAKES, True),
        (TURNS, False),
    ]


def test_rule_has_short_ids_for_long_berth_codes(graph):
    long_berth = "B" * 190
    claims = rule(
        {
            "id": f"{SITUATION}:x",
            "entries": [
                {"type": "observation", "berth": long_berth},
                {"type": "outcome", "held": False, "moved_to": ["C" * 190]},
            ],
        }
    )
    assert all(len(claim.get("lesson", claim.get("playbook", ""))) <= 200 for claim in claims)
    assert len({claim.get("lesson", claim.get("playbook")) for claim in claims}) == 3


def test_rule_of_an_episode_without_entries_says_nothing():
    assert rule({"id": f"{SITUATION}:x", "entries": []}) == []
    assert rule({"id": f"{SITUATION}:x", "entries": [{"type": "outcome", "held": True}]}) == []


@pytest.mark.parametrize("held", [True, False])
def test_overload_that_ended_without_a_move_gives_no_playbook(graph, held):
    claims = rule(ended_overload(graph, {"held": held, "moved_to": []}))
    assert not [claim for claim in claims if "playbook" in claim]
