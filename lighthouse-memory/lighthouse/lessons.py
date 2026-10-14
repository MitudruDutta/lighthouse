"""Lessons: what was learned from episodes that ended. The semantic memory.

  (Lesson)-[:SUPPORTED_BY]->(Episode)       the episodes that agree with it
  (Lesson)-[:CONTRADICTED_BY]->(Episode)    the episodes that do not
  (Lesson)-[:USED_IN {helped}]->(Episode)   where it was used, and whether that helped
  (Lesson)-[:ABOUT]->(entity)               what it is about
  (Agent)-[:WROTE]->(Lesson)

A lesson with no evidence is not stored: it rests on at least one episode that has ended.
The library writes no lesson of its own. An agent or a rule of the application says what
was learned; the library keeps the evidence, counts it, and ranks by it. The weight of a
lesson is what agrees with it and where it helped, minus what contradicts it and where it
failed. A lesson that is retired stays in the graph and is no longer given out.
"""

import json

from falkordb import Graph
from redis.exceptions import ResponseError

from lighthouse.clock import now, stamp
from lighthouse.episodes import evidence, links, lookup_keys, lookups, moment, pairs, refuse
from lighthouse.kinds import Kind
from lighthouse.read import pages
from lighthouse.values import (
    MAX_REFERENCES,
    MAX_SIZE,
    MAX_TEXT,
    describe,
    is_key,
    is_name,
    is_storable,
    named,
    properties,
)

# Properties of a lesson that the library sets. Its values cannot use these names.
LESSON_PROPERTIES = {"id", "statement", "by", "at", "recorded_at", "touched_at", "weight"}
LESSON_PROPERTIES |= {"support", "against", "used", "helped", "failed"}
LESSON_PROPERTIES |= {
    "retired_at",
    "retired_by",
    "retired_why",
    "supported_by",
    "contradicted_by",
    "about",
}

WEIGHT = "l.support - l.against + l.helped - l.failed"


def _episodes(ids, what: str) -> list[str]:
    """Ids of episodes, checked and without doubles."""
    if not isinstance(ids, (list, tuple)) or len(ids) > MAX_REFERENCES:
        raise ValueError(f"{what} must be a list of at most {MAX_REFERENCES} episode ids")
    if not all(is_name(item) for item in ids):
        raise ValueError(f"{what}: not an episode id in {describe(ids)}")
    return list(dict.fromkeys(ids))


def _learn_query(groups: list[tuple]) -> str:
    clauses, names, missing = lookups(groups, "old, proof")
    about = links(groups, "l", "ABOUT {{label: '{label}', key: {key}}}")
    return f"""
OPTIONAL MATCH (old:Lesson {{id: $id}})
WITH old
OPTIONAL MATCH (ep:Episode) WHERE ep.id IN $episodes AND ep.closed_at IS NOT NULL
WITH old, collect(ep) AS proof{clauses}
WITH old, proof{names}, localdatetime($at) AS t,
  CASE
    WHEN old IS NOT NULL THEN 'exists'
    WHEN size(proof) < size($episodes){missing} THEN 'missing'
    ELSE 'learned'
  END AS status
FOREACH (_ IN CASE WHEN status = 'learned' THEN [1] ELSE [] END |
  CREATE (l:Lesson {{id: $id, statement: $statement, by: $by, at: t, touched_at: t,
                    recorded_at: localdatetime($now), support: size(proof), against: 0,
                    used: 0, helped: 0, failed: 0}})
  SET l += $values
  MERGE (a:Agent {{id: $by}})
  CREATE (a)-[:WROTE]->(l)
  FOREACH (ep IN proof | CREATE (l)-[:SUPPORTED_BY {{at: t, by: $by}}]->(ep)){about}
)
RETURN status
"""


# The counts are worked out before any write: a FOREACH sees what an earlier FOREACH set.
WEIGH = """
MATCH (l:Lesson {id: $id})
OPTIONAL MATCH (ep:Episode {id: $episode}) WHERE ep.closed_at IS NOT NULL
OPTIONAL MATCH (l)-[seen:SUPPORTED_BY|CONTRADICTED_BY]->(ep)
WITH l, ep, localdatetime($at) AS t,
  CASE
    WHEN l.retired_at IS NOT NULL THEN 'retired'
    WHEN ep IS NULL THEN 'missing'
    WHEN seen IS NOT NULL THEN 'exists'
    ELSE 'weighed'
  END AS status
FOREACH (_ IN CASE WHEN status = 'weighed' AND $agrees THEN [1] ELSE [] END |
  CREATE (l)-[:SUPPORTED_BY {at: t, by: $by}]->(ep)
  SET l.support = l.support + 1, l.touched_at = t)
FOREACH (_ IN CASE WHEN status = 'weighed' AND NOT $agrees THEN [1] ELSE [] END |
  CREATE (l)-[:CONTRADICTED_BY {at: t, by: $by}]->(ep)
  SET l.against = l.against + 1, l.touched_at = t)
RETURN status
"""

