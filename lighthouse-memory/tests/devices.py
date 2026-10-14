"""A domain for the tests that belongs to no product: devices, rooms, teams, and people."""

from datetime import UTC, datetime, timedelta

from lighthouse import SELF, Kind, remember

ROOM = Kind("Room", key="code")
TEAM = Kind("Team", key="name")
DEVICE = Kind(
    "Device",
    key="serial",
    times=("last_seen",),
    relations={"LOCATED_IN": ROOM, "USED_BY": TEAM},
)
PERSON = Kind("Person", key="email", relations={"KNOWS": SELF})
MANUAL = Kind("Manual", key="code", text=("title", "body"), dimensions=8)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
ENGINE = {"fp", "valid_from", "valid_to", "recorded_at", "by", "seen_last", "entry"}


def count(graph, pattern: str, what: str = "*") -> int:
    """Rows that match. To count edges, name the edge and pass it as `what`: FalkorDB
    matches parallel edges of one type between two nodes once when the edge has no name."""
    return graph.ro_query(f"MATCH {pattern} RETURN count({what})").result_set[0][0]


def when(minute: int) -> datetime:
    return T0 + timedelta(minutes=minute)


def row(minute=0, key="d1", room="r1", teams=("red",), **values) -> dict:
    """The full picture of one device at `minute` after T0."""
    return {
        "key": key,
        "t": when(minute),
        "values": {"status": "ok", **values},
        "relations": {"LOCATED_IN": room, "USED_BY": list(teams)},
    }


def write(graph, *rows, kind=DEVICE) -> list[str]:
    return [receipt["status"] for receipt in remember(graph, kind, list(rows), by="test")]


def shape(graph) -> tuple[dict, dict]:
    kind = "[l IN labels(n) WHERE l <> 'Entity'][0]"  # every entity also has the label Entity
    nodes = graph.ro_query(f"MATCH (n) WHERE NOT n:Stamp RETURN {kind}, count(n)").result_set
    edges = graph.ro_query("MATCH ()-[e]->() RETURN type(e), count(e)").result_set
    return dict(nodes), dict(edges)


def windows(graph, relation: str, key="d1") -> list[tuple]:
    """Every edge of one relation from a device: (target, valid_from, valid_to), by time."""
    rows = graph.ro_query(
        f"MATCH (:Device {{serial: $key}})-[o:{relation}]->(x) "
        "RETURN coalesce(x.code, x.name), o.valid_from, o.valid_to "
        "ORDER BY o.valid_from, coalesce(x.code, x.name)",
        {"key": key},
    ).result_set
    return [tuple(r) for r in rows]


def failures(graph) -> list[list]:
    query = "MATCH (f:WriteFailure) RETURN f.reason, f.kind, f.key, f.detail ORDER BY f.reason"
    return graph.ro_query(query).result_set


def check_invariants(graph):
    """What must hold for every history, whatever was written."""
    open_states = graph.ro_query(
        "MATCH (e)-[:HAS_STATE]->(:State) WITH DISTINCT e "
        "OPTIONAL MATCH (e)-[:HAS_STATE]->(s:State) WHERE s.valid_to IS NULL "
        "RETURN id(e), count(s)"
    ).result_set
    assert [r for r in open_states if r[1] != 1] == [], "one open State per entity"
    states, entities = count(graph, "(s:State)"), len(open_states)
    assert count(graph, "()-[h:HAS_STATE]->(:State)", "h") == states
    assert count(graph, "(:State)-[n:NEXT]->(:State)", "n") == states - entities
    # A closed State ends exactly where the next one starts.
    assert count(graph, "(a:State)-[:NEXT]->(b:State) WHERE a.valid_to <> b.valid_from") == 0
    assert count(graph, "(a:State)-[:NEXT]->(:State) WHERE a.valid_to IS NULL") == 0
    assert count(graph, "(a:State) WHERE a.valid_to IS NOT NULL AND NOT (a)-[:NEXT]->()") == 0
    assert count(graph, "(a:State) WHERE a.valid_to <= a.valid_from") == 0
    crossing = "(p)-[:HAS_STATE]->(:State)-[:NEXT]->(:State)<-[:HAS_STATE]-(q)"
    assert count(graph, f"{crossing} WHERE id(p) <> id(q)") == 0
    # The entity node shows exactly the values of its open State.
    pairs = graph.ro_query(
        "MATCH (e)-[:HAS_STATE]->(s:State) WHERE s.valid_to IS NULL RETURN e, s"
    ).result_set
    for entity, state in pairs:
        current = {k: v for k, v in state.properties.items() if k not in ENGINE}
        shown = dict(entity.properties)
        assert len(shown) == len(current) + 1, (shown, current)  # plus the key
        assert current.items() <= shown.items()
    # Relation edges: a positive window, and never two open edges for the same pair.
    relation = "(a)-[o]->(b) WHERE NOT type(o) IN ['HAS_STATE', 'NEXT']"
    assert count(graph, f"{relation} AND o.valid_from IS NULL") == 0
    assert count(graph, f"{relation} AND o.valid_to <= o.valid_from") == 0
    doubles = graph.ro_query(
        f"MATCH {relation} AND o.valid_to IS NULL "
        "WITH a, b, type(o) AS kind, count(o) AS n WHERE n > 1 RETURN count(*)"
    ).result_set[0][0]
    assert doubles == 0, "one open edge per relation and pair"
