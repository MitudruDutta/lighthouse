"""Bounded, read-only views of the world graph for investigations and operations."""

import lighthouse
from falkordb import Graph

from app.portcalls import BY_LABEL, PORT_CALL, key_for

KEYS = {label: kind.key for label, kind in BY_LABEL.items()} | {
    "Episode": "id",
    "Entry": "id",
    "Lesson": "id",
    "Playbook": "id",
}
NODES = 25
EDGES = 48
TIMEOUT = 2_000


def _node(node) -> dict:
    label = next((label for label in node.labels if label in KEYS), None)
    values = node.properties
    key = values[KEYS[label]]
    title = values.get("name") or values.get("statement") or values.get("type") or str(key)
    return {
        "id": node.id,
        "ref": [label, key],
        "title": str(title)[:180],
        "by": values.get("by"),
        "at": values.get("recorded_at") or values.get("opened_at"),
        "description": str(values.get("text") or values.get("statement") or "")[:800],
        "state": "closed" if values.get("closed_at") else "open" if label == "Episode" else None,
    }


def network(graph: Graph, kind: str = "Episode", key: str | None = None) -> dict:
    if kind not in KEYS:
        raise ValueError("unknown graph kind")
    if key is None:
        query = (
            "MATCH (n:Episode) RETURN n ORDER BY n.closed_at IS NULL DESC, n.opened_at DESC LIMIT 1"
        )
        rows = graph.ro_query(query, timeout=TIMEOUT).result_set
        if not rows:
            rows = graph.ro_query(
                "MATCH (n:PortCall) RETURN n ORDER BY n.id LIMIT 1", timeout=TIMEOUT
            ).result_set
    else:
        parsed = key_for(BY_LABEL[kind], key) if kind in BY_LABEL else key
        rows = graph.ro_query(
            f"MATCH (n:{kind} {{{KEYS[kind]}: $key}}) RETURN n", {"key": parsed}, timeout=TIMEOUT
        ).result_set
    if not rows:
        return {"focus": None, "nodes": [], "edges": [], "limited": False}
    root = rows[0][0]
    # Exclude history-state and writer edges. Historical entity relations are closed.
    neighbours = graph.ro_query(
        "MATCH (n)-[r]-(m) WHERE id(n) = $root AND r.valid_to IS NULL "
        "AND any(label IN labels(m) WHERE label IN $labels) "
        "RETURN n, r, m ORDER BY type(r), id(m), id(r) LIMIT $limit",
        {"root": root.id, "labels": list(KEYS), "limit": EDGES + 1},
        timeout=TIMEOUT,
    ).result_set
    nodes, edges = {root.id: _node(root)}, []
    limited = len(neighbours) > EDGES
    for n, edge, m in neighbours[:EDGES]:
        if m.id not in nodes and len(nodes) >= NODES:
            limited = True
            continue
        nodes[m.id] = _node(m)
        edges.append(
            {
                "id": edge.id,
                "source": edge.src_node,
                "target": edge.dest_node,
                "type": edge.relation,
                "since": edge.properties.get("valid_from"),
            }
        )
    return {"focus": root.id, "nodes": list(nodes.values()), "edges": edges, "limited": limited}


def overview(graph: Graph) -> dict:
    tasks = dict(
        graph.ro_query("MATCH (t:Task) RETURN t.status, count(t)", timeout=TIMEOUT).result_set
    )
    handoffs = graph.ro_query(
        "MATCH (h:Handoff) RETURN count(h), count(h.accepted_at)", timeout=TIMEOUT
    ).result_set[0]
    assessments = graph.ro_query(
        "MATCH (e:Entry {type: 'assessment'}) RETURN count(e), "
        "sum(CASE WHEN e.outcome = 'grounded' THEN 1 ELSE 0 END)",
        timeout=TIMEOUT,
    ).result_set[0]
    groups = lighthouse.groups(graph, [PORT_CALL], ["ABOUT"], records=["Episode"], limit=4, show=12)
    ranks = lighthouse.important(graph, [PORT_CALL], "CALLS_AT", limit=8)
    names = dict(
        graph.ro_query(
            "MATCH (p:Port) WHERE p.name IS NOT NULL RETURN p.locode, p.name", timeout=TIMEOUT
        ).result_set
    )
    return {
        "tasks": tasks,
        "handoffs": {"total": handoffs[0], "accepted": handoffs[1]},
        "assessments": {"total": assessments[0], "grounded": assessments[1] or 0},
        "groups": groups,
        "central": [
            dict(item, name=names.get(item["entity"][1], str(item["entity"][1])))
            for item in ranks
            if item["entity"][0] == "Port"
        ],
    }


def quality(graph: Graph, *, diagnostics: bool = False) -> dict:
    ports = graph.ro_query(
        "MATCH (p:Port) RETURN count(p), "
        "sum(CASE WHEN p.lat IS NOT NULL AND p.lon IS NOT NULL THEN 1 ELSE 0 END), "
        "sum(CASE WHEN p.calls IS NOT NULL THEN 1 ELSE 0 END), "
        "sum(CASE WHEN p.portwatch IS NOT NULL AND NOT p.locode STARTS WITH 'portwatch:' THEN 1 ELSE 0 END)",
        timeout=TIMEOUT,
    ).result_set[0]
    calls = graph.ro_query(
        "MATCH (p:PortCall) OPTIONAL MATCH (p)-[r:AT]->(b:Berth) WHERE r.valid_to IS NULL "
        "RETURN count(DISTINCT p), count(DISTINCT b), "
        "count(DISTINCT CASE WHEN b IS NOT NULL THEN p END), "
        "count(DISTINCT CASE WHEN p.eta IS NOT NULL THEN p END), "
        "count(DISTINCT CASE WHEN p.ata IS NOT NULL THEN p END), "
        "count(DISTINCT CASE WHEN p.areas > 1 THEN p END)",
        timeout=TIMEOUT,
    ).result_set[0]
    failures = graph.ro_query(
        "MATCH (f:WriteFailure) WHERE f.owner IS NULL "
        "RETURN f.reason, count(f), sum(coalesce(f.times, 1)) ORDER BY f.reason LIMIT 20",
        timeout=TIMEOUT,
    ).result_set if diagnostics else []
    versions = graph.ro_query("MATCH (s:State) RETURN count(s)", timeout=TIMEOUT).result_set[0][0]
    return {
        "ports": dict(zip(("total", "located", "daily_counts", "joined_by_locode"), ports)),
        "calls": dict(
            zip(
                (
                    "total",
                    "berths",
                    "with_berth",
                    "with_eta",
                    "with_actual_arrival",
                    "multiple_areas",
                ),
                calls,
            )
        ),
        "versions": versions,
        **({"refused_writes": [
            {"reason": reason, "distinct": count, "attempts": attempts}
            for reason, count, attempts in failures
        ]} if diagnostics else {}),
    }
