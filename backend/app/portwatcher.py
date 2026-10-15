"""The Port Watcher: an agent that sees a port of the world whose ships stop coming, or come
in far greater numbers than usual, and acts on it.

After each read of PortWatch it compares each new day of each port with what is usual for
that port: the median of its port calls on the BASELINE days before. A port is unusual on a
day when
  quiet  its port calls fell to QUIET of the usual or less
  busy   they rose to BUSY times the usual or more
at a port that usually has at least MIN_USUAL a day. For a port that turns unusual, it opens
an episode about the port, writes what it sees with the port as evidence, as it was that
day, recalls what was learned about the port, raises a task, and hands the episode to the
desk. Each further day it stays unusual adds an observation. When the port is back to
usual, it closes the episode with how many days it lasted.

The Reviewer turns those that ended into lessons about each port: whether a quiet or busy
spell there passes within SHORT days.
"""

import statistics
from datetime import date, timedelta

from falkordb import Graph
from lighthouse import (
    add_task,
    close_episode,
    hand_off,
    lessons_about,
    open_episode,
    record,
    used,
)
from lighthouse.read import pages
from lighthouse.values import whole_number

from app.portcalls import PORT

SITUATION = "port-activity"
DESK = "desk"
BY = "port-watcher"
BASELINE = 28  # days before a day that tell what is usual at a port
LEAST_DAYS = 14  # of those, how many a port needs before any day of it is unusual
MIN_USUAL = 6  # port calls a day: at a smaller port, a quiet day is no news
QUIET = 0.5
BUSY = 2.0
SHORT = 3  # days: a spell that ends within this many passed quickly
MAX_LESSONS = 3

# Port calls of the days of each port, from the States that held on them. Days with the
# same numbers are one State, so each State stands for every day it held.
DAYS = """
MATCH (p:Port)-[:HAS_STATE]->(s:State)
WHERE s.calls IS NOT NULL AND s.valid_from <= localdatetime($last)
  AND (s.valid_to IS NULL OR s.valid_to > localdatetime($first))
RETURN p.locode, s.valid_from, s.valid_to, s.calls, s.name ORDER BY p.locode, s.valid_from
"""

OPEN = f"""
MATCH (ep:Episode)-[:ABOUT]->(p:Port)
WHERE ep.closed_at IS NULL AND ep.id STARTS WITH '{SITUATION}:'
RETURN p.locode, ep.id, ep.opened_at ORDER BY ep.id
"""


UNUSUAL = f"""
MATCH (ep:Episode)-[:ABOUT]->(p:Port)
WHERE ep.closed_at IS NULL AND ep.id STARTS WITH '{SITUATION}:'
MATCH (ep)-[:HAS]->(e:Entry {{seq: 1}})
RETURN p.locode, e.name, e.state, e.calls, e.usual, e.day, ep.id
ORDER BY e.day DESC, p.locode LIMIT $limit
"""


def _done(receipt: dict, *expected: str) -> dict:
    """A receipt of the library, or an error when the write was refused. The library has
    stored the refusal already."""
    if receipt["status"] not in expected:
        raise RuntimeError(f"{receipt['status']}: {receipt.get('reason')}")
    return receipt


def series(graph: Graph, first: date, last: date) -> dict[str, dict]:
    """{port: {"name", "calls": {day: port calls}}} for the days from `first` to `last`."""
    params = {"first": f"{first}T00:00:00", "last": f"{last}T00:00:00"}
    found: dict[str, dict] = {}
    for key, start, end, calls, name in pages(graph, DAYS, params):
        port = found.setdefault(key, {"name": name, "calls": {}})
        port["name"] = name or port["name"]
        day = max(start.date(), first)
        stop = min(end.date() - timedelta(days=1), last) if end else last
        while day <= stop:
            port["calls"][day] = calls
            day += timedelta(days=1)
    return found


def judge(calls: dict, day: date) -> dict | None:
    """How a port was on `day`: {"state", "calls", "usual", "ratio"}, with state "quiet",
    "busy", or "usual"; None when the port has too few days before it to tell."""
    if day not in calls:
        return None
    before = [
        calls[d] for d in (day - timedelta(days=n) for n in range(1, BASELINE + 1)) if d in calls
    ]
    if len(before) < LEAST_DAYS:
        return None
    usual = statistics.median(before)
    today = calls[day]
    ratio = round(today / usual, 2) if usual else None
    state = "usual"
    if usual >= MIN_USUAL and today <= QUIET * usual:
        state = "quiet"
    elif usual >= MIN_USUAL and today >= BUSY * usual:
        state = "busy"
    return {"state": state, "calls": today, "usual": usual, "ratio": ratio}


