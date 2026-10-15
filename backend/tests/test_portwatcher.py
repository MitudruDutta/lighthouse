"""The Port Watcher: a port whose ships stop coming, or come in far greater numbers, becomes
an episode with the port as evidence; when it is back to usual the episode ends, and the
Reviewer learns whether such spells pass quickly there."""

from datetime import date, timedelta

import pytest
from lighthouse import as_of, claim, episode, handoffs_for, lesson, remember

from app import portwatcher
from app.portcalls import PORT
from app.reviewer import review

DAY0 = date(2026, 6, 1)


def day(n: int) -> str:
    return (DAY0 + timedelta(days=n)).isoformat()


def port_days(graph, key, calls, name="Test Port", start=0):
    """One row for each day from `start`: the port calls of that day."""
    rows = [
        {"key": key, "t": f"{day(start + n)}T00:00:00Z", "values": {"name": name, "calls": c}}
        for n, c in enumerate(calls)
    ]
    assert {r["status"] for r in remember(graph, PORT, rows, by="portwatch")} <= {
        "created",
        "changed",
        "unchanged",
    }


USUAL = [10, 11, 9, 10, 12, 10, 9, 11, 10, 10, 11, 9, 10, 10]  # 14 days, median 10


def test_a_quiet_day_opens_an_episode_with_the_port_as_evidence(graph):
    port_days(graph, "INNSA", USUAL + [4], name="Nhava Sheva")
    (done,) = portwatcher.watch(graph, [day(14)])
    assert (done["port"], done["day"], done["did"]) == ("INNSA", day(14), "opened")
    found = episode(graph, done["episode"])
    assert found["about"] == [("Port", "INNSA")]
    seen = found["entries"][0]
    assert (seen["type"], seen["state"], seen["calls"], seen["usual"]) == (
        "observation",
        "quiet",
        4,
        10,
    )
    assert seen["name"] == "Nhava Sheva" and seen["cites"] == [("Port", "INNSA")]
    assert seen["at"].date().isoformat() == day(14)
    # The port as the agent saw it, that day.
    assert as_of(graph, PORT, "INNSA", seen["at"])["calls"] == 4
    (handed,) = handoffs_for(graph, "desk")
    assert "4 port calls at Nhava Sheva" in handed["ask"] and "fewer" in handed["ask"]
    assert claim(graph, "desk", portwatcher.SITUATION)["id"] == done["episode"]


def test_a_busy_day_opens_an_episode_too(graph):
    port_days(graph, "CNQDG", USUAL + [25], name="Qingdao")
    (done,) = portwatcher.watch(graph, [day(14)])
    assert done["did"] == "opened"
    assert episode(graph, done["episode"])["entries"][0]["state"] == "busy"
    assert "far more" in handoffs_for(graph, "desk")[0]["ask"]


def test_a_spell_is_followed_each_day_and_ends_when_the_port_is_back(graph):
    port_days(graph, "INNSA", USUAL + [4, 3, 10])
    did = [d["did"] for d in portwatcher.watch(graph, [day(14), day(15), day(16)])]
    assert did == ["opened", "seen", "ended"]
    found = episode(graph, f"port-activity:INNSA:{day(14)}")
    assert found["closed_at"].date().isoformat() == day(16)
    outcome = found["entries"][-1]
    assert (outcome["type"], outcome["days"], outcome["back_to_usual"]) == ("outcome", 2, True)
    assert [e["calls"] for e in found["entries"] if e["type"] == "observation"] == [4, 3]


def test_a_spell_of_equal_days_is_followed_through_one_version(graph):
    port_days(graph, "INNSA", [10] * 13 + [3, 3])  # the last two days are one State
    (done,) = portwatcher.watch(graph, [day(14)])
    assert done["did"] == "opened"
    assert episode(graph, done["episode"])["entries"][0]["calls"] == 3


def test_usual_days_and_small_ports_say_nothing(graph):
    port_days(graph, "FIHEL", USUAL + [9])  # within what is usual
    port_days(graph, "FIKTK", [2] * 14 + [0])  # usually 2: an empty day is no news
    port_days(graph, "NEWPT", [10] * 5 + [1], start=9)  # too few days to know what is usual
    assert portwatcher.watch(graph, [day(14)]) == []


