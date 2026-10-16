"""Batches: remember() takes rows of one kind, in waves that hold each entity once, and in
queries of a bounded load. A row at or after the current State is written by the query
here; a row that came late goes on to late.py."""

from falkordb import Graph
from redis.exceptions import ResponseError

from lighthouse.clock import now
from lighthouse.kinds import ENTITY, TO_EMBED, VECTOR, Kind
from lighthouse.values import describe, is_key, named
from lighthouse.write.failures import record_failure
from lighthouse.write.late import insert
from lighthouse.write.rows import checked

BATCH = 500  # rows per query: stays under RESULTSET_SIZE
# FalkorDB cannot stop a write that runs too long, and one write blocks every other writer
# of the graph. So a query carries a bounded load: one unit for each row, each relation
# target, and each 1,000 characters.
LOAD = 2_000


# One row per entity. FalkorDB runs one write query at a time per graph and a query is
# atomic, so reading the current State and adding the next one cannot interleave with
# another writer. Rows of one query do not see each other's writes: remember() never puts
# two rows for the same entity in one query.
#
# A row is written only when its time is later than the current State. Every open relation
# edge of the entity started at or before that State, so the edges can be closed and opened
# at the row's time without a check of their own.
#
# `SET e = r.entity` replaces every property of the entity node. A feature that keeps its
# own property on an entity node must change this line.
#
# A row older than the current State with other content comes back 'stale', and goes in
# with late.py, in a second query with the other late rows of the batch.
def _remember_query(kind: Kind) -> str:
    times = "".join(f", {{0}}.{name} = localdatetime(r.times.{name})" for name in kind.times)
    # The open edges of each relation are collected before the writes. A pattern
    # comprehension would be shorter, but in FalkorDB 6.0.2 it corrupts FOREACH variables.
    open_edges, carried, relations = "", "", ""
    for name, target in kind.relations.items():
        open_edges += f"""
OPTIONAL MATCH (e)-[o:{name}]->(x:{target.label}) WHERE o.valid_to IS NULL
WITH r, e, t, src, cur, at, status{carried}, collect(o) AS open_{name}, collect(x.{target.key}) AS have_{name}"""
        carried += f", open_{name}, have_{name}"
        relations += f"""
  FOREACH (o IN [o IN open_{name} WHERE NOT endNode(o).{target.key} IN r.relations.{name}] |
    SET o.valid_to = t)
  FOREACH (k IN [k IN r.relations.{name} WHERE NOT k IN have_{name}] |
    MERGE (y:{target.label}:{ENTITY} {{{target.key}: k}})
    CREATE (e)-[:{name} {{valid_from: t, recorded_at: localdatetime($now), by: $by}}]->(y))"""
    # A vector stands for the text it was made from. When a row changes that text, the
    # vector leaves the index in the same query, so a search by meaning never answers from
    # text that is gone, and the entity waits for embed() with the label ThingToEmbed: a
    # label, because `SET e = r.entity` keeps labels and replaces every property. The text
    # is compared before the entity is written.
    reword = ""
    if kind.dimensions:
        differs = " OR ".join(
            f"coalesce(e.{name}, '') <> coalesce(r.entity.{name}, '')" for name in kind.text
        )
        worded = " OR ".join(f"r.entity.{name} IS NOT NULL" for name in kind.text)
        waits = f"{kind.label}{TO_EMBED}"
        open_edges += f"""
OPTIONAL MATCH (e)-[:EMBEDDED_AS]->(v:{kind.label}{VECTOR})
WITH r, e, t, src, cur, at, status{carried}, collect(v) AS vectors, ({differs}) AS reworded"""
        reword = f"""
  FOREACH (v IN CASE WHEN reworded THEN vectors ELSE [] END | SET v.vector = NULL)
  FOREACH (_ IN CASE WHEN reworded AND ({worded}) THEN [1] ELSE [] END | SET e:{waits})
  FOREACH (_ IN CASE WHEN reworded AND NOT ({worded}) THEN [1] ELSE [] END | REMOVE e:{waits})"""
    return f"""
UNWIND $rows AS r
MERGE (e:{kind.label}:{ENTITY} {{{kind.key}: r.key}})
WITH r, e, localdatetime(r.t) AS t
OPTIONAL MATCH (src:Entry {{id: r.entry}})
OPTIONAL MATCH (e)-[:HAS_STATE]->(cur:State) WHERE cur.valid_to IS NULL
OPTIONAL MATCH (e)-[:HAS_STATE]->(at:State)
  WHERE at.valid_from <= t AND (at.valid_to IS NULL OR at.valid_to > t)
WITH r, e, t, src, cur, at,
  CASE
    // A row of update() was made from the State that began at r.base.from, or from none.
    // A State never changes, so another current State begins at another time. If one has
    // come since, the row is not written: update() reads again.
    WHEN r.base IS NOT NULL AND ((cur IS NULL) <> (r.base.from IS NULL)
         OR cur.valid_from <> localdatetime(r.base.from)) THEN 'moved'
    WHEN cur IS NULL THEN 'created'
    WHEN at.fp = r.fp THEN 'unchanged'
    WHEN at.valid_to IS NULL AND t > at.valid_from
         AND (at.seen_last IS NULL OR at.seen_last < t) THEN 'changed'
    ELSE 'stale'
  END AS status{open_edges}
// A row that repeats the State of its time says that State still held then. A row that
// comes later with a time before that must not run past it: see late.py.
FOREACH (a IN CASE WHEN status = 'unchanged' AND at.valid_from < t
                    AND (at.seen_last IS NULL OR at.seen_last < t) THEN [at] ELSE [] END |
  SET a.seen_last = t)
FOREACH (_ IN CASE WHEN status IN ['created', 'changed'] THEN [1] ELSE [] END |
  SET e = r.entity{times.format("e")}
  CREATE (e)-[:HAS_STATE]->(s:State {{fp: r.fp, valid_from: t,
                                     recorded_at: localdatetime($now), by: $by}})
  SET s += r.values{times.format("s")}
  FOREACH (x IN CASE WHEN src IS NULL THEN [] ELSE [src] END | CREATE (s)-[:FROM]->(x))
  FOREACH (c IN CASE WHEN cur IS NULL THEN [] ELSE [cur] END |
    SET c.valid_to = t
    CREATE (c)-[:NEXT]->(s)){relations}{reword}
)
RETURN r.key AS key, status
"""


