"""The port desk over HTTP, for the screen: read-only routes under /api.

Every route reads the graph through the library or a query of its own; none writes. The
poller and the agents are the writers. A question the library cannot take (a key of the
wrong form, an unknown kind) is a 422 with the reason.
"""

import os
from collections import Counter
from typing import Annotated

import lighthouse
from falkordb import Graph
from fastapi import APIRouter, Depends, HTTPException, Query
from lighthouse.episodes import pairs
from lighthouse.values import without_words

from app import intelligence, portwatch, portwatcher
from app.berths import loads
from app.db import get_db
from app.model import readiness
from app.poller import last_poll
from app.portcalls import BERTH, PORT, PORT_CALL, VESSEL, key_for, kind_named

router = APIRouter(prefix="/api")
HIDDEN = {"fp"}  # of a State: a fingerprint that says nothing to a reader
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
    """Customer-facing counts, source dates and availability. No operator diagnostics."""
    labels = ("PortCall", "Vessel", "Berth", "Port", "Episode", "Lesson", "Playbook")
    open_episodes = graph.ro_query(
        "MATCH (ep:Episode) WHERE ep.closed_at IS NULL RETURN count(ep)"
    ).result_set[0][0]
    feed, world, desk, live = (
        last_poll(graph, source) for source in ("feed", "portwatch", "desk", "ais")
    )

    def available(source, success):
        failure = last_poll(graph, f"{source}-error")
        return bool(success and (not failure or failure["at"] <= success["at"]))

    def shown(summary, fields):
        if summary is None:
            return None
        result = {field: summary[field] for field in fields if field in summary}
        for field in ("port_calls", "rows", "did"):
            if field in result:
                result[field] = {key: value for key, value in result[field].items() if key in {
                    "created", "changed", "inserted", "unchanged", "assessed", "ended before the desk looked"
                }}
        if result.get("state") == "partial":
            result["state"] = "updating"
        return result

    return {
        "now": lighthouse.now(),  # for "how long ago", by the clock of the graph's writers
        "counts": {label: _count(graph, label) for label in labels},
        "open_episodes": open_episodes,
        "last_poll": shown(feed, ("at", "feed_time", "port_calls")),
        "last_world_poll": shown(world, ("at", "ports", "days", "rows", "newest", "state")),
        "last_desk": shown(desk, ("at", "did", "waiting")),
        "last_ais": shown(live, ("at", "ports", "ships_now")),
        "availability": {
            "feed": available("feed", feed),
            "portwatch": available("portwatch", world),
            "ais": available("ais", live),
            "desk": readiness()["ready"] and not bool(desk and desk.get("failed")),
        },
    }


@router.get("/live")
def live(graph: Desk) -> dict:
    """Ships stopped at the busiest ports now and today, from live AIS positions. Empty
    until the live reader has a key and has written once."""
    rows = graph.ro_query(
        "MATCH (l:LivePort) RETURN l.port, l.name, l.ships_now, l.ships_today, l.day "
        "ORDER BY l.ships_now DESC, l.port LIMIT $most",
        {"most": MOST},
    ).result_set
    summary = last_poll(graph, "ais")
    return {
        "at": summary["at"] if summary else None,
        "ports": {
            key: {"name": name, "now": now_, "today": today, "day": day}
            for key, name, now_, today, day in rows
        },
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


@router.get("/network")
def network(graph: Desk, kind: Annotated[str, Query(pattern="^(Episode|Entry|Lesson|Playbook|Port|PortCall|Vessel|Berth)$")] = "Episode", key: Annotated[str | None, Query(max_length=300)] = None) -> dict:
    return intelligence.network(graph, kind, key)


@router.get("/intelligence")
def intelligence_overview(graph: Desk) -> dict:
    return intelligence.overview(graph)


@router.get("/quality")
def data_quality(graph: Desk) -> dict:
    return intelligence.quality(graph)


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
    partial: bool = False,
    limit: Annotated[int, Query(ge=1, le=MOST)] = 10,
) -> list[dict]:
    """Vessels, berths, or ports whose name has the words of `q`, best first. With
    `earlier`, the names they had at any time, each with when it held. With `partial`,
    those whose name holds `q` anywhere, shortest name first: for a box that searches as
    a person types."""
    found = kind_named(kind)
    if partial and not earlier:
        if not q.strip():
            return []
        # The text is a parameter; the label is one of three fixed kinds.
        rows = graph.ro_query(
            f"MATCH (n:{found.label}) WHERE toLower(coalesce(n.name, '')) CONTAINS toLower($q) "
            "RETURN n ORDER BY size(n.name), n.name LIMIT $limit",
            {"q": q.strip(), "limit": limit},
        ).result_set
        return [
            {
                "key": node.properties[found.key],
                "score": 1.0,
                "values": {
                    name: value
                    for name, value in _shown(without_words(node.properties)).items()
                    if name != found.key
                },
            }
            for (node,) in rows
        ]
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
    return [_shown(port) for port in portwatch.busiest(graph, country, limit)]


@router.get("/activity")
def activity(graph: Desk, limit: Annotated[int, Query(ge=1, le=MOST)] = 30) -> dict:
    """What the agents wrote last, newest first, each entry with its episode; and how many
    episodes were opened on each of the last 14 days that have any."""
    rows = graph.ro_query(
        "MATCH (ep:Episode)-[:HAS]->(e:Entry) "
        "WITH ep, e ORDER BY e.recorded_at DESC, e.id DESC LIMIT $limit "
        "RETURN ep.id, e ORDER BY e.recorded_at DESC, e.id DESC",
        {"limit": limit},
    ).result_set
    opened = Counter(
        at.date().isoformat()
        for (at,) in graph.ro_query("MATCH (ep:Episode) RETURN ep.opened_at").result_set
        if at is not None
    )
    return {
        "entries": [
            {"episode": episode_id, **without_words(entry.properties)} for episode_id, entry in rows
        ],
        "opened": [{"day": day, "count": opened[day]} for day in sorted(opened)[-14:]],
    }


@router.get("/unusual")
def unusual(graph: Desk, limit: Annotated[int, Query(ge=1, le=MOST)] = 50) -> dict:
    """The ports that are unusual now, the newest spells first, each with its port calls
    on the day it began against the usual, and its open episode."""
    return {"ports": portwatcher.unusual(graph, limit)}


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
        "days": portwatch.daily(versions, portwatch.newest(graph), days),
        "lessons": lighthouse.lessons_about(graph, PORT, key),
        "episodes": lighthouse.episodes_about(graph, PORT, key),
        "port_calls": calls,
    }
