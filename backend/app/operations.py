"""Tenant-scoped case decisions and personal watchlists over shared source evidence."""

import re
from functools import cache
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import lighthouse
from fastapi import APIRouter, Depends, HTTPException
from lighthouse.values import without_words
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.exceptions import ResponseError

from app.api import Desk
from app.desk_api import User, _memory

router = APIRouter(prefix="/api/operations")
LIMIT = 200


@cache
def workspace(tenant: str):
    graph = _memory(tenant)
    for label, key in (("OpsProfile", "user"), ("OpsCase", "id")):
        try:
            graph.create_node_unique_constraint(label, key)
        except ResponseError as exc:
            if "already" not in str(exc):
                raise
    return graph


def private(who: User):
    return workspace(who[0])


Private = Annotated[object, Depends(private)]


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="UTC", max_length=64)
    focus: Literal["all", "finland", "global"] = "all"
    view: Literal["attention", "watching", "mine"] = "attention"
    ports: list[str] = Field(default_factory=list, max_length=50)
    vessels: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid name")
        return value.strip()

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown timezone") from None
        return value

    @field_validator("ports", "vessels")
    @classmethod
    def valid_keys(cls, values):
        if any(
            not value or len(value) > 100 or any(ord(c) < 32 for c in value) for value in values
        ):
            raise ValueError("Invalid watchlist key")
        return list(dict.fromkeys(values))


def profile(memory, user):
    rows = memory.ro_query("MATCH (p:OpsProfile {user: $user}) RETURN p", {"user": user}).result_set
    default_name = user
    if not rows and re.fullmatch(r"[a-f0-9]{32}", user):
        from app.memory_control import database

        with database() as db:
            account = db.execute("SELECT name FROM users WHERE id=?", (user,)).fetchone()
            if account:
                default_name = account["name"]
    return (
        {key: value for key, value in rows[0][0].properties.items() if key != "user"}
        if rows
        else {
            "name": default_name,
            "timezone": "UTC",
            "focus": "all",
            "view": "attention",
            "ports": [],
            "vessels": [],
        }
    )


@router.get("/profile")
def my_profile(memory: Private, who: User):
    return profile(memory, who[1])


@router.get("/watchlist-options")
def watchlist_options(graph: Desk, who: User):
    ports = graph.ro_query(
        "MATCH (p:Port) RETURN p.locode, p.name ORDER BY p.name, p.locode LIMIT 5000", timeout=2000
    ).result_set
    vessels = graph.ro_query(
        "MATCH (v:Vessel) RETURN toString(v.imo), v.name ORDER BY v.name, v.imo LIMIT 5000",
        timeout=2000,
    ).result_set
    return {
        "ports": [{"key": key, "name": name or key} for key, name in ports],
        "vessels": [{"key": key, "name": name or key} for key, name in vessels],
    }


@router.put("/profile")
def save_profile(body: Profile, graph: Desk, memory: Private, who: User):
    ports = graph.ro_query(
        "MATCH (p:Port) WHERE p.locode IN $keys RETURN p.locode", {"keys": body.ports}
    ).result_set
    vessels = graph.ro_query(
        "MATCH (v:Vessel) WITH toString(v.imo) AS key WHERE key IN $keys RETURN key",
        {"keys": body.vessels},
    ).result_set
    if set(body.ports) != {row[0] for row in ports} or set(body.vessels) != {
        row[0] for row in vessels
    }:
        raise HTTPException(422, "Choose a port or vessel already in this workspace.")
    memory.query(
        "MERGE (p:OpsProfile {user: $user}) SET p.name = $name, p.timezone = $timezone, "
        "p.focus = $focus, p.view = $view, p.ports = $ports, p.vessels = $vessels",
        {"user": who[1], **body.model_dump()},
    )
    return profile(memory, who[1])


# Names the feed gives a berth it cannot name: "not known", in Finnish. Shown as a name, two
# such berths would read as one place, so the berth's code is shown instead.
PLACEHOLDER_NAMES = {"ei tiedossa", "unknown"}


def name_locations(graph, sources):
    keys = [(source.get("observation") or {}).get("berth") for source in sources.values()]
    names = dict(
        graph.ro_query(
            "MATCH (b:Berth) WHERE b.key IN $keys RETURN b.key, b.name",
            {"keys": [key for key in keys if key]},
            timeout=2000,
        ).result_set
    )
    for source in sources.values():
        name = names.get((source.get("observation") or {}).get("berth"))
        known = isinstance(name, str) and name.strip().lower() not in PLACEHOLDER_NAMES
        source["berth_name"] = name if known else None