def _begin(graph: Graph, key: str, name: str | None, seen: dict, moment: str) -> str:
    episode_id = f"{SITUATION}:{key}:{moment[:10]}"
    _done(open_episode(graph, episode_id, BY, [(PORT, key)], moment), "opened")
    values = {"situation": SITUATION, "port": key, "name": name, "day": moment[:10], **seen}
    _done(record(graph, episode_id, "observation", BY, values, [(PORT, key)], moment), "recorded")
    for lesson in lessons_about(graph, PORT, key)[:MAX_LESSONS]:
        values = {
            "lesson": lesson["id"],
            "statement": lesson.get("statement"),
            "weight": lesson["weight"],
        }
        _done(
            record(graph, episode_id, "recall", BY, values, [("Lesson", lesson["id"])], moment),
            "recorded",
        )
        _done(used(graph, lesson["id"], BY, episode_id, at=moment), "used", "exists")
    word = "fewer" if seen["state"] == "quiet" else "more"
    ask = (
        f"{seen['calls']} port calls at {name or key} on {moment[:10]}, far {word} than the usual "
        f"{seen['usual']} a day"
    )
    add_task(graph, episode_id, SITUATION, ref=episode_id)
    _done(
        hand_off(graph, episode_id, BY, DESK, [("Episode", episode_id)], {"ask": ask}, moment),
        "given",
        "exists",
    )
    values = {"did": "raised a task and handed the episode over", "to": DESK, "task": episode_id}
    _done(record(graph, episode_id, "action", BY, values, at=moment), "recorded")
    return episode_id


def watch(graph: Graph, days: list[str]) -> list[dict]:
    """Look at each of `days` (YYYY-MM-DD, oldest first) at every port. Returns what was done:
    [{"port", "day", "episode", "did"}] with did opened, seen, ended, or failed (with
    "reason"). A port with nothing to do is not listed."""
    if not days:
        return []
    wanted = sorted(date.fromisoformat(day) for day in days)
    ports = series(graph, wanted[0] - timedelta(days=BASELINE), wanted[-1])
    episodes = {
        key: (episode_id, opened) for key, episode_id, opened in graph.ro_query(OPEN).result_set
    }
    done = []
    for day in wanted:
        moment = f"{day}T00:00:00"
        for key, port in ports.items():
            seen = judge(port["calls"], day)
            if seen is None:
                continue
            current = episodes.get(key)
            try:
                if seen["state"] != "usual" and current is None:
                    episode_id = _begin(graph, key, port["name"], seen, moment)
                    episodes[key] = (episode_id, day)
                    did = "opened"
                elif seen["state"] != "usual":
                    episode_id = current[0]
                    values = {"situation": SITUATION, "port": key, "day": str(day), **seen}
                    _done(
                        record(graph, episode_id, "observation", BY, values, [(PORT, key)], moment),
                        "recorded",
                    )
                    did = "seen"
                elif current is not None:
                    episode_id, opened = current
                    began = opened.date() if hasattr(opened, "date") else opened
                    outcome = {"back_to_usual": True, "days": (day - began).days, **seen}
                    _done(
                        close_episode(graph, episode_id, BY, outcome, [(PORT, key)], moment),
                        "recorded",
                    )
                    del episodes[key]
                    did = "ended"
                else:
                    continue
                done.append({"port": key, "day": str(day), "episode": episode_id, "did": did})
            except RuntimeError as exc:
                done.append(
                    {
                        "port": key,
                        "day": str(day),
                        "episode": None,
                        "did": "failed",
                        "reason": str(exc),
                    }
                )
    return done


def rule(found: dict) -> list[dict]:
    """What one port episode that ended shows, as claims for promote(): whether a spell of
    this kind at this port passed within SHORT days."""
    entries = found["entries"]
    first = next((entry for entry in entries if entry["type"] == "observation"), None)
    end = entries[-1] if entries else None
    if first is None or end is None or end["type"] != "outcome" or type(end.get("days")) is not int:
        return []
    key, state = first["port"], first["state"]
    name = first.get("name") or key
    word = (
        "fall to half the usual or less" if state == "quiet" else "rise to twice the usual or more"
    )
    return [
        {
            "lesson": f"{SITUATION}:{key}:{state}:passes",
            "statement": f"When port calls at {name} {word}, they are back within {SHORT} days.",
            "about": [(PORT, key)],
            "agrees": end["days"] <= SHORT,
        }
    ]


def unusual(graph: Graph, limit: int = 50) -> list[dict]:
    """The ports that are unusual now, the newest spells first: each with the day its spell
    began, its port calls that day against the usual, and its open episode."""
    whole_number(limit, "limit", 500)
    fields = ("port", "name", "state", "calls", "usual", "since", "episode")
    return [dict(zip(fields, row)) for row in graph.ro_query(UNUSUAL, {"limit": limit}).result_set]
