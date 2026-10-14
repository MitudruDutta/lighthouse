"""The Watcher: an agent that sees a berth with more port calls expected than it ever held,
and acts on it.

After a poll of the feed it asks the graph where a berth is overloaded. For a berth that was
not, it opens an episode about the berth and the port calls, writes what it sees with the
evidence, and does what memory says:

  a lesson about the berth      it writes the lesson into the episode, and that it used it
  a playbook for the situation  it writes each step as an action, and records the run
then it raises a task and hands the episode over to the desk, with what the playbook says.

While the overload lasts and its picture changes, it adds an observation. When the overload
is gone, it closes the episode with what became of each port call, and whether the berth
held them all after all. Every entry cites the berth and the port calls as they were then.
"""

import hashlib
import json
from datetime import datetime

from falkordb import Graph
from lighthouse import (
    add_task,
    as_of,
    close_episode,
    episode,
    episodes_about,
    hand_off,
    lessons_about,
    now,
    open_episode,
    playbooks_for,
    ran,
    record,
    related,
    stamp,
    used,
)

from app.berths import loads
from app.portcalls import BERTH, PORT_CALL

SITUATION = "berth-overload"
DESK = "desk"  # who gets the episode when no playbook fits
MAX_CITED = 50  # port calls that one entry cites
MAX_LESSONS = 3  # lessons that one episode recalls