def _load(row: dict) -> int:
    targets = sum(len(keys) for keys in row["relations"].values())
    return 1 + targets + len(row["refused"]) // 1000 + len(str(row["values"])) // 1000


def chunks(wave: list[tuple[int, dict]]) -> list[list[tuple[int, dict]]]:
    """A wave cut into queries, each within BATCH rows and LOAD units."""
    chunks, chunk, load = [], [], 0
    for item in wave:
        weight = _load(item[1])
        if chunk and (len(chunk) == BATCH or load + weight > LOAD):
            chunks.append(chunk)
            chunk, load = [], 0
        chunk.append(item)
        load += weight
    return [*chunks, chunk] if chunk else chunks


def remember(graph: Graph, kind: Kind, rows, by: str) -> list[dict]:
    """Store what is true about entities of one kind, from the time `t` of each row.

    A row is {"key", "t", "values", "relations", "entry"}; key and t are required.
      values     properties of the entity. Null or missing means the value is absent.
      relations  {TYPE: key or list of keys} of the entities it points at, for the types
                 declared in the Kind. Missing means it points at none.
      entry      the id of the entry the row comes from, such as an observation. A State
                 that the row adds points at that entry, as its evidence.
    A row is the full picture at time t: what it does not name is no longer true.
    `by` names the agent or source that writes. It is stored on every State and edge.

    Returns one receipt per row, in order: {"key", "status"} with status
      created    first State of the entity
      changed    the row differs: the current State is closed and a new one added
      inserted   the row came late: it is put into the history at its time
      unchanged  the row is already recorded for that time
      stale      the row came late, after a row with a later time that repeated what held
                 before it: where it ends is not known, so it is refused
      conflict   another row with other content has the same time: refused
      missing    the entry it names does not exist: refused
      invalid    the row cannot be stored
      failed     the database refused the query
    Stale, conflicting, missing, invalid, and failed rows leave a WriteFailure node.
    """
    named(by=by)
    rows = list(rows)
    receipts: list[dict | None] = [None] * len(rows)
    pending: list[tuple[int, dict]] = []
    for i, row in enumerate(rows):
        try:
            pending.append((i, checked(kind, row)))
        except (TypeError, ValueError) as exc:
            key = row.get("key") if isinstance(row, dict) else None
            key = key if is_key(key) else None
            record_failure(graph, "invalid", kind.label, key, str(exc))
            receipts[i] = {"key": key, "status": "invalid", "reason": str(exc)}
    return send(graph, kind, pending, by, receipts)


def send(graph: Graph, kind: Kind, pending: list, by: str, receipts: list) -> list[dict]:
    """Write rows that were checked, as [(place, row)], and fill in their receipts."""
    query = _remember_query(kind)
    pending = _known_entries(graph, kind, pending, receipts)
    while pending:
        # A wave holds each entity at most once. Later rows wait for the next wave.
        wave, rest, seen = [], [], set()
        for item in pending:
            (rest if item[1]["key"] in seen else wave).append(item)
            seen.add(item[1]["key"])
        for chunk in chunks(wave):
            keys = [row["key"] for _, row in chunk]
            params = {"rows": [row for _, row in chunk], "now": now(), "by": by}
            try:
                result = graph.query(query, params).result_set
            except ResponseError as exc:
                # The query is atomic: nothing from this chunk was stored.
                record_failure(graph, "failed", kind.label, None, f"{exc} keys={describe(keys)}")
                for i, row in chunk:
                    receipts[i] = {"key": row["key"], "status": "failed", "reason": str(exc)}
                continue
            status = dict(result)
            if len(result) != len(chunk) or set(status) != set(keys):
                raise RuntimeError(
                    f"receipts do not match rows: sent {describe(keys)}, got {describe(result)}"
                )
            late = [(i, row) for i, row in chunk if status[row["key"]] == "stale"]
            for i, row in chunk:
                receipts[i] = {"key": row["key"], "status": status[row["key"]]}
            for (i, _), receipt in zip(late, insert(graph, kind, [row for _, row in late], by)):
                receipts[i] = receipt
        pending = rest
    return receipts


def _known_entries(graph: Graph, kind: Kind, pending: list, receipts: list) -> list:
    """The rows whose entry exists, or that name none. The others are refused as missing.
    Entries are never deleted, so what exists now exists when the rows are written."""
    ids = sorted({row["entry"] for _, row in pending if row["entry"] is not None})
    if not ids:
        return pending
    found = graph.ro_query(
        "UNWIND $ids AS id MATCH (n:Entry {id: id}) RETURN n.id", {"ids": ids}
    ).result_set
    known = {row[0] for row in found}
    kept = []
    for i, row in pending:
        if row["entry"] is None or row["entry"] in known:
            kept.append((i, row))
            continue
        reason = f"the entry {row['entry']!r} does not exist"
        record_failure(graph, "missing", kind.label, row["key"], f"{reason}: {row['refused']}")
        receipts[i] = {"key": row["key"], "status": "missing", "reason": reason}
    return kept
