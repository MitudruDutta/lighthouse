"""The port desk over HTTP, for the screen: read-only routes under /api.

Every route reads the graph through the library or a query of its own; none writes. The
poller and the agents are the writers. A question the library cannot take (a key of the
wrong form, an unknown kind) is a 422 with the reason.
"""

import os
from datetime import date, timedelta
from typing import Annotated

import lighthouse
from falkordb import Graph
from fastapi import APIRouter, Depends, HTTPException, Query
from lighthouse.episodes import pairs
from lighthouse.values import without_words

from app import portwatch
from app.berths import loads
from app.db import get_db
from app.poller import last_poll
from app.portcalls import BERTH, PORT, PORT_CALL, VESSEL, key_for, kind_named

router = APIRouter(prefix="/api")
HIDDEN = {"fp"}  # of a State: a fingerprint that says nothing to a reader
# The numbers of a day of a port, as portwatch.py names them.
NUMBERS = list(portwatch.DAY.values())
MOST = 200  # items in one answer


def get_graph() -> Graph:
    """The graph the desk reads: LIGHTHOUSE_GRAPH, or the shared world graph."""
    return get_db().select_graph(os.environ.get("LIGHTHOUSE_GRAPH", lighthouse.WORLD))


Desk = Annotated[Graph, Depends(get_graph)]


def _shown(state: dict | None) -> dict | None:
    return None if state is None else {k: v for k, v in state.items() if k not in HIDDEN}


def _count(graph: Graph, label: str) -> int:
    return graph.ro_query(f"MATCH (n:{label}) RETURN count(n)").result_set[0][0]


@router.get("/status")
def status(graph: Desk) -> dict:
    """What the graph holds, and what the last read of the feed did."""
    labels = ("PortCall", "Vessel", "Berth", "Port", "Episode", "Lesson", "Playbook")
    open_episodes = graph.ro_query(
        "MATCH (ep:Episode) WHERE ep.closed_at IS NULL RETURN count(ep)"
    ).result_set[0][0]
    return {
        "graph": graph.name,
        "counts": {label: _count(graph, label) for label in labels},
        "open_episodes": open_episodes,
        "last_poll": last_poll(graph),
        "last_world_poll": last_poll(graph, "portwatch"),
    }


@router.get("/berths")
def berths(graph: Desk, at: str | None = None) -> list[dict]:
    """Every berth with port calls: what it held, and where more are expected than that.
    Overloaded berths first. `at` looks from another time (default: now)."""
    found = loads(graph, at)
    names = dict(graph.ro_query("MATCH (b:Berth) RETURN b.key, [b.name, b.area_name]").result_set)
    for load in found:
        name, area = names.get(load["berth"], [None, None])
        load |= {"name": name, "area": area}
    return sorted(found, key=lambda load: (load["overload"] is None, load["berth"]))


@router.get("/episodes")
def episodes(
    graph: Desk,
    state: Annotated[str, Query(pattern="^(open|closed|all)$")] = "all",
    situation: Annotated[str | None, Query(pattern="^(berth-overload|port-activity)$")] = None,
    limit: Annotated[int, Query(ge=1, le=MOST)] = 50,
) -> list[dict]:
    """The episodes, newest first, each with what it is about, how many entries it has, and
    its first entry. `situation` keeps to the overloads of berths or the unusual days of
    ports."""
    where = {"open": "ep.closed_at IS NULL", "closed": "ep.closed_at IS NOT NULL", "all": "true"}
    rows = graph.ro_query(
        f"MATCH (ep:Episode) WHERE {where[state]} AND ep.id STARTS WITH $prefix "
        "WITH ep ORDER BY ep.opened_at DESC, ep.id LIMIT $limit "
        "OPTIONAL MATCH (ep)-[a:ABOUT]->() "
        "WITH ep, collect([a.label, a.key]) AS about "
        # FalkorDB finds nothing in an optional match right after an aggregate: a plain WITH.
        "WITH ep, about "
        "OPTIONAL MATCH (ep)-[:HAS]->(first:Entry {seq: 1}) "
        "RETURN ep, about, first ORDER BY ep.opened_at DESC, ep.id",
        {"limit": limit, "prefix": f"{situation}:" if situation else ""},
    ).result_set
    return [
        {
            **node.properties,
            "about": pairs(about),
            # What was seen first, so that a list can say what the episode is about.
            "first": without_words(first.properties) if first else None,
        }
        for node, about, first in rows
    ]


