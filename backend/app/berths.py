"""Berths: how many ships a berth has held at one time, and where more are expected.

The feed does not say how many ships fit at a berth, and some berth codes stand for a whole
quay or harbour. The graph does say it: port calls that were alongside together show what a
berth takes. An overload is more port calls expected at one time than the berth ever held at
one time, in what the graph has recorded.
"""

from datetime import UTC, datetime, timedelta

from falkordb import Graph
from lighthouse import now, stamp

HISTORY_DAYS = 90  # port calls that ended longer ago do not count
# Limit: a port call longer than this is taken for bad data and left out. The feed had one
# with an arrival eleven years before its expected arrival; it would count as alongside
# for good. A ship that is laid up longer is left out too.
MAX_STAY = timedelta(days=120)
FOREVER = datetime.max.replace(tzinfo=UTC)

# The berth of a port call is its open AT edge, and its times are its current values.
# A port call without a start and an end, or with an end before its start, is left out.
CALLS = """
MATCH (pc:PortCall)-[at:AT]->(b:Berth) WHERE at.valid_to IS NULL
WITH b.key AS berth, pc, coalesce(pc.ata, pc.eta) AS start, coalesce(pc.atd, pc.etd) AS finish
WHERE finish > start AND finish > localdatetime($since)
RETURN berth, collect([pc.id, start, finish, pc.ata IS NOT NULL, pc.atd IS NOT NULL])
ORDER BY berth
"""


def _moment(at) -> datetime:
    """The time to look from: the given one, or now. Never ahead of the clock."""
    text = min(stamp(at) or now(), now())
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def _load(calls: list, moment: datetime) -> dict:
    """What one berth held and what it is expected to hold, from its port calls:
    [id, start, finish, arrived, departed]."""
    calls = [call for call in calls if call[2] - call[1] <= MAX_STAY]
    # A port call that arrived and did not leave is alongside, whatever its expected
    # departure says.
    alongside = [
        (start, finish if left else FOREVER, key)
        for key, start, finish, came, left in calls
        if came
    ]
    together = max(
        (
            sorted(key for start, finish, key in alongside if start <= when < finish)
            for when, _, _ in alongside
        ),
        key=len,
        default=[],
    )
    capacity = max(1, len(together))
    # What is expected: port calls that have not left. One that is alongside past its
    # expected departure is there now, and no later time is known for it.
    still_here = moment + timedelta(seconds=1)
    waiting = [
        (start, max(finish, still_here) if came else finish, key)
        for key, start, finish, came, left in calls
        if not left
    ]
    # The first stretch of time, from the look on, in which more are expected than that.
    # The number alongside changes only when one arrives or leaves.
    times = {max(start, moment) for start, _, _ in waiting} | {finish for _, finish, _ in waiting}
    overload = None
    for when in sorted(time for time in times if time >= moment):
        group = [key for start, finish, key in waiting if start <= when < finish]
        if len(group) > capacity:
            overload = overload or {"from": when, "until": None, "most": 0, "calls": set()}
            overload["most"] = max(overload["most"], len(group))
            overload["calls"] |= set(group)
        elif overload:
            overload |= {"until": when, "calls": sorted(overload["calls"])}
            break
    return {"capacity": capacity, "together": together, "overload": overload}


def loads(graph: Graph, at=None) -> list[dict]:
    """Every berth with port calls, by key: {"berth", "capacity", "together", "overload"}.

    capacity  the most port calls that were alongside at one time, and 1 at least
    together  the port calls that were, as their ids
    overload  None, or {"from", "until", "most", "calls"}: the first stretch of time from
              `at` (default: now) in which more port calls are expected alongside than
              the capacity, the most at one time in it, and the ids of all of them
    """
    moment = _moment(at)
    since = (moment - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = graph.ro_query(CALLS, {"since": since}).result_set
    return [{"berth": berth, **_load(calls, moment)} for berth, calls in rows]


def overloads(graph: Graph, at=None) -> list[dict]:
    """The berths where more port calls are expected at one time than the berth ever held."""
    return [load for load in loads(graph, at) if load["overload"]]
