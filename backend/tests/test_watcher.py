"""The Watcher: it sees an overload, acts on what memory says, and closes what is over."""

import json

import pytest
from feed import failures, poll, record, when
from lighthouse import (
    claim,
    close_episode,
    episode,
    episodes_about,
    handoffs_for,
    learn,
    lesson,
    open_episode,
    playbook,
    ran,
    write_playbook,
)

from app.portcalls import BERTH, PORT_CALL
from app.watcher import SITUATION, watch

VC2 = "FIHEL/VUOS/VC2"


def call(id, minute=0, berth="VC2", **times) -> dict:
    return record(id=id, minute=minute, imo=9000000 + id, berth=berth, **times)


def look(graph, minute) -> list[dict]:
    return watch(graph, when(minute))


def entries(graph, name) -> list[dict]:
    return episode(graph, name)["entries"]


@pytest.fixture
def overloaded(graph):
    """Two port calls expected at VC2 from minute 700 to 900, seen at minute 5."""
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    (done,) = look(graph, 5)
    assert (done["berth"], done["did"]) == (VC2, "opened")
    graph.episode = done["episode"]
    return graph


# --- a new overload --------------------------------------------------------------------


def test_new_overload_becomes_an_episode_with_what_was_seen(overloaded):
    name = overloaded.episode
    assert name == f"{SITUATION}:{VC2}:2026-10-12T10:05:00"
    found = episode(overloaded, name)
    assert found["about"] == [("Berth", VC2), ("PortCall", 1), ("PortCall", 2)]
    assert (found["by"], found["opened_at"]) == ("watcher", when(5))
    seen, acted = found["entries"]
    assert {k: seen[k] for k in ("type", "by", "at")} == {
        "type": "observation",
        "by": "watcher",
        "at": when(5),
    }
    assert {
        k: v for k, v in seen.items() if k not in ("id", "seq", "type", "by", "at", "recorded_at")
    } == {
        "situation": "berth-overload",
        "berth": VC2,
        "ongoing": False,
        "from": "2026-10-12T21:40:00",
        "until": "2026-10-13T01:00:00",
        "expected": 2,
        "capacity": 1,
        "calls": [1, 2],
        "together": [],
        "cites": [("Berth", VC2), ("PortCall", 1), ("PortCall", 2)],
    }
    assert acted["type"] == "action" and failures(overloaded) == []


def test_without_a_playbook_the_desk_gets_a_task_and_the_episode(overloaded):
    name = overloaded.episode
    acted = entries(overloaded, name)[-1]
    assert (acted["did"], acted["to"], acted["task"]) == (
        "raised a task and handed the episode over",
        "desk",
        name,
    )
    (handed,) = handoffs_for(overloaded, "desk")
    assert handed["points_to"] == [("Episode", name)] and handed["by"] == "watcher"
    assert handed["ask"] == "2 port calls are expected at a berth that held 1"
    assert claim(overloaded, "desk", SITUATION) == {
        "id": name,
        "kind": SITUATION,
        "ref": name,
        "until": None,
    }
    assert claim(overloaded, "desk", SITUATION) is None  # one task


def test_same_look_again_does_nothing(overloaded):
    before = entries(overloaded, overloaded.episode)
    assert look(overloaded, 5) == [] and look(overloaded, 60) == []
    poll(overloaded, 61, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))  # the same poll
    assert look(overloaded, 61) == []
    assert entries(overloaded, overloaded.episode) == before
    assert len(episodes_about(overloaded, BERTH, VC2)) == 1


def test_berth_without_an_overload_gets_no_episode(graph):
    poll(
        graph,
        0,
        call(1, eta=600, etd=900),
        call(2, eta=900, etd=1000),
        call(3, berth="VA8", eta=1, etd=9),
    )
    assert look(graph, 5) == []
    assert episodes_about(graph, BERTH, VC2) == []


