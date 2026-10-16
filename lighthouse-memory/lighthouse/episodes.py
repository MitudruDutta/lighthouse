"""Episodes: the ordered record of one event, written by agents.

  (Episode)-[:ABOUT]->(entity)                  what the episode is about
  (Episode)-[:HAS]->(Entry)-[:NEXT]->(Entry)    what happened, in the order it was written
  (Entry)-[:CITES {as_of}]->(evidence)          what an entry rests on
  (Agent)-[:WROTE]->(Entry)                     who wrote it

An entry is appended with one query, so entries written at the same moment still get one
order. Evidence must exist: an entry that cites something unknown is refused. A cited entity
is pinned to the time of the entry, so the State the agent saw can be read back with
as_of(). A closed episode takes no more entries. A refused entry leaves a WriteFailure node.
"""

import json

from falkordb import Graph
from redis.exceptions import ResponseError

from lighthouse.clock import is_ahead, now, stamp
from lighthouse.kinds import STAMP, Kind
from lighthouse.read import pages
from lighthouse.values import (
    MAX_REFERENCES,
    MAX_SIZE,
    WORDS,
    describe,
    indexed,
    is_key,
    is_name,
    named,
    properties,
    without_words,
)
from lighthouse.write import record_failure

OUTCOME = "outcome"  # the type of the entry that closes an episode
MAX_ENTRIES = 5_000  # entries in one episode: one event cannot grow without end

# Properties of an entry that the library sets. An entry's values cannot use these names.
# `serial` is the place of the entry among all entries of the graph, in the order they were
# stored: see _append_query().
ENTRY_PROPERTIES = {"id", "seq", "serial", "type", "at", "recorded_at", "by", "cites", WORDS}

# Records of the library that a reference may point at, by label: the property that
# identifies one. Entities of the application are named with their Kind.
RECORDS = {"Entry": "id", "Episode": "id", "Lesson": "id", "Playbook": "id"}
# Edges of the records that say what something is about or rests on. Edges that keep an
# order or name a writer are left out: through an agent, everything is connected.
RECORD_EDGES = ("ABOUT", "HAS", "CITES", "SUPPORTED_BY", "CONTRADICTED_BY", "USED_IN", "RAN_IN")


def evidence(items, what: str, records=tuple(RECORDS)) -> list[tuple[str, str, list]]:
    """References, checked and grouped by what they point at: [(label, key property, keys)].

    A reference is (Kind, key) for an entity, (label, id) for a record of the library
    (Entry, Episode, Lesson, Playbook), or an entry id alone. `records` names the record
    labels allowed here.
    """
    if not isinstance(items, (list, tuple)):
        raise TypeError(f"{what} must be a list of references")
    if len(items) > MAX_REFERENCES:
        raise ValueError(f"{what}: more than {MAX_REFERENCES} references")
    groups: dict[str, tuple[str, list]] = {}
    for item in items:
        pair = ("Entry", item) if is_name(item) else item
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError(f"{what}: not a reference: {describe(item)}")
        target, key = pair
        if isinstance(target, Kind) and is_key(key):
            label, key_property = target.label, target.key
        elif isinstance(target, str) and target in records and is_name(key):
            label, key_property = target, RECORDS[target]
        else:
            raise ValueError(f"{what}: not a reference that is allowed here: {describe(item)}")
        known, keys = groups.setdefault(label, (key_property, []))
        if known != key_property:
            raise ValueError(f"{what}: label {label!r} has two different keys")
        if key not in keys:
            keys.append(key)
    return [(label, key_property, keys) for label, (key_property, keys) in groups.items()]


def lookups(groups: list[tuple], carried: str) -> tuple[str, str, str]:
    """Cypher that finds what the references point at: (clauses, names to carry, the test
    that something is missing). The keys go in as the parameters of lookup_keys()."""
    clauses, names, missing = "", "", ""
    for i, (label, key_property, _) in enumerate(groups):
        clauses += f"""
OPTIONAL MATCH (x{i}:{label}) WHERE x{i}.{key_property} IN $keys_{i}
WITH {carried}{names}, collect(x{i}) AS found_{i}"""
        names += f", found_{i}"
        missing += f" OR size(found_{i}) < size($keys_{i})"
    return clauses, names, missing


def links(groups: list[tuple], source: str, edge: str) -> str:
    """Cypher that links `source` to everything found. The edge names what it points at,
    so a reader needs no Kind to tell what that is."""
    return "".join(
        f"""
  FOREACH (x IN found_{i} |
    CREATE ({source})-[:{edge.format(label=label, key=f"x.{key_property}")}]->(x))"""
        for i, (label, key_property, _) in enumerate(groups)
    )


def lookup_keys(groups: list[tuple]) -> dict:
    return {f"keys_{i}": keys for i, (_, _, keys) in enumerate(groups)}


def moment(at) -> str:
    """The time something happened: the given one, or now. Never ahead of the clock."""
    time = stamp(at) or now()
    if is_ahead(time):
        raise ValueError(f"at is in the future: {time}")
    return time