def test_a_day_without_numbers_and_no_days_are_nothing(graph):
    port_days(graph, "INNSA", USUAL)
    assert portwatcher.watch(graph, [day(20)]) == []  # no row for that day
    assert portwatcher.watch(graph, []) == []


def test_what_was_learned_about_a_port_is_recalled(graph):
    # Three quiet spells at one port, each over within a day: the Reviewer learns it.
    calls = []
    for _ in range(3):
        calls += USUAL + [3, 10]
    port_days(graph, "INNSA", calls)
    spells = [day(n) for n in range(len(calls))]
    portwatcher.watch(graph, spells)
    found = review(graph)
    (learned,) = found["lessons"]
    assert learned["id"] == "port-activity:INNSA:quiet:passes" and learned["status"] == "learned"
    assert lesson(graph, learned["id"])["weight"] == 3
    # The next quiet day recalls it.
    port_days(graph, "INNSA", USUAL + [2], start=len(calls))
    (done,) = portwatcher.watch(graph, [day(len(calls) + 14)])
    entries = episode(graph, done["episode"])["entries"]
    assert [e["type"] for e in entries[:2]] == ["observation", "recall"]
    assert entries[1]["lesson"] == "port-activity:INNSA:quiet:passes"


def test_a_refused_write_is_reported_and_the_look_goes_on(graph, monkeypatch):
    port_days(graph, "INNSA", USUAL + [4])
    port_days(graph, "CNQDG", USUAL + [25])
    real = portwatcher.open_episode

    def refuses_one(graph, episode_id, *args, **kwargs):
        if "INNSA" in episode_id:
            return {"id": None, "status": "invalid", "reason": "refused for the test"}
        return real(graph, episode_id, *args, **kwargs)

    monkeypatch.setattr(portwatcher, "open_episode", refuses_one)
    done = {d["port"]: d for d in portwatcher.watch(graph, [day(14)])}
    assert done["INNSA"]["did"] == "failed" and "refused for the test" in done["INNSA"]["reason"]
    assert done["CNQDG"]["did"] == "opened"


@pytest.mark.parametrize(
    ("before", "today", "state"),
    [
        (USUAL, 5, "quiet"),  # half of 10
        (USUAL, 6, "usual"),
        (USUAL, 20, "busy"),  # twice 10
        (USUAL, 19, "usual"),
        ([5] * 14, 0, "usual"),  # usually 5: below the smallest port that counts
        ([0] * 14, 3, "usual"),
    ],
)
def test_what_is_unusual(before, today, state):
    calls = {DAY0 + timedelta(days=n): c for n, c in enumerate(before + [today])}
    assert portwatcher.judge(calls, DAY0 + timedelta(days=len(before)))["state"] == state


def test_too_few_days_say_nothing():
    calls = {DAY0 + timedelta(days=n): 10 for n in range(15)}
    assert portwatcher.judge(calls, DAY0 + timedelta(days=13)) is None  # 13 days before it
    assert portwatcher.judge(calls, DAY0 + timedelta(days=14))["state"] == "usual"
    assert portwatcher.judge(calls, DAY0 + timedelta(days=99)) is None  # no such day
    gap = {DAY0 + timedelta(days=n): 10 for n in range(30) if n != 20}
    assert portwatcher.judge(gap, DAY0 + timedelta(days=20)) is None  # a day in between


def test_the_rule_learns_only_from_port_episodes_that_ended():
    seen = {"type": "observation", "port": "INNSA", "state": "busy", "name": "Nhava Sheva"}
    ended = {"type": "outcome", "days": 5}
    (claim_,) = portwatcher.rule({"id": "port-activity:INNSA:x", "entries": [seen, ended]})
    assert (claim_["lesson"], claim_["agrees"]) == ("port-activity:INNSA:busy:passes", False)
    assert "Nhava Sheva" in claim_["statement"] and "twice" in claim_["statement"]
    assert portwatcher.rule({"id": "x", "entries": [seen]}) == []
    assert portwatcher.rule({"id": "x", "entries": []}) == []
    assert portwatcher.rule({"id": "x", "entries": [seen, {"type": "outcome", "days": "5"}]}) == []