def test_each_overloaded_berth_gets_its_own_episode(graph):
    poll(
        graph,
        0,
        call(1, eta=600, etd=900),
        call(2, eta=700, etd=1000),
        call(3, eta=600, etd=900, berth="VA8"),
        call(4, eta=700, etd=1000, berth="VA8"),
        call(5, eta=600, etd=900, berth="VB1"),
    )
    done = look(graph, 5)
    assert [(d["berth"], d["did"]) for d in done] == [
        ("FIHEL/VUOS/VA8", "opened"),
        (VC2, "opened"),
    ]
    assert episode(graph, done[0]["episode"])["about"] == [
        ("Berth", "FIHEL/VUOS/VA8"),
        ("PortCall", 3),
        ("PortCall", 4),
    ]
    assert len(handoffs_for(graph, "desk")) == 2


def test_expected_is_the_most_at_one_time_not_all_that_come(graph):
    # 1 and 2 overlap, then 2 and 3: three port calls, and never more than two at one time.
    poll(graph, 0, call(1, eta=100, etd=300), call(2, eta=200, etd=500), call(3, eta=300, etd=600))
    (done,) = look(graph, 5)
    seen = entries(graph, done["episode"])[0]
    assert (seen["calls"], seen["expected"], seen["until"]) == ([1, 2, 3], 2, "2026-10-12T18:20:00")
    assert (
        handoffs_for(graph, "desk")[0]["ask"] == "2 port calls are expected at a berth that held 1"
    )