def source_rows(graph):
    episodes = graph.ro_query(
        "MATCH (ep:Episode) WHERE ep.id STARTS WITH 'berth-overload:' OR ep.id STARTS WITH 'port-activity:' "
        "RETURN ep ORDER BY ep.closed_at IS NULL DESC, ep.opened_at DESC, ep.id LIMIT $limit",
        {"limit": LIMIT + 1},
        timeout=2000,
    ).result_set
    source = {
        node.properties["id"]: {"episode": node.properties, "about": [], "vessels": []}
        for (node,) in episodes[:LIMIT]
    }
    if not source:
        return source, False
    params = {"ids": list(source)}
    entries = graph.ro_query(
        "MATCH (ep:Episode)-[:HAS]->(e:Entry) WHERE ep.id IN $ids "
        "AND e.type IN ['observation', 'assessment'] "
        "WITH ep.id AS id, e.type AS type, e.seq AS seq "
        "WITH id, type, max(seq) AS last WITH id, type, last "
        "MATCH (ep:Episode {id: id})-[:HAS]->(e:Entry {seq: last}) RETURN id, type, e",
        params,
        timeout=2000,
    ).result_set
    for id_, type_, entry in entries:
        source[id_][type_] = without_words(entry.properties)
    for id_, label, key in graph.ro_query(
        "MATCH (ep:Episode)-[r:ABOUT]->() WHERE ep.id IN $ids RETURN ep.id, r.label, r.key",
        params,
        timeout=2000,
    ).result_set:
        source[id_]["about"].append([label, key])
    for id_, imo in graph.ro_query(
        "MATCH (ep:Episode)-[:ABOUT]->(p:PortCall)-[r:MADE_BY]->(v:Vessel) "
        "WHERE ep.id IN $ids AND r.valid_to IS NULL RETURN DISTINCT ep.id, v.imo",
        params,
        timeout=2000,
    ).result_set:
        source[id_]["vessels"].append(str(imo))
    for id_, state in graph.ro_query(
        "MATCH (t:Task) WHERE t.id IN $ids RETURN t.id, t.status",
        params,
        timeout=2000,
    ).result_set:
        source[id_]["task"] = state
    name_locations(graph, source)
    return source, len(episodes) > LIMIT


def decision(memory, id_):
    rows = memory.ro_query("MATCH (c:OpsCase {id: $id}) RETURN c", {"id": id_}).result_set
    return dict(rows[0][0].properties) if rows else {}


def prior_outcomes(memory, port, id_):
    rows = memory.ro_query(
        "MATCH (c:OpsCase) WHERE c.port = $port AND c.status = 'resolved' AND c.id <> $id "
        "RETURN c ORDER BY c.updated_at DESC LIMIT 3",
        {"port": port, "id": id_},
        timeout=2000,
    ).result_set
    return [
        {
            key: node.properties.get(key)
            for key in ("id", "action", "outcome", "updated_at", "updated_by")
        }
        for (node,) in rows
    ]


def shown(source, held, preferences, user):
    episode = source["episode"]
    observation = source.get("observation") or {}
    assessment = source.get("assessment")
    global_ = episode["id"].startswith("port-activity:")
    port = observation.get("port") or str(observation.get("berth", "")).split("/")[0]
    expected, capacity = observation.get("expected", 0), observation.get("capacity", 0)
    if global_:
        title = f"{observation.get('name') or port}: {observation.get('state', 'unusual')} activity"
        impact = f"{observation.get('calls', '?')} calls vs {observation.get('usual', '?')} usual per day"
    else:
        title = f"Arrival overlap at {source.get('berth_name') or observation.get('berth', port)}"
        impact = f"{expected} expected together · {capacity} observed together historically"
    status = held.get("status") or (
        "source_cleared"
        if episode.get("closed_at")
        else "needs_review"
        if assessment
        else "investigating"
        if source.get("task") == "claimed"
        else "queued"
    )
    return {
        "id": episode["id"],
        "title": title,
        "impact": impact,
        "scope": "global" if global_ else "finland",
        "port": port,
        "observation_at": observation.get("day") or observation.get("at") or episode["opened_at"],
        "opened_at": episode["opened_at"],
        "source_cleared": bool(episode.get("closed_at")),
        "status": status,
        "owner": held.get("owner"),
        "revision": held.get("revision", 0),
        "action": held.get("action", ""),
        "action_status": held.get("action_status", ""),
        "outcome": held.get("outcome", ""),
        "updated_at": held.get("updated_at"),
        "assessment": assessment,
        "about": source["about"],
        "watching": port in preferences.get("ports", [])
        or bool(set(source.get("vessels", [])) & set(preferences.get("vessels", []))),
        "mine": held.get("owner") == user,
    }


