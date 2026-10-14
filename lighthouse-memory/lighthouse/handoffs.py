"""Handoffs: one agent passes work to another by pointing at what the other must read.

  (Agent)-[:GAVE]->(Handoff)-[:TO]->(Agent)
  (Handoff)-[:POINTS_TO {as_of}]->(entry, episode, or entity)

A handoff carries no copy of the work. It points at entries, episodes, and entities in the
graph, so the receiver reads the same record the giver read. It must point at something,
and that thing must exist. Only the agent it was given to can accept it, and only once.
"""

import json

from falkordb import Graph
from redis.exceptions import ResponseError

from lighthouse.clock import now
from lighthouse.episodes import evidence, links, lookup_keys, lookups, moment, pairs, refuse
from lighthouse.read import pages
from lighthouse.values import MAX_SIZE, named, properties

# Properties of a handoff that the library sets. Its values cannot use these names.
HANDOFF_PROPERTIES = {"id", "by", "to", "at", "recorded_at", "accepted_at", "points_to"}


def _give_query(groups: list[tuple]) -> str:
    clauses, names, missing = lookups(groups, "old")
    points = links(groups, "h", "POINTS_TO {{label: '{label}', key: {key}, as_of: t}}")
    return f"""
OPTIONAL MATCH (old:Handoff {{id: $id}})
WITH old{clauses}
WITH old{names}, localdatetime($at) AS t,
  CASE
    WHEN old IS NOT NULL THEN 'exists'
    WHEN false{missing} THEN 'missing'
    ELSE 'given'
  END AS status
FOREACH (_ IN CASE WHEN status = 'given' THEN [1] ELSE [] END |
  CREATE (h:Handoff {{id: $id, by: $by, to: $to, at: t, recorded_at: localdatetime($now)}})
  SET h += $values
  MERGE (giver:Agent {{id: $by}})
  MERGE (receiver:Agent {{id: $to}})
  CREATE (giver)-[:GAVE]->(h)
  CREATE (h)-[:TO]->(receiver){points}
)
RETURN status
"""


# One query reads who the handoff is for and marks it accepted, so it is accepted once.
ACCEPT = """
MATCH (h:Handoff {id: $id})
WITH h,
  CASE
    WHEN h.to <> $by THEN 'refused'
    WHEN h.accepted_at IS NOT NULL THEN 'exists'
    ELSE 'accepted'
  END AS status
FOREACH (_ IN CASE WHEN status = 'accepted' THEN [1] ELSE [] END |
  SET h.accepted_at = localdatetime($now)
)
RETURN status
"""


def hand_off(
    graph: Graph, handoff_id: str, by: str, to: str, points_to, values=None, at=None
) -> dict:
    """Pass work from agent `by` to agent `to`.

      points_to  what the receiver must read: entry ids, ("Episode", id), and entities as
                 (Kind, key). At least one. An entity is pinned to the time of the handoff.
      values     short properties of the handoff, such as what is asked
      at         when it was given (default: now)

    Returns a receipt {"id", "status"} with status
      given    the handoff was made
      exists   a handoff with this id is there already; nothing changed
      missing  something in `points_to` does not exist: refused
      invalid  it points at nothing, or the values, references, or time cannot be stored
      failed   the database refused the query
    Missing, invalid, and failed leave a WriteFailure node that holds the refused handoff.
    """
    named(handoff_id=handoff_id, by=by, to=to)
    content = {"by": by, "to": to, "points_to": points_to, "values": values, "at": at}
    try:
        groups = evidence(points_to, "points_to")
        if not groups:
            raise ValueError("points_to: a handoff must point at something")
        params = {
            "id": handoff_id,
            "by": by,
            "to": to,
            "values": properties(values, HANDOFF_PROPERTIES, "values"),
            "at": moment(at),
            "now": now(),
        }
        if len(json.dumps(params["values"])) > MAX_SIZE:
            raise ValueError(f"the handoff is larger than {MAX_SIZE} characters")
        rows = graph.query(_give_query(groups), params | lookup_keys(groups)).result_set
    except (TypeError, ValueError) as exc:
        return refuse(graph, "Handoff", handoff_id, "invalid", str(exc), content)
    except ResponseError as exc:
        return refuse(graph, "Handoff", handoff_id, "failed", str(exc), content)
    status = rows[0][0]
    if status == "missing":
        reason = "something it points at does not exist"
        return refuse(graph, "Handoff", handoff_id, status, reason, content)
    return {"id": handoff_id, "status": status}


def accept(graph: Graph, handoff_id: str, by: str) -> dict:
    """Take a handoff. Returns a receipt {"id", "status"} with status
      accepted  the handoff is now accepted by the agent it was given to
      exists    that agent accepted it before; nothing changed
      refused   it was given to another agent
      unknown   there is no such handoff
    Refused and unknown leave a WriteFailure node that names who tried.
    """
    named(handoff_id=handoff_id, by=by)
    rows = graph.query(ACCEPT, {"id": handoff_id, "by": by, "now": now()}).result_set
    status = rows[0][0] if rows else "unknown"
    if status in ("refused", "unknown"):
        reason = "it was given to another agent" if rows else "there is no such handoff"
        return refuse(graph, "Handoff", handoff_id, status, reason, {"by": by})
    return {"id": handoff_id, "status": status}


def handoffs_for(graph: Graph, agent: str, waiting_only: bool = True) -> list[dict]:
    """What was handed to an agent, oldest first. Each has "points_to": the (label, key)
    pairs to read. By default only the handoffs the agent has not accepted yet."""
    named(agent=agent)
    waiting = "WHERE h.accepted_at IS NULL " if waiting_only else ""
    rows = pages(
        graph,
        f"MATCH (h:Handoff)-[:TO]->(:Agent {{id: $agent}}) {waiting}"
        "OPTIONAL MATCH (h)-[p:POINTS_TO]->() "
        "WITH h, collect([p.label, p.key]) AS points RETURN h, points ORDER BY h.at, h.id",
        {"agent": agent},
    )
    return [{**node.properties, "points_to": pairs(points)} for node, points in rows]