def _plain(references):
    """References in a form that can be stored as text: (Kind, key) becomes [label, key]."""
    if not isinstance(references, (list, tuple)):
        return references
    return [
        [item[0].label, *item[1:]]
        if isinstance(item, tuple) and item and isinstance(item[0], Kind)
        else item
        for item in references
    ]


def refuse(
    graph: Graph, label: str, key: str, status: str, reason: str, content: dict, owner=None
) -> dict:
    """Store a refused write with what it held, and give the receipt for it."""
    content = {name: _plain(value) for name, value in content.items()}
    detail = f"{reason}: {describe(content)}"  # short and safe, whatever was refused
    record_failure(graph, status, label, key, detail, owner)
    return {"id": None, "status": status, "reason": reason}


def _open_query(groups: list[tuple]) -> str:
    clauses, names, missing = lookups(groups, "old")
    about = links(groups, "ep", "ABOUT {{label: '{label}', key: {key}}}")
    return f"""
OPTIONAL MATCH (old:Episode {{id: $id}})
WITH old{clauses}
WITH old{names},
  CASE
    WHEN old IS NOT NULL THEN 'exists'
    WHEN false{missing} THEN 'missing'
    ELSE 'opened'
  END AS status
FOREACH (_ IN CASE WHEN status = 'opened' THEN [1] ELSE [] END |
  CREATE (ep:Episode {{id: $id, opened_at: localdatetime($at),
                      recorded_at: localdatetime($now), by: $by, entry_count: 0}}){about}
)
RETURN status
"""


# The episode counts its entries. The next entry takes the next number in the same query
# that links it after the last one, so two writers cannot take the same place.
#
# The entry also takes the next serial of the graph from its stamp. FalkorDB runs one write
# of a graph at a time, so serials follow the order in which entries were stored: a job
# that has seen serial n has seen every entry before it, and reads on from there.
def _append_query(groups: list[tuple]) -> str:
    clauses, names, missing = lookups(groups, "ep, last, stamp")
    cites = links(groups, "n", "CITES {{label: '{label}', key: {key}, as_of: t}}")
    return f"""
MATCH (ep:Episode {{id: $id}})
OPTIONAL MATCH (ep)-[:HAS]->(last:Entry {{seq: ep.entry_count}})
OPTIONAL MATCH (stamp:{STAMP})
WITH ep, last, stamp{clauses}
WITH ep, last, stamp{names}, ep.entry_count + 1 AS seq, localdatetime($at) AS t,
  CASE
    WHEN ep.closed_at IS NOT NULL THEN 'closed'
    WHEN ep.entry_count >= $most THEN 'full'
    WHEN false{missing} THEN 'missing'
    ELSE 'recorded'
  END AS status
FOREACH (_ IN CASE WHEN status = 'recorded' THEN [1] ELSE [] END |
  SET ep.entry_count = seq
  FOREACH (s IN CASE WHEN stamp IS NULL THEN [] ELSE [stamp] END |
    SET s.entries = coalesce(s.entries, 0) + 1)
  CREATE (ep)-[:HAS]->(n:Entry {{id: $id + '/' + toString(seq), seq: seq, type: $type, at: t,
                                serial: stamp.entries, recorded_at: localdatetime($now), by: $by}})
  SET n += $values
  MERGE (a:Agent {{id: $by}})
  CREATE (a)-[:WROTE]->(n)
  FOREACH (l IN CASE WHEN last IS NULL THEN [] ELSE [last] END | CREATE (l)-[:NEXT]->(n)){cites}
  FOREACH (_ IN CASE WHEN $close THEN [1] ELSE [] END | SET ep.closed_at = t)
)
RETURN status, seq
"""


REFUSED = {
    "missing": "something it refers to does not exist",
    "closed": "the episode is closed",
    "full": f"the episode has {MAX_ENTRIES} entries",
    "unknown": "the episode does not exist",
}


def open_episode(graph: Graph, episode_id: str, by: str, about=(), at=None) -> dict:
    """Start the record of one event. `about` lists the entities it concerns, as (Kind, key).

    Returns a receipt {"id", "status"} with status
      opened   the episode was made
      exists   an episode with this id is there already; nothing changed
      missing  an entity in `about` does not exist: refused
      invalid  `about` or `at` cannot be used: refused
      failed   the database refused the query
    Missing, invalid, and failed leave a WriteFailure node.
    """
    named(episode_id=episode_id, by=by)
    content = {"about": about, "at": at}
    try:
        groups = evidence(about, "about", records=())
        params = {"id": episode_id, "by": by, "at": moment(at), "now": now()}
        rows = graph.query(_open_query(groups), params | lookup_keys(groups)).result_set
    except (TypeError, ValueError) as exc:
        return refuse(graph, "Episode", episode_id, "invalid", str(exc), content)
    except ResponseError as exc:
        return refuse(graph, "Episode", episode_id, "failed", str(exc), content)
    status = rows[0][0]
    if status == "missing":
        return refuse(graph, "Episode", episode_id, status, REFUSED[status], content)
    return {"id": episode_id, "status": status}


