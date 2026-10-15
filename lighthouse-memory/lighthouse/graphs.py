"""Which graph holds what, and the schema a graph needs before the first write."""

import re
import time

from falkordb import FalkorDB, Graph
from redis.exceptions import ResponseError

from lighthouse.kinds import MAX_DIMENSIONS, STAMP, VECTOR, all_kinds
from lighthouse.values import WORDS

WORLD = "world"

_TENANT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}")


def world(db: FalkorDB) -> Graph:
    """The graph every tenant may read."""
    return db.select_graph(WORLD)


def tenant(db: FalkorDB, tenant_id: str) -> Graph:
    """The private graph of one tenant. FalkorDB accepts any graph name, so the identifier
    is checked here: a tenant can never name the world graph or another tenant's graph."""
    if not isinstance(tenant_id, str) or not _TENANT_ID.fullmatch(tenant_id):
        raise ValueError(f"invalid tenant id: {tenant_id!r}")
    return db.select_graph(f"tenant:{tenant_id}")


def _vector_index(graph: Graph, label: str, dimensions: int) -> None:
    """An index for search by meaning. efRuntime is 100: the default of 10 found 85 of 100
    true neighbours in a test, 100 found all of them."""
    try:
        graph.query(
            f"CREATE VECTOR INDEX FOR (v:{label}) ON (v.vector) OPTIONS "
            f"{{dimension: {dimensions}, similarityFunction: 'cosine', "
            "M: 16, efConstruction: 200, efRuntime: 100}"
        )
    except ResponseError as exc:
        if "already indexed" not in str(exc):
            raise
    # A vector of another size is stored without an error and never found. So an index that
    # was made for another size must stop the start, not be used.
    found = graph.ro_query(
        "CALL db.indexes() YIELD label, options WHERE label = $label RETURN options.vector.dimension",
        {"label": label},
    ).result_set
    if found[0][0] != dimensions:
        raise RuntimeError(f"{label} is indexed for {found[0][0]} dimensions, not {dimensions}")


def _create(create, label: str, prop: str, deadline: float) -> None:
    """Make one index or constraint, unless it is there. FalkorDB refuses to make one while
    another is being made ("another write is in progress"), as when two processes start on
    one graph together: then ask again, until `deadline`."""
    while True:
        try:
            create(label, prop)
            return
        except ResponseError as exc:
            text = str(exc)
            if "already indexed" in text or "already exists" in text:
                return
            if "another write is in progress" not in text or time.monotonic() > deadline:
                raise
        time.sleep(0.05)


def ensure_schema(
    graph: Graph, kinds=(), wait_seconds: float = 10.0, entry_dimensions: int = 0
) -> None:
    """Create a unique constraint on the key of every kind, a full-text index on the text
    of every kind and of its States, a vector index for every kind with dimensions, and the
    engine's own indexes, among them the full-text index of entries. With `entry_dimensions`,
    entries get a vector index of that size too, for embed_entries() and nearest_entries(). Give the graph its stamp, once.
    A duplicate key then fails the whole query. Safe to call on every start.

    Call it before the first write. When it adds a kind to a graph that is in use, stop
    the writers first: a write during the build of an index is lost from that index."""
    graph.query(f"MERGE (s:{STAMP}) ON CREATE SET s.id = randomUUID()")
    keys = {("Task", "id"), ("Agent", "id"), ("Episode", "id"), ("Entry", "id"), ("Handoff", "id")}
    keys |= {("Lesson", "id"), ("Playbook", "id")}
    keys |= {("Session", "key"), ("Message", "key"), ("Reference", "key")}
    declared = all_kinds(kinds).values()
    keys |= {(kind.label, kind.key) for kind in declared}
    indexes = [(graph.create_node_range_index, "Task", "status")]
    indexes += [(graph.create_node_range_index, "Playbook", "name")]
    indexes += [(graph.create_node_range_index, "Session", "user")]
    indexes += [(graph.create_node_range_index, "WriteFailure", "owner")]
    indexes += [(graph.create_node_range_index, "WriteFailure", "same")]
    # Full-text indexes read the words a node keeps of its text, never the text as it is.
    searched = ["Message", "Entry"] + [k.label for k in declared if k.text]
    searched += ["State"] if any(k.text for k in declared) else []  # every version, all kinds
    indexes += [(graph.create_node_fulltext_index, label, WORDS) for label in searched]
    deadline = time.monotonic() + wait_seconds
    for create, label, prop in indexes:
        _create(create, label, prop, deadline)
    for kind in declared:
        if kind.dimensions:
            _vector_index(graph, f"{kind.label}{VECTOR}", kind.dimensions)
    if type(entry_dimensions) is not int or not 0 <= entry_dimensions <= MAX_DIMENSIONS:
        raise ValueError(f"entry_dimensions is a whole number from 0 to {MAX_DIMENSIONS}")
    if entry_dimensions:
        _vector_index(graph, f"Entry{VECTOR}", entry_dimensions)
    for label, prop in sorted(keys):
        _create(graph.create_node_unique_constraint, label, prop, deadline)
    # Indexes and constraints are built in the background. A node written while its index
    # is under construction is never added to it (FalkorDB 6.0.2): MATCH and MERGE by key
    # then miss the node for good. So do not return before everything is operational.
    while True:
        states = {
            (c["label"], tuple(c["properties"])): c["status"] for c in graph.list_constraints()
        }
        waiting = {key: states.get((key[0], (key[1],))) for key in keys}
        waiting = {key: status for key, status in waiting.items() if status != "OPERATIONAL"}
        indexes = graph.ro_query("CALL db.indexes() YIELD label, status RETURN label, status")
        waiting |= {row[0]: row[1] for row in indexes.result_set if row[1] != "OPERATIONAL"}
        if not waiting:
            return
        if "FAILED" in waiting.values() or time.monotonic() > deadline:
            raise RuntimeError(f"schema not ready: {waiting}")
        time.sleep(0.01)