@router.get("/episodes/{episode_id:path}")
def episode(graph: Desk, episode_id: str) -> dict:
    """One episode: every entry in order, with the evidence it cites, and how it ended."""
    found = lighthouse.episode(graph, episode_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such episode")
    return found


@router.get("/lessons")
def lessons(graph: Desk) -> list[dict]:
    """The lessons that still hold, heaviest first, with the episodes for and against."""
    ids = graph.ro_query(
        "MATCH (l:Lesson) WHERE l.retired_at IS NULL RETURN l.id ORDER BY l.id LIMIT $most",
        {"most": MOST},
    ).result_set
    found = [lighthouse.lesson(graph, lesson_id) for (lesson_id,) in ids]
    return sorted(found, key=lambda item: (-item["weight"], item["id"]))


@router.get("/playbooks")
def playbooks(graph: Desk) -> list[dict]:
    """The newest version of each playbook, with its trigger, steps, and record."""
    names = graph.ro_query(
        "MATCH (pb:Playbook) RETURN DISTINCT pb.name ORDER BY pb.name LIMIT $most",
        {"most": MOST},
    ).result_set
    return [lighthouse.playbook(graph, name) for (name,) in names]


@router.get("/portcalls/{key}")
def port_call(graph: Desk, key: str, at: str | None = None) -> dict:
    """One port call as it was at `at` (default: now): its values, what it pointed at, and
    every version of it."""
    number = key_for(PORT_CALL, key)
    when = at or lighthouse.now()
    versions = lighthouse.history(graph, PORT_CALL, number)
    if not versions:
        raise HTTPException(status_code=404, detail="no such port call")
    relations = {
        name: lighthouse.related(graph, PORT_CALL, number, name, when)
        for name in PORT_CALL.relations
    }
    return {
        "key": number,
        "at": when,
        "values": _shown(lighthouse.as_of(graph, PORT_CALL, number, when)),
        "relations": relations,
        "versions": [_shown(state) for state in versions],
        "episodes": lighthouse.episodes_about(graph, PORT_CALL, number),
    }


@router.get("/search")
def search(
    graph: Desk,
    q: Annotated[str, Query(max_length=1_000)],
    kind: Annotated[str, Query(pattern="^(Vessel|Berth|Port)$")] = "Vessel",
    earlier: bool = False,
    limit: Annotated[int, Query(ge=1, le=MOST)] = 10,
) -> list[dict]:
    """Vessels, berths, or ports whose name has the words of `q`, best first. With
    `earlier`, the names they had at any time, each with when it held."""
    found = kind_named(kind)
    if earlier:
        return [
            {"key": item["key"], "score": item["score"], "state": _shown(item["state"])}
            for item in lighthouse.search_history(graph, found, q, limit, match="any")
        ]
    return lighthouse.search(graph, found, q, limit, match="any")


@router.get("/connection")
def connection(
    graph: Desk,
    from_kind: str,
    from_key: str,
    to_kind: str,
    to_key: str,
    at: str | None = None,
    max_hops: Annotated[int, Query(ge=1, le=10)] = 6,
) -> dict:
    """How two things are connected: the shortest chain of relations, now or at `at`."""
    start, end = kind_named(from_kind), kind_named(to_kind)
    steps = lighthouse.connection(
        graph,
        (start, key_for(start, from_key)),
        (end, key_for(end, to_key)),
        kinds=[PORT_CALL],
        max_hops=max_hops,
        at=at,
    )
    return {"steps": steps}


@router.get("/vessels/{imo}")
def vessel(graph: Desk, imo: str) -> dict:
    """One vessel: its names over time, and its port calls."""
    number = key_for(VESSEL, imo)
    versions = lighthouse.history(graph, VESSEL, number)
    if not versions:
        raise HTTPException(status_code=404, detail="no such vessel")
    calls = lighthouse.pointing_at(graph, PORT_CALL, "MADE_BY", number)
    return {
        "key": number,
        "versions": [_shown(state) for state in versions],
        "port_calls": calls,
    }


@router.get("/berths/{key:path}")
def berth(graph: Desk, key: str) -> dict:
    """One berth: its names over time, its port calls now, and what was learned about it."""
    versions = lighthouse.history(graph, BERTH, key)
    if not versions:
        raise HTTPException(status_code=404, detail="no such berth")
    return {
        "key": key,
        "versions": [_shown(state) for state in versions],
        "port_calls": lighthouse.pointing_at(graph, PORT_CALL, "AT", key),
        "lessons": lighthouse.lessons_about(graph, BERTH, key),
        "episodes": lighthouse.episodes_about(graph, BERTH, key),
    }


@router.get("/ports")
def ports(
    graph: Desk,
    country: Annotated[str | None, Query(pattern="^[A-Z]{3}$")] = None,
    limit: Annotated[int, Query(ge=1, le=MOST)] = 50,
) -> list[dict]:
    """Ports of the world with what happened on their last day, busiest first. `country`
    keeps to one country, by its ISO 3166 code, such as IND."""
    rows = graph.ro_query(
        "MATCH (p:Port) WHERE p.calls IS NOT NULL AND ($country IS NULL OR p.iso3 = $country) "
        "RETURN p ORDER BY p.calls DESC, p.locode LIMIT $limit",
        {"country": country, "limit": limit},
    ).result_set
    return [
        {"key": node.properties["locode"], **_shown(without_words(node.properties))}
        for (node,) in rows
    ]


@router.get("/world")
def world(graph: Desk) -> dict:
    """Every port with a place, for a map: [key, name, iso3, country, lat, lon, calls], and the
    ports that are unusual now, with their open episode."""
    rows = graph.ro_query(
        "MATCH (p:Port) WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL "
        "RETURN p.locode, p.name, p.iso3, p.country, p.lat, p.lon, p.calls ORDER BY p.locode"
    ).result_set
    unusual = dict(
        graph.ro_query(
            "MATCH (ep:Episode)-[:ABOUT]->(p:Port) "
            "WHERE ep.closed_at IS NULL AND ep.id STARTS WITH 'port-activity:' "
            "RETURN p.locode, ep.id"
        ).result_set
    )
    return {"newest_day": portwatch.newest(graph), "ports": rows, "unusual": unusual}


def _daily(versions: list[dict], newest: str | None, days: int) -> list[dict]:
    """The last `days` days of a port, one entry a day. A version holds every day from its
    start until the next one; the open one until the newest day that was read."""
    found = {}
    last = date.fromisoformat(newest) if newest else None
    for state in versions:
        day = state["valid_from"].date()
        end = state["valid_to"].date() - timedelta(days=1) if state.get("valid_to") else last
        while end is not None and day <= end:
            found[day] = {"day": day.isoformat(), **{k: state.get(k) for k in NUMBERS}}
            day += timedelta(days=1)
    return [found[day] for day in sorted(found)[-days:]]


@router.get("/ports/{key:path}")
def port(graph: Desk, key: str, days: Annotated[int, Query(ge=1, le=366)] = 30) -> dict:
    """One port: where it is, its last `days` days of port calls, what was learned about it,
    its episodes, and the port calls of the feed that called there, came from there, or are
    bound there."""
    versions = lighthouse.history(graph, PORT, key)
    calls = {
        relation: lighthouse.pointing_at(graph, PORT_CALL, relation, key)
        for relation in ("CALLS_AT", "CAME_FROM", "BOUND_FOR")
    }
    if not versions and not any(calls.values()):
        raise HTTPException(status_code=404, detail="no such port")
    place = versions[-1] if versions else {}
    return {
        "key": key,
        "place": {k: place.get(k) for k in ("name", "country", "iso3", "continent", "lat", "lon")},
        "days": _daily(versions, portwatch.newest(graph), days),
        "lessons": lighthouse.lessons_about(graph, PORT, key),
        "episodes": lighthouse.episodes_about(graph, PORT, key),
        "port_calls": calls,
    }