USED = """
MATCH (l:Lesson {id: $id})
OPTIONAL MATCH (ep:Episode {id: $episode})
OPTIONAL MATCH (l)-[use:USED_IN]->(ep)
WITH l, ep, use, localdatetime($at) AS t,
  CASE
    WHEN l.retired_at IS NOT NULL THEN 'retired'
    WHEN ep IS NULL THEN 'missing'
    WHEN use IS NULL THEN 'used'
    WHEN use.helped IS NULL AND $helped IS NOT NULL THEN 'judged'
    ELSE 'exists'
  END AS status
WITH l, ep, use, t, status,
  CASE WHEN status IN ['used', 'judged'] AND $helped = true THEN 1 ELSE 0 END AS helped,
  CASE WHEN status IN ['used', 'judged'] AND $helped = false THEN 1 ELSE 0 END AS failed
FOREACH (_ IN CASE WHEN status = 'used' THEN [1] ELSE [] END |
  CREATE (l)-[:USED_IN {at: t, by: $by, helped: $helped}]->(ep)
  SET l.used = l.used + 1)
FOREACH (u IN CASE WHEN status = 'judged' THEN [use] ELSE [] END |
  SET u.helped = $helped, u.judged_by = $by)
FOREACH (_ IN CASE WHEN status IN ['used', 'judged'] THEN [1] ELSE [] END |
  SET l.helped = l.helped + helped, l.failed = l.failed + failed, l.touched_at = t)
RETURN status
"""

RETIRE = """
MATCH (l:Lesson {id: $id})
WITH l, CASE WHEN l.retired_at IS NOT NULL THEN 'exists' ELSE 'done' END AS status
FOREACH (_ IN CASE WHEN status = 'done' THEN [1] ELSE [] END |
  SET l.retired_at = localdatetime($at), l.retired_by = $by, l.retired_why = $why)
RETURN status
"""

REFUSED = {
    "missing": "an episode it rests on does not exist or has not ended",
    "retired": "the lesson is retired",
    "unknown": "there is no such lesson",
}


def learn(
    graph: Graph,
    lesson_id: str,
    by: str,
    statement: str,
    supported_by,
    about=(),
    values=None,
    at=None,
) -> dict:
    """Store what was learned, with the episodes it was learned from.

      statement     the lesson, in words
      supported_by  ids of episodes that have ended. At least one.
      about         the entities it is about, as (Kind, key)
      values        other properties of the lesson

    Returns a receipt {"id", "status"} with status
      learned  the lesson was stored
      exists   a lesson with this id is there already; nothing changed
      missing  an episode has not ended or does not exist, or an entity does not exist
      invalid  no statement, no episode, or something that cannot be stored
      failed   the database refused the query
    Missing, invalid, and failed leave a WriteFailure node that holds the refused lesson.
    """
    named(lesson_id=lesson_id, by=by)
    content = {
        "statement": statement,
        "supported_by": supported_by,
        "about": about,
        "values": values,
    }
    try:
        if not isinstance(statement, str) or not statement.strip() or not is_storable(statement):
            raise ValueError(f"statement must be text of 1 to {MAX_TEXT} characters")
        episodes = _episodes(supported_by, "supported_by")
        if not episodes:
            raise ValueError("supported_by: a lesson rests on at least one episode")
        groups = evidence(about, "about", records=())
        params = {
            "id": lesson_id,
            "by": by,
            "statement": statement,
            "episodes": episodes,
            "values": properties(values, LESSON_PROPERTIES, "values"),
            "at": moment(at),
            "now": now(),
        }
        if len(json.dumps(params["values"])) > MAX_SIZE:
            raise ValueError(f"the lesson is larger than {MAX_SIZE} characters")
        rows = graph.query(_learn_query(groups), params | lookup_keys(groups)).result_set
    except (TypeError, ValueError) as exc:
        return refuse(graph, "Lesson", lesson_id, "invalid", str(exc), content)
    except ResponseError as exc:
        return refuse(graph, "Lesson", lesson_id, "failed", str(exc), content)
    status = rows[0][0]
    if status == "missing":
        return refuse(graph, "Lesson", lesson_id, status, REFUSED[status], content)
    return {"id": lesson_id, "status": status}