def _append(graph, episode_id, entry_type, by, values, cites, at, close: bool) -> dict:
    named(episode_id=episode_id, entry_type=entry_type, by=by)
    content = {"type": entry_type, "by": by, "values": values, "cites": cites, "at": at}
    try:
        groups = evidence(cites, "cites")
        params = {
            "id": episode_id,
            "type": entry_type,
            "by": by,
            "values": properties(values, ENTRY_PROPERTIES, "values"),
            "close": close,
            "most": MAX_ENTRIES,
            "at": moment(at),
            "now": now(),
        }
        if len(json.dumps(params["values"])) > MAX_SIZE:
            raise ValueError(f"the entry is larger than {MAX_SIZE} characters")
        params["values"] = params["values"] | indexed(params["values"].values())
        rows = graph.query(_append_query(groups), params | lookup_keys(groups)).result_set
    except (TypeError, ValueError) as exc:
        return refuse(graph, "Entry", episode_id, "invalid", str(exc), content)
    except ResponseError as exc:
        return refuse(graph, "Entry", episode_id, "failed", str(exc), content)
    status, seq = rows[0] if rows else ("unknown", None)
    if status != "recorded":
        return refuse(graph, "Entry", episode_id, status, REFUSED[status], content)
    return {"id": f"{episode_id}/{seq}", "seq": seq, "status": status}


def record(
    graph: Graph, episode_id: str, entry_type: str, by: str, values=None, cites=(), at=None
) -> dict:
    """Append one entry to an episode: an observation, a forecast, an action, or any other
    type the application names.

      values  properties of the entry
      cites   the evidence: ids of earlier entries, entities as (Kind, key), and other
              episodes as ("Episode", id)
      at      when it happened (default: now)

    Returns a receipt. {"id", "seq", "status": "recorded"} when stored. Otherwise
    {"id": None, "status", "reason"} with status
      unknown  the episode does not exist
      closed   the episode is closed
      full     the episode has 5,000 entries
      missing  something in `cites` does not exist
      invalid  `values`, `cites`, or `at` cannot be stored
      failed   the database refused the query
    and a WriteFailure node that holds the refused entry.
    """
    if entry_type == OUTCOME:
        raise ValueError("an outcome is recorded with close_episode()")
    return _append(graph, episode_id, entry_type, by, values, cites, at, close=False)


def close_episode(graph: Graph, episode_id: str, by: str, outcome=None, cites=(), at=None) -> dict:
    """Record what the event ended in, and close the episode. The outcome is the last entry.
    Returns the same receipt as record()."""
    return _append(graph, episode_id, OUTCOME, by, outcome, cites, at, close=True)


def pairs(found) -> list[tuple]:
    """What edges point at, as sorted (label, key) pairs. Each pair is a reference again."""
    return sorted({(label, key) for label, key in found if label is not None}, key=str)


def _shown(entry: dict) -> dict:
    """An entry as a reader gets it: without the words the index reads, and without its
    serial, which only the jobs that read entries off the write path use."""
    return {name: value for name, value in without_words(entry).items() if name != "serial"}


def episode(graph: Graph, episode_id: str) -> dict | None:
    """An episode with its entries in order, or None if it does not exist. Each entry has
    "cites": the (label, key) pairs it rests on. "about" has the same form."""
    named(episode_id=episode_id)
    found = graph.ro_query(
        "MATCH (ep:Episode {id: $id}) OPTIONAL MATCH (ep)-[a:ABOUT]->() "
        "RETURN ep, collect([a.label, a.key])",
        {"id": episode_id},
    ).result_set
    if not found:
        return None
    entries = graph.ro_query(
        "MATCH (:Episode {id: $id})-[:HAS]->(n:Entry) OPTIONAL MATCH (n)-[c:CITES]->() "
        "WITH n, collect([c.label, c.key]) AS cites RETURN n, cites ORDER BY n.seq",
        {"id": episode_id},
    ).result_set
    return {
        **found[0][0].properties,
        "about": pairs(found[0][1]),
        "entries": [{**_shown(node.properties), "cites": pairs(cites)} for node, cites in entries],
    }


def ended(graph: Graph) -> list[str]:
    """Ids of the episodes that have ended, in the order they ended."""
    query = "MATCH (ep:Episode) WHERE ep.closed_at IS NOT NULL RETURN ep.id ORDER BY ep.closed_at, ep.id"
    return [row[0] for row in pages(graph, query, {})]


def episodes_about(graph: Graph, kind: Kind, key) -> list[dict]:
    """The episodes about one entity, newest first. Each has "outcome": the entry that
    closed it, or None while it is open."""
    if not is_key(key):
        raise ValueError(f"key must be a name or an integer, got {describe(key)}")
    rows = pages(
        graph,
        f"MATCH (:{kind.label} {{{kind.key}: $key}})<-[:ABOUT]-(ep:Episode) "
        f"OPTIONAL MATCH (ep)-[:HAS]->(o:Entry {{type: '{OUTCOME}'}}) "
        "RETURN ep, o ORDER BY ep.opened_at DESC, ep.id DESC",
        {"key": key},
    )
    return [
        {**ep.properties, "outcome": _shown(outcome.properties) if outcome else None}
        for ep, outcome in rows
    ]
