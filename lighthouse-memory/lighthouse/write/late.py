"""Late rows: a row whose time is inside an earlier State, or before the first, is put into
the history at its time, in one query for the late rows of a batch."""

from falkordb import Graph
from redis.exceptions import ResponseError

from lighthouse.clock import now
from lighthouse.kinds import ENTITY, Kind
from lighthouse.values import describe
from lighthouse.write.failures import record_failure


# A row that came late: its time t is inside a State that is closed, or before the first,
# or inside the current State before a row that repeated it. It holds from t until the next
# State starts ("until"), so the State that held at t now ends at t. If the row says what
# the next State says, the next State starts earlier instead, and its old start is kept as
# a time a row repeated it. Each relation edge that held at t and that the row does not
# name is cut out of that stretch of time: it ends at t, and goes on from "until" as an edge
# of its own. Each target that the row names and that no edge held at t gets an edge for
# the stretch, or an edge that starts at "until" starts at t instead. So the history is the
# one that the rows give in the order of their times.
#
# The library does not keep every row, only the changes, and for each State the last time a
# row repeated it (seen_last). A repeat after t says the State held again after the late row
# began, at a time the library no longer knows exactly. Such a row is refused as 'stale' and
# stored as a WriteFailure, never placed wrong. A repeat at t itself is a 'conflict'.
#
# The NEXT edge between the State at t and the next one is deleted: the only thing a write
# deletes. The query gives the graph a new stamp in the same step, for what relies on a
# graph that only grows.
def _insert_query(kind: Kind) -> str:
    times = "".join(f", {{0}}.{name} = localdatetime(r.times.{name})" for name in kind.times)
    gather, carried, relations = "", "", ""
    for name, target in kind.relations.items():
        # Collected before any write, with what each edge points at and when it ends.
        # A missing match collects nulls, so every list is read with "WHERE i[0] IS NOT NULL".
        gather += f"""
OPTIONAL MATCH (e)-[o:{name}]->(x:{target.label})
  WHERE o.valid_from <= t AND (o.valid_to IS NULL OR o.valid_to > t)
WITH r, e, t, src, until, at, after, old, stamp, status{carried},
  collect([o, x.{target.key}, o.valid_to, x]) AS held_{name}
OPTIONAL MATCH (e)-[o:{name}]->(x:{target.label}) WHERE o.valid_from = until
WITH r, e, t, src, until, at, after, old, stamp, status{carried}, held_{name},
  collect([o, x.{target.key}]) AS next_{name}"""
        carried += f", held_{name}, next_{name}"
        relations += f"""
  FOREACH (o IN [i IN held_{name} WHERE i[0] IS NOT NULL AND NOT i[1] IN r.relations.{name} | i[0]] |
    SET o.valid_to = t)
  FOREACH (i IN [i IN held_{name} WHERE i[0] IS NOT NULL AND NOT i[1] IN r.relations.{name}
                 AND (i[2] IS NULL OR i[2] > until)] |
    FOREACH (y IN [i[3]] |
      CREATE (e)-[:{name} {{valid_from: until, valid_to: i[2],
                          recorded_at: i[0].recorded_at, by: i[0].by}}]->(y)))
  FOREACH (o IN [i IN next_{name} WHERE i[0] IS NOT NULL AND i[1] IN r.relations.{name} | i[0]] |
    SET o.valid_from = t)
  FOREACH (k IN [k IN r.relations.{name}
                 WHERE NOT k IN [i IN held_{name} WHERE i[0] IS NOT NULL | i[1]]
                 AND NOT k IN [i IN next_{name} WHERE i[0] IS NOT NULL | i[1]]] |
    MERGE (y:{target.label}:{ENTITY} {{{target.key}: k}})
    CREATE (e)-[:{name} {{valid_from: t, valid_to: until,
                        recorded_at: localdatetime($now), by: $by}}]->(y))"""
    return f"""
UNWIND $rows AS r
MATCH (e:{kind.label}:{ENTITY} {{{kind.key}: r.key}})
WITH r, e, localdatetime(r.t) AS t
OPTIONAL MATCH (src:Entry {{id: r.entry}})
OPTIONAL MATCH (e)-[:HAS_STATE]->(same:State) WHERE same.valid_from = t
OPTIONAL MATCH (e)-[:HAS_STATE]->(at:State)
  WHERE at.valid_from < t AND (at.valid_to IS NULL OR at.valid_to > t)
OPTIONAL MATCH (e)-[:HAS_STATE]->(later:State) WHERE later.valid_from > t
WITH r, e, t, src, same, at, min(later.valid_from) AS until
// An optional match right after an aggregate, on its value, finds nothing in FalkorDB:
// the value passes through a WITH of its own first.
WITH r, e, t, src, same, at, until
OPTIONAL MATCH (e)-[:HAS_STATE]->(after:State) WHERE after.valid_from = until
OPTIONAL MATCH (at)-[old:NEXT]->(after)
OPTIONAL MATCH (stamp:Stamp)
WITH r, e, t, src, until, at, after, old, stamp,
  CASE
    WHEN same IS NOT NULL AND same.fp = r.fp THEN 'unchanged'
    WHEN same IS NOT NULL THEN 'conflict'
    WHEN at IS NOT NULL AND at.fp = r.fp THEN 'unchanged'
    WHEN at.seen_last = t THEN 'conflict'
    WHEN at.seen_last > t OR after IS NULL THEN 'stale'
    ELSE 'inserted'
  END AS status{gather}
FOREACH (a IN CASE WHEN status = 'unchanged' AND at IS NOT NULL
                    AND (at.seen_last IS NULL OR at.seen_last < t) THEN [at] ELSE [] END |
  SET a.seen_last = t)
FOREACH (_ IN CASE WHEN status = 'inserted' THEN [1] ELSE [] END |
  FOREACH (a IN CASE WHEN at IS NULL THEN [] ELSE [at] END | SET a.valid_to = t)
  // The next State starts earlier. Its old start becomes a time a row repeated it.
  FOREACH (n IN CASE WHEN after.fp = r.fp THEN [after] ELSE [] END |
    SET n.seen_last = CASE WHEN n.seen_last IS NULL THEN n.valid_from ELSE n.seen_last END,
        n.valid_from = t)
  FOREACH (_ IN CASE WHEN after.fp = r.fp THEN [] ELSE [1] END |
    CREATE (e)-[:HAS_STATE]->(s:State {{fp: r.fp, valid_from: t, valid_to: until,
                                       recorded_at: localdatetime($now), by: $by}})
    SET s += r.values{times.format("s")}
    FOREACH (x IN CASE WHEN src IS NULL THEN [] ELSE [src] END | CREATE (s)-[:FROM]->(x))
    CREATE (s)-[:NEXT]->(after)
    FOREACH (a IN CASE WHEN at IS NULL THEN [] ELSE [at] END | CREATE (a)-[:NEXT]->(s))
    FOREACH (n IN CASE WHEN old IS NULL THEN [] ELSE [old] END | DELETE n)
    FOREACH (x IN CASE WHEN old IS NULL OR stamp IS NULL THEN [] ELSE [stamp] END |
      SET x.id = randomUUID())){relations}
)
RETURN r.key AS key, status
"""


def insert(graph: Graph, kind: Kind, rows: list[dict], by: str) -> list[dict]:
    """Put rows that came late into the history, in one query: rows of other entities, and
    no more than one query of remember() took."""
    if not rows:
        return []
    keys = [row["key"] for row in rows]
    try:
        result = graph.query(_insert_query(kind), {"rows": rows, "now": now(), "by": by})
    except ResponseError as exc:
        # The query is atomic: nothing from these rows was stored.
        record_failure(graph, "failed", kind.label, None, f"{exc} keys={describe(keys)}")
        return [{"key": key, "status": "failed", "reason": str(exc)} for key in keys]
    status = dict(result.result_set)
    receipts = []
    for row in rows:
        receipts.append({"key": row["key"], "status": status[row["key"]]})
        if status[row["key"]] in ("conflict", "stale"):
            record_failure(graph, status[row["key"]], kind.label, row["key"], row["refused"])
    return receipts