def _text(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%S")


def _episode_id(berth: str, moment: str) -> str:
    """One id for one overload of one berth, first seen at one time."""
    name = f"{SITUATION}:{berth}:{moment}"
    if len(name) > 200:  # the longest id the library takes
        name = f"{SITUATION}:{hashlib.sha256(berth.encode()).hexdigest()[:16]}:{moment}"
    return name


def _done(receipt: dict, *expected: str) -> dict:
    """A receipt of the library, or an error when the write was refused. The library has
    stored the refusal already."""
    if receipt["status"] not in expected:
        raise RuntimeError(f"{receipt['status']}: {receipt.get('reason')}")
    return receipt


def _picture(load: dict, moment: str) -> dict:
    """What the Watcher sees at a berth, as the values of an observation."""
    over = load["overload"]
    ongoing = _text(over["from"]) <= moment
    return {
        "situation": SITUATION,
        "berth": load["berth"],
        "ongoing": ongoing,  # it has begun: "from" is then the time of this look
        "from": _text(over["from"]),
        "until": _text(over["until"]),
        "expected": over["most"],  # at one time
        "capacity": load["capacity"],
        "calls": over["calls"],
        "together": load["together"],  # the port calls that showed the capacity
    }


def _same(old: dict, new: dict) -> bool:
    """Whether two pictures show the same overload. One that has begun moves its start
    with the clock, and that is no change."""
    return (old.get("calls"), old.get("until"), old.get("ongoing")) == (
        new["calls"],
        new["until"],
        new["ongoing"],
    ) and (new["ongoing"] or old.get("from") == new["from"])


def _cites(berth: str, *calls: list) -> list:
    keys = dict.fromkeys(key for group in calls for key in group)
    return [(BERTH, berth), *((PORT_CALL, key) for key in list(keys)[:MAX_CITED])]


def _open(graph: Graph, berth: str) -> dict | None:
    """The episode of an overload of this berth that is still open."""
    # Limit: this reads every episode about the berth, closed ones too.
    for found in episodes_about(graph, BERTH, berth):
        if found["id"].startswith(f"{SITUATION}:") and found["outcome"] is None:
            return found
    return None


def _seen(graph: Graph, episode_id: str) -> dict:
    """The last picture that was written into an episode."""
    entries = episode(graph, episode_id)["entries"]
    return next((entry for entry in reversed(entries) if entry["type"] == "observation"), {})


def _begin(graph: Graph, load: dict, moment: str, by: str) -> str:
    """Open the episode of a new overload, and act on it."""
    berth, picture = load["berth"], _picture(load, moment)
    name = _episode_id(berth, moment)
    _done(open_episode(graph, name, by, _cites(berth, picture["calls"]), moment), "opened")
    cites = _cites(berth, picture["calls"], picture["together"])
    _done(record(graph, name, "observation", by, picture, cites, moment), "recorded")

    for lesson in lessons_about(graph, BERTH, berth)[:MAX_LESSONS]:
        values = {
            "lesson": lesson["id"],
            "statement": lesson.get("statement"),
            "weight": lesson["weight"],
        }
        _done(
            record(graph, name, "recall", by, values, [("Lesson", lesson["id"])], moment),
            "recorded",
        )
        _done(used(graph, lesson["id"], by, name), "used", "exists")

    situation = {"situation": SITUATION, "berth": berth, "port": berth.split("/")[0]}
    books = playbooks_for(graph, situation)
    ask = (
        f"{picture['expected']} port calls are expected at a berth that held {picture['capacity']}"
    )
    if books:
        book = books[0]  # the one with the best record
        for number, step in enumerate(book["steps"], 1):
            values = {
                "playbook": book["id"],
                "step": number,
                "does": json.dumps(step, sort_keys=True),
            }
            _done(
                record(graph, name, "action", by, values, [("Playbook", book["id"])], moment),
                "recorded",
            )
        _done(ran(graph, book["name"], by, name), "recorded", "exists")
        # Each step as "name value" pairs, in the order of their names: one text for one step.
        steps = "; ".join(
            ", ".join(f"{k} {v}" for k, v in sorted(step.items())) for step in book["steps"]
        )
        ask += f". The playbook {book['id']} says: {steps}"
    # The Watcher cannot move a ship. What it found, and what memory proposes, goes to the
    # desk, where a person or another agent can act on it.
    add_task(graph, name, SITUATION, ref=name)
    _done(
        hand_off(graph, name, by, DESK, [("Episode", name)], {"ask": ask}, moment),
        "given",
        "exists",
    )
    values = {"did": "raised a task and handed the episode over", "to": DESK, "task": name}
    _done(record(graph, name, "action", by, values, at=moment), "recorded")
    return name


def _became(graph: Graph, call, berth: str, moment: str) -> str:
    """What became of a port call that was part of an overload, in a few words."""
    berths = related(graph, PORT_CALL, call, "AT")
    if berth not in berths:
        return f"{call}: moved to {berths[0]}" if berths else f"{call}: has no berth"
    state = as_of(graph, PORT_CALL, call, moment) or {}
    if state.get("atd"):
        return f"{call}: departed"
    if state.get("ata"):
        return f"{call}: alongside"
    return f"{call}: expected from {state.get('eta')} to {state.get('etd')}"


def _end(graph: Graph, load: dict, name: str, moment: str, by: str) -> None:
    """Close the episode of an overload that is gone, with what became of it."""
    berth, last = load["berth"], _seen(graph, name)
    calls = last.get("calls", [])
    elsewhere = [related(graph, PORT_CALL, call, "AT") for call in calls]
    outcome = {
        "cleared": True,
        "capacity": load["capacity"],
        # The berth took as many as were expected: it was no overload after all.
        "held": load["capacity"] >= last.get("expected", len(calls) or 1),
        "calls": [_became(graph, call, berth, moment) for call in calls],
        # The berths that port calls of the overload were moved to.
        "moved_to": sorted({berths[0] for berths in elsewhere if berths and berth not in berths}),
    }
    _done(close_episode(graph, name, by, outcome, _cites(berth, calls), moment), "recorded")


def watch(graph: Graph, observed=None, by: str = "watcher") -> list[dict]:
    """One look at every berth, after a poll. `observed` is the time of the poll (default:
    now). Returns what was done: [{"berth", "episode", "did"}] with did
      opened   a new overload: an episode was opened and acted on
      updated  the overload goes on with other port calls or other times
      cleared  the overload is gone: the episode was closed
      failed   the library refused a write: "reason" says which, and the look goes on
    A berth with nothing to do is not listed.
    """
    moment = min(stamp(observed) or now(), now())
    done = []
    for load in loads(graph, moment):
        berth, current = load["berth"], _open(graph, load["berth"])
        try:
            if load["overload"] and current is None:
                did, name = "opened", _begin(graph, load, moment, by)
            elif load["overload"]:
                did, name, picture = "updated", current["id"], _picture(load, moment)
                if _same(_seen(graph, name), picture):
                    continue
                cites = _cites(berth, picture["calls"], picture["together"])
                _done(record(graph, name, "observation", by, picture, cites, moment), "recorded")
            elif current:
                did, name = "cleared", current["id"]
                _end(graph, load, name, moment, by)
            else:
                continue
            done.append({"berth": berth, "episode": name, "did": did})
        except RuntimeError as exc:
            done.append({"berth": berth, "episode": None, "did": "failed", "reason": str(exc)})
    return done