def test_writer_is_the_one_that_is_named(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    (done,) = watch(graph, when(5), by="night-watch")
    assert {entry["by"] for entry in entries(graph, done["episode"])} == {"night-watch"}
    assert handoffs_for(graph, "desk")[0]["by"] == "night-watch"


# --- what memory says -------------------------------------------------------------------


def ended(graph, name, about=()) -> str:
    """An episode that is over, to rest a lesson or a playbook on."""
    open_episode(graph, name, by="reviewer", about=list(about))
    close_episode(graph, name, by="reviewer", outcome={"ok": True})
    return name


def test_lesson_about_the_berth_is_written_into_the_episode_and_counted_as_used(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    proof = ended(graph, "past", [(BERTH, VC2)])
    learn(graph, "vc2-is-short", "reviewer", "VC2 takes one ship", [proof], [(BERTH, VC2)])
    learn(graph, "other", "reviewer", "about another berth", [proof], [(PORT_CALL, 1)])
    (done,) = look(graph, 5)
    seen, recalled, acted = entries(graph, done["episode"])
    assert (seen["type"], recalled["type"], acted["type"]) == ("observation", "recall", "action")
    assert (recalled["lesson"], recalled["statement"], recalled["weight"]) == (
        "vc2-is-short",
        "VC2 takes one ship",
        1,
    )
    assert recalled["cites"] == [("Lesson", "vc2-is-short")]
    assert lesson(graph, "vc2-is-short")["used"] == 1 and lesson(graph, "other")["used"] == 0
    assert look(graph, 6) == [] and lesson(graph, "vc2-is-short")["used"] == 1


def test_playbook_for_the_situation_is_followed_and_its_run_recorded(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    steps = [{"do": "ask the later ship to slow down"}, {"do": "tell the pilot", "within": 30}]
    write_playbook(
        graph,
        "overload",
        "reviewer",
        {"situation": SITUATION},
        steps,
        [ended(graph, "past")],
        needs=1,
    )
    (done,) = look(graph, 5)
    seen, first, second, handed = entries(graph, done["episode"])
    assert (seen["type"], handed["did"]) == (
        "observation",
        "raised a task and handed the episode over",
    )
    assert (first["type"], first["playbook"], first["step"]) == ("action", "overload#1", 1)
    assert json.loads(first["does"]) == {"do": "ask the later ship to slow down"}
    assert (
        json.loads(second["does"]) == {"do": "tell the pilot", "within": 30} and second["step"] == 2
    )
    assert first["cites"] == [("Playbook", "overload#1")]
    assert playbook(graph, "overload")["runs"] == 1
    # The Watcher cannot do the steps itself: the desk gets them with the episode.
    (handoff,) = handoffs_for(graph, "desk")
    assert handoff["ask"] == (
        "2 port calls are expected at a berth that held 1. The playbook overload#1 says: "
        "do ask the later ship to slow down; do tell the pilot, within 30"
    )
    assert claim(graph, "desk", SITUATION)["id"] == done["episode"]
    assert look(graph, 6) == [] and playbook(graph, "overload")["runs"] == 1


def test_only_the_heaviest_lessons_are_recalled(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    proofs = [ended(graph, f"past-{n}", [(BERTH, VC2)]) for n in range(4)]
    for n in range(4):  # lesson n rests on n + 1 episodes
        learn(graph, f"lesson-{n}", "reviewer", f"said {n}", proofs[: n + 1], [(BERTH, VC2)])
    (done,) = look(graph, 5)
    recalled = [entry for entry in entries(graph, done["episode"]) if entry["type"] == "recall"]
    assert [(entry["lesson"], entry["weight"]) for entry in recalled] == [
        ("lesson-3", 4),
        ("lesson-2", 3),
        ("lesson-1", 2),
    ]
    assert lesson(graph, "lesson-0")["used"] == 0


def test_playbook_with_the_best_record_is_the_one_that_is_followed(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    proof = ended(graph, "past")
    for name in ("alpha", "beta"):
        write_playbook(
            graph, name, "reviewer", {"situation": SITUATION}, [{"do": name}], [proof], needs=1
        )
    ran(graph, "alpha", "reviewer", proof, succeeded=False)  # alpha failed once
    (done,) = look(graph, 5)
    acted = entries(graph, done["episode"])[-2]
    assert (acted["playbook"], json.loads(acted["does"])) == ("beta#1", {"do": "beta"})
    assert (playbook(graph, "beta")["runs"], playbook(graph, "alpha")["runs"]) == (1, 1)


def test_open_episode_of_another_agent_about_the_berth_is_left_alone(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    open_episode(graph, "inspection", by="harbour-master", about=[(BERTH, VC2)])
    (done,) = look(graph, 5)
    assert done["did"] == "opened" and done["episode"] != "inspection"
    assert entries(graph, "inspection") == [] and look(graph, 6) == []
    poll(graph, 30, call(2, minute=30, eta=950, etd=1000))
    assert look(graph, 31) == [{"berth": VC2, "episode": done["episode"], "did": "cleared"}]
    assert [ep["id"] for ep in episodes_about(graph, BERTH, VC2) if ep["outcome"] is None] == [
        "inspection"
    ]


def test_playbook_for_another_port_does_not_fit(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    proof = ended(graph, "past")
    for name, port in (("kotka", "FIKTK"), ("helsinki", "FIHEL")):
        trigger = {"situation": SITUATION, "port": port}
        write_playbook(graph, name, "reviewer", trigger, [{"do": name}], [proof], needs=1)
    (done,) = look(graph, 5)
    acted = entries(graph, done["episode"])[-2]
    assert (acted["playbook"], json.loads(acted["does"])) == ("helsinki#1", {"do": "helsinki"})
    assert playbook(graph, "kotka")["runs"] == 0


# --- an overload that goes on ------------------------------------------------------------


def test_overload_that_changes_gets_one_more_observation(overloaded):
    name = overloaded.episode
    poll(overloaded, 10, call(3, minute=10, eta=750, etd=800))  # a third port call
    assert look(overloaded, 11) == [{"berth": VC2, "episode": name, "did": "updated"}]
    last = entries(overloaded, name)[-1]
    assert (last["type"], last["calls"], last["expected"], last["from"], last["until"]) == (
        "observation",
        [1, 2, 3],
        3,
        "2026-10-12T21:40:00",
        "2026-10-13T01:00:00",
    )
    assert last["cites"] == [("Berth", VC2), ("PortCall", 1), ("PortCall", 2), ("PortCall", 3)]
    poll(overloaded, 20, call(2, minute=20, eta=650, etd=1000))  # the second comes earlier
    assert [d["did"] for d in look(overloaded, 21)] == ["updated"]
    last = entries(overloaded, name)[-1]
    assert (last["from"], last["until"], last["calls"]) == (
        "2026-10-12T20:50:00",
        "2026-10-13T01:00:00",
        [1, 2, 3],
    )
    assert look(overloaded, 22) == []
    poll(overloaded, 25, call(1, minute=25, eta=600, etd=960))  # the first stays longer
    assert [d["did"] for d in look(overloaded, 26)] == ["updated"]
    last = entries(overloaded, name)[-1]
    assert (last["from"], last["until"]) == ("2026-10-12T20:50:00", "2026-10-13T02:00:00")
    assert look(overloaded, 27) == []
    assert len(episodes_about(overloaded, BERTH, VC2)) == 1  # still the one episode
    assert len(handoffs_for(overloaded, "desk")) == 1  # and it acted once


def test_overload_that_has_begun_is_not_written_again_at_every_look(overloaded):
    name = overloaded.episode
    assert [d["did"] for d in look(overloaded, 750)] == ["updated"]  # it began at minute 700
    last = entries(overloaded, name)[-1]
    assert (last["ongoing"], last["from"]) == (True, "2026-10-12T22:30:00")
    count = len(entries(overloaded, name))
    for minute in (760, 800, 850):
        assert look(overloaded, minute) == []
    assert len(entries(overloaded, name)) == count


# --- an overload that is over ----------------------------------------------------------


def outcome(graph, name) -> dict:
    (found,) = [ep for ep in episodes_about(graph, BERTH, VC2) if ep["id"] == name]
    return found["outcome"]


def test_overload_that_is_gone_closes_its_episode_with_what_changed(overloaded):
    name = overloaded.episode
    poll(overloaded, 30, call(2, minute=30, eta=950, etd=1000))  # the second comes later
    assert look(overloaded, 31) == [{"berth": VC2, "episode": name, "did": "cleared"}]
    closed = outcome(overloaded, name)
    assert (closed["type"], closed["cleared"], closed["held"], closed["capacity"]) == (
        "outcome",
        True,
        False,
        1,
    )
    assert closed["calls"] == [
        "1: expected from 2026-10-12 20:00:00+00:00 to 2026-10-13 01:00:00+00:00",
        "2: expected from 2026-10-13 01:50:00+00:00 to 2026-10-13 02:40:00+00:00",
    ]
    assert entries(overloaded, name)[-1]["cites"] == [
        ("Berth", VC2),
        ("PortCall", 1),
        ("PortCall", 2),
    ]
    assert look(overloaded, 32) == []


def test_port_call_that_moved_or_left_is_named_in_the_outcome(overloaded):
    poll(overloaded, 30, call(2, minute=30, eta=700, etd=1000, berth="VA8"))
    assert [d["did"] for d in look(overloaded, 31)] == ["cleared"]
    assert outcome(overloaded, overloaded.episode)["calls"][1] == "2: moved to FIHEL/VUOS/VA8"

    poll(overloaded, 40, call(2, minute=40, eta=700, etd=1000))  # back: a new overload
    (again,) = look(overloaded, 41)
    assert again["did"] == "opened" and again["episode"] != overloaded.episode
    poll(overloaded, 50, call(1, minute=50, eta=600, ata=605, etd=900, atd=640))
    poll(overloaded, 51, call(2, minute=51, eta=700, etd=1000, berth=None))
    assert [d["did"] for d in look(overloaded, 52)] == ["cleared"]
    assert outcome(overloaded, again["episode"])["calls"] == ["1: departed", "2: has no berth"]
    assert len(episodes_about(overloaded, BERTH, VC2)) == 2
    assert len(handoffs_for(overloaded, "desk", waiting_only=False)) == 2


def test_berth_that_held_them_all_after_all_is_said_to_have_held(overloaded):
    name = overloaded.episode
    poll(overloaded, 720, call(1, minute=720, eta=600, ata=610, etd=900))
    poll(overloaded, 721, call(2, minute=721, eta=700, ata=715, etd=1000))  # both alongside
    assert look(overloaded, 722) == [{"berth": VC2, "episode": name, "did": "cleared"}]
    closed = outcome(overloaded, name)
    assert (closed["held"], closed["capacity"]) == (True, 2)
    assert closed["calls"] == ["1: alongside", "2: alongside"]
    # The graph has seen two there: two expected at one time is no overload any more.
    poll(
        overloaded,
        730,
        call(3, minute=730, eta=1100, etd=1300),
        call(4, minute=730, eta=1200, etd=1400),
    )
    assert look(overloaded, 731) == []
    poll(overloaded, 740, call(5, minute=740, eta=1250, etd=1260))
    (third,) = look(overloaded, 741)
    assert third["did"] == "opened"
    seen = entries(overloaded, third["episode"])[0]
    assert (seen["capacity"], seen["together"], seen["calls"]) == (2, [1, 2], [3, 4, 5])
    # It cites what is expected, and the port calls that showed what the berth holds.
    assert seen["cites"] == [("Berth", VC2), *(("PortCall", key) for key in (1, 2, 3, 4, 5))]
    assert episode(overloaded, third["episode"])["about"] == [
        ("Berth", VC2),
        ("PortCall", 3),
        ("PortCall", 4),
        ("PortCall", 5),
    ]


# --- what can go wrong -------------------------------------------------------------------


def test_berth_with_a_long_code_gets_a_short_id(graph):
    code = "Q" * 180  # a key that the library takes, and too long to be part of an id
    poll(graph, 0, call(1, eta=600, etd=900, berth=code), call(2, eta=700, etd=1000, berth=code))
    (done,) = look(graph, 5)
    assert done["did"] == "opened" and len(done["episode"]) <= 200
    assert done["episode"].startswith(f"{SITUATION}:") and code not in done["episode"]
    assert episode(graph, done["episode"])["about"][0] == ("Berth", f"FIHEL/VUOS/{code}")
    assert look(graph, 6) == []
    # Another berth with a long code, overloaded in the same look, has an id of its own.
    other = "Z" * 180
    poll(graph, 7, call(3, eta=600, etd=900, berth=other), call(4, eta=700, etd=1000, berth=other))
    poll(
        graph,
        7,
        call(5, eta=600, etd=900, berth="R" * 180),
        call(6, eta=700, etd=1000, berth="R" * 180),
    )
    again = look(graph, 8)
    assert [found["did"] for found in again] == ["opened", "opened"]
    assert len({done["episode"], again[0]["episode"], again[1]["episode"]}) == 3


def test_write_that_is_refused_is_told_and_the_look_goes_on(graph, monkeypatch):
    poll(
        graph,
        0,
        call(1, eta=600, etd=900, berth="VA8"),
        call(2, eta=700, etd=1000, berth="VA8"),
        call(3, eta=600, etd=900),
        call(4, eta=700, etd=1000),
    )
    send = watch.__globals__["record"]

    def refusing(graph, name, *rest, **more):
        if "VA8" in name:
            return {"id": None, "status": "full", "reason": "the episode has 5000 entries"}
        return send(graph, name, *rest, **more)

    monkeypatch.setitem(watch.__globals__, "record", refusing)
    done = look(graph, 5)
    assert done[0] == {
        "berth": "FIHEL/VUOS/VA8",
        "episode": None,
        "did": "failed",
        "reason": "full: the episode has 5000 entries",
    }
    assert (done[1]["berth"], done[1]["did"]) == (VC2, "opened")