@router.get("/cases")
def cases(graph: Desk, memory: Private, who: User):
    sources, limited = source_rows(graph)
    preferences = profile(memory, who[1])
    held = {
        node.properties["id"]: node.properties
        for (node,) in memory.ro_query(
            "MATCH (c:OpsCase) WHERE c.id IN $ids RETURN c",
            {"ids": list(sources)},
            timeout=2000,
        ).result_set
    }
    found = [
        shown(source, held.get(id_, {}), preferences, who[1]) for id_, source in sources.items()
    ]
    found.sort(key=lambda c: str(c["opened_at"]), reverse=True)
    found.sort(
        key=lambda c: (
            c["status"] in {"resolved", "source_cleared"},
            c["scope"] == "global",
            not c["watching"],
        )
    )
    return {"cases": found, "profile": preferences, "user": who[1], "limited": limited}


def case_source(graph, id_):
    episode = lighthouse.episode(graph, id_)
    if not episode or not id_.startswith(("berth-overload:", "port-activity:")):
        raise HTTPException(404, "Case not found.")
    source = {
        "episode": episode,
        "about": episode.get("about", []),
        "vessels": [
            str(imo)
            for (imo,) in graph.ro_query(
                "MATCH (ep:Episode {id: $id})-[:ABOUT]->(p:PortCall)-[r:MADE_BY]->(v:Vessel) "
                "WHERE r.valid_to IS NULL RETURN DISTINCT v.imo",
                {"id": id_},
                timeout=2000,
            ).result_set
        ],
        **{
            kind: next((e for e in reversed(episode["entries"]) if e["type"] == kind), None)
            for kind in ("observation", "assessment")
        },
    }

    name_locations(graph, {id_: source})
    return source


@router.get("/case")
def case(id: str, graph: Desk, memory: Private, who: User):
    if len(id) > 200:
        raise HTTPException(422, "Case identifier is too long.")
    source = case_source(graph, id)
    events = memory.ro_query(
        "MATCH (c:OpsCase {id: $id})-[:HAS_DECISION]->(e:OpsEvent) "
        "RETURN e ORDER BY e.revision DESC LIMIT 50",
        {"id": id},
        timeout=2000,
    ).result_set
    item = shown(source, decision(memory, id), profile(memory, who[1]), who[1])
    return {
        "case": item,
        "prior_outcomes": prior_outcomes(memory, item["port"], id),
        "source": source["episode"],
        "events": [e.properties for (e,) in events],
        "user": who[1],
        "profile": profile(memory, who[1]),
    }


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    revision: int = Field(ge=0)
    operation: Literal["claim", "release", "propose", "approve", "resolve", "reopen"]
    text: str = Field(default="", max_length=2000)


@router.post("/case")
def change(body: Change, graph: Desk, memory: Private, who: User):
    source = case_source(graph, body.id)
    held = decision(memory, body.id)
    user = who[1]
    if held.get("revision", 0) != body.revision:
        raise HTTPException(409, "This case changed. Refresh before saving.")
    if held.get("owner") not in (None, user):
        raise HTTPException(403, "This case belongs to another teammate.")
    if body.operation != "claim" and held.get("owner") != user:
        raise HTTPException(403, "Take ownership before making a decision.")
    if held.get("status") == "resolved" and body.operation != "reopen":
        raise HTTPException(409, "Reopen this case before making another decision.")
    text = body.text.strip()
    if (
        "\x00" in body.id
        or "\x00" in text
        or (body.operation in {"propose", "resolve"} and not text)
    ):
        raise HTTPException(422, "Add a short explanation before saving.")
    if body.operation == "approve" and (
        not held.get("action") or held.get("action_status") != "proposed"
    ):
        raise HTTPException(409, "Propose a next step before approving it.")
    status = {
        "claim": "investigating",
        "release": "queued",
        "propose": "needs_review",
        "approve": "investigating",
        "resolve": "resolved",
        "reopen": "investigating",
    }[body.operation]
    updates = {"owner": None if body.operation == "release" else user, "status": status}
    observation = source.get("observation") or {}
    updates["port"] = observation.get("port") or str(observation.get("berth", "")).split("/")[0]
    if body.operation == "propose":
        updates |= {"action": text, "action_status": "proposed"}
    if body.operation == "approve":
        updates["action_status"] = "approved"
    if body.operation == "resolve":
        updates["outcome"] = text
    if body.operation == "reopen":
        updates |= {"outcome": "", "action_status": "", "action": ""}
    rows = memory.query(
        "MERGE (c:OpsCase {id: $id}) ON CREATE SET c.revision = 0 "
        "WITH c WHERE c.revision = $revision "
        "SET c += $updates, c.revision = c.revision + 1, c.updated_at = $at, c.updated_by = $user "
        "CREATE (c)-[:HAS_DECISION]->(e:OpsEvent {revision: c.revision, operation: $operation, "
        "text: $text, by: $user, at: $at}) RETURN c.revision",
        {
            **body.model_dump(),
            "updates": updates,
            "user": user,
            "at": lighthouse.now(),
            "text": text,
        },
    ).result_set
    if not rows:
        raise HTTPException(409, "This case changed. Refresh before saving.")
    return {"revision": rows[0][0], "status": status}
