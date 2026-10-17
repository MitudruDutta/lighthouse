"""Reads of what was true: the versions of an entity, and its state at any time."""

from falkordb import Graph

from lighthouse.clock import stamp
from lighthouse.kinds import Kind
from lighthouse.values import describe, is_key, without_words

# FalkorDB cuts a result at RESULTSET_SIZE (10,000 by default) without a sign. A read that
# may be longer is taken in pages, so nothing is lost at the end.
PAGE = 5_000
# A read can be stopped, a write cannot. A read whose cost depends on how well connected
# the graph is gets this many milliseconds.
READ_TIMEOUT = 5_000


# A State points at the entry it came from, when the row named one.
EVIDENCE = "OPTIONAL MATCH (s)-[:FROM]->(n:Entry) RETURN s, n.id"


def version(state, entry) -> dict:
    """A State as a map of its values, with "entry": the id of its evidence, if it has one."""
    return without_words(state.properties) | ({"entry": entry} if entry is not None else {})


def pages(graph: Graph, query: str, params: dict, timeout: int | None = None) -> list:
    """Every row of a read query that ends in ORDER BY, however many there are. `timeout`
    is milliseconds for each page, for a read whose cost grows with the history it reads;
    without one, the server's own limit holds."""
    rows, skip = [], 0
    while True:
        page = graph.ro_query(
            f"{query} SKIP $skip LIMIT $page",
            params | {"skip": skip, "page": PAGE},
            timeout=timeout,
        )
        rows += page.result_set
        if len(page.result_set) < PAGE:
            return rows
        skip += PAGE


def _when(when) -> str:
    text = stamp(when)
    if text is None:
        raise ValueError("when (the time to read) is missing")
    return text


def _key(key):
    if not is_key(key):
        raise ValueError(f"key must be a name or an integer, got {describe(key)}")
    return key


def history(graph: Graph, kind: Kind, key) -> list[dict]:
    """Every State of an entity, oldest first. A State that a row with an entry added has
    "entry": the id of that entry."""
    query = (
        f"MATCH (:{kind.label} {{{kind.key}: $key}})-[:HAS_STATE]->(s:State) "
        f"{EVIDENCE} ORDER BY s.valid_from"
    )
    return [version(*row) for row in pages(graph, query, {"key": _key(key)})]


def as_of(graph: Graph, kind: Kind, key, when) -> dict | None:
    """The State that was valid at `when`, or None if the entity was not known then."""
    query = (
        f"MATCH (:{kind.label} {{{kind.key}: $key}})-[:HAS_STATE]->(s:State) "
        "WHERE s.valid_from <= localdatetime($when) "
        f"AND (s.valid_to IS NULL OR s.valid_to > localdatetime($when)) {EVIDENCE}"
    )
    rows = graph.ro_query(query, {"key": _key(key), "when": _when(when)}).result_set
    return version(*rows[0]) if rows else None


def related(graph: Graph, kind: Kind, key, relation: str, when=None) -> list:
    """Keys of the entities that `key` pointed at through `relation` at `when` (default: now)."""
    if relation not in kind.relations:
        raise ValueError(f"{kind.label} has no relation {relation!r}")
    target = kind.relations[relation]
    window = "o.valid_to IS NULL"
    params = {"key": _key(key)}
    if when is not None:
        window = (
            "o.valid_from <= localdatetime($when) "
            "AND (o.valid_to IS NULL OR o.valid_to > localdatetime($when))"
        )
        params["when"] = _when(when)
    query = (
        f"MATCH (:{kind.label} {{{kind.key}: $key}})-[o:{relation}]->(x:{target.label}) "
        f"WHERE {window} RETURN x.{target.key} ORDER BY x.{target.key}"
    )
    return [row[0] for row in pages(graph, query, params)]