def _change(graph: Graph, lesson_id: str, query: str, params: dict, content: dict) -> dict:
    """Run a query that changes one lesson. Refusals are stored, like every refused write."""
    try:
        rows = graph.query(query, {"id": lesson_id, "at": moment(params.pop("at")), **params})
    except (TypeError, ValueError) as exc:
        return refuse(graph, "Lesson", lesson_id, "invalid", str(exc), content)
    except ResponseError as exc:
        return refuse(graph, "Lesson", lesson_id, "failed", str(exc), content)
    status = rows.result_set[0][0] if rows.result_set else "unknown"
    if status in REFUSED:
        return refuse(graph, "Lesson", lesson_id, status, REFUSED[status], content)
    return {"id": lesson_id, "status": status}


def weigh(graph: Graph, lesson_id: str, by: str, episode_id: str, agrees: bool, at=None) -> dict:
    """Add an episode that ended as evidence for a lesson, or against it. An episode counts
    once. Status: weighed, exists, or the refusals missing, retired, unknown."""
    named(lesson_id=lesson_id, by=by, episode_id=episode_id)
    if type(agrees) is not bool:
        raise TypeError("agrees must be True or False")
    params = {"by": by, "episode": episode_id, "agrees": agrees, "at": at}
    return _change(
        graph, lesson_id, WEIGH, params, {"by": by, "episode": episode_id, "agrees": agrees}
    )


def used(graph: Graph, lesson_id: str, by: str, episode_id: str, helped=None, at=None) -> dict:
    """Record that a lesson was used in an episode. `helped` says whether acting on it led
    to a correct result: True, False, or None while that is not known. It can be said once,
    in this call or a later one. Status: used, judged, exists, or a refusal."""
    named(lesson_id=lesson_id, by=by, episode_id=episode_id)
    if helped is not None and type(helped) is not bool:
        raise TypeError("helped must be True, False, or None")
    params = {"by": by, "episode": episode_id, "helped": helped, "at": at}
    return _change(
        graph, lesson_id, USED, params, {"by": by, "episode": episode_id, "helped": helped}
    )


def retire(graph: Graph, lesson_id: str, by: str, why: str, at=None) -> dict:
    """Say that a lesson no longer holds. It stays in the graph with its evidence, and is no
    longer given out. Status: retired, exists (it was retired before), or unknown."""
    named(lesson_id=lesson_id, by=by, why=why)
    content = {"by": by, "why": why}
    receipt = _change(graph, lesson_id, RETIRE, {"by": by, "why": why, "at": at}, content)
    # The query says 'done': 'retired' is what a change to a retired lesson is refused with.
    return receipt | {"status": "retired"} if receipt["status"] == "done" else receipt


def lesson(graph: Graph, lesson_id: str) -> dict | None:
    """A lesson with its weight, the episodes for and against it, and what it is about."""
    named(lesson_id=lesson_id)
    rows = graph.ro_query(
        f"MATCH (l:Lesson {{id: $id}}) "
        "OPTIONAL MATCH (l)-[e:SUPPORTED_BY|CONTRADICTED_BY]->(ep:Episode) "
        f"WITH l, {WEIGHT} AS weight, collect([type(e), ep.id]) AS proof "
        "OPTIONAL MATCH (l)-[a:ABOUT]->() RETURN l, weight, proof, collect([a.label, a.key])",
        {"id": lesson_id},
    ).result_set
    if not rows:
        return None
    node, weight, proof, about = rows[0]
    return {
        **node.properties,
        "weight": weight,
        "supported_by": sorted(ep for kind, ep in proof if kind == "SUPPORTED_BY"),
        "contradicted_by": sorted(ep for kind, ep in proof if kind == "CONTRADICTED_BY"),
        "about": pairs(about),
    }


def lessons_about(graph: Graph, kind: Kind, key, at_least: int = 1, since=None) -> list[dict]:
    """The lessons about one entity that still hold, heaviest first. Each has "weight".

    at_least  the least weight a lesson needs to be given out
    since     leave out lessons that no episode has supported, contradicted, or used
              since this time: a lesson that nothing touches fades
    """
    if not is_key(key):
        raise ValueError(f"key must be a name or an integer, got {describe(key)}")
    if type(at_least) is not int:
        raise ValueError("at_least must be a whole number")
    params = {"key": key, "at_least": at_least}
    recent = ""
    if since is not None:
        params["since"] = stamp(since)
        if params["since"] is None:
            raise ValueError("since is not a time")
        recent = "AND l.touched_at >= localdatetime($since) "
    rows = pages(
        graph,
        f"MATCH (:{kind.label} {{{kind.key}: $key}})<-[:ABOUT]-(l:Lesson) "
        f"WHERE l.retired_at IS NULL AND {WEIGHT} >= $at_least {recent}"
        f"RETURN l, {WEIGHT} AS weight ORDER BY weight DESC, l.touched_at DESC, l.id",
        params,
    )
    return [{**node.properties, "weight": weight} for node, weight in rows]
