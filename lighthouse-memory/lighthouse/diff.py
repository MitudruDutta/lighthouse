"""Temporal world diffing and zero-copy counterfactual simulation.

`diff_between()` computes the structural delta of entities, states, relations,
and episodes between two timestamps. `what_if()` overlays hypothetical rows on
a read-only snapshot to preview topology and ranking shifts with zero writes.
"""

from lighthouse.clock import now, stamp
from lighthouse.kinds import ENGINE_PROPERTIES, Kind
from lighthouse.playbooks import playbooks_for
from lighthouse.read import pages
from lighthouse.snapshot import joined, ranked
from lighthouse.values import is_key

# Every change of an entity adds a State, also a change of its relations alone, so the
# entities that changed between t1 and t2 are those with a State that began then: found
# through the index on when a State begins, without reading the others.
STATE_DIFF_QUERY = """
MATCH (s:State) WHERE s.valid_from > localdatetime($t1) AND s.valid_from <= localdatetime($t2)
MATCH (e:__LABEL__)-[:HAS_STATE]->(s)
WITH DISTINCT e
MATCH (e)-[:HAS_STATE]->(x:State)
WITH e, min(x.valid_from) AS born, collect(x) AS states
WITH e.__KEY__ AS k, born,
     [x IN states WHERE x.valid_from <= localdatetime($t1)
        AND (x.valid_to IS NULL OR x.valid_to > localdatetime($t1))] AS at1,
     [x IN states WHERE x.valid_from <= localdatetime($t2)
        AND (x.valid_to IS NULL OR x.valid_to > localdatetime($t2))] AS at2
WITH k, at1, at2, born > localdatetime($t1) AND born <= localdatetime($t2) AS added
WHERE added OR (size(at1) > 0 AND size(at2) > 0)
RETURN k, added, [x IN at1 | properties(x)][0], [x IN at2 | properties(x)][0]
ORDER BY k
"""

RELATION_DIFF_QUERY = """
MATCH (s:State) WHERE s.valid_from > localdatetime($t1) AND s.valid_from <= localdatetime($t2)
MATCH (a:__LABEL__)-[:HAS_STATE]->(s)
WITH DISTINCT a
MATCH (a)-[o:__REL__]->(b:__TARGET_LABEL__)
WHERE (o.valid_from > localdatetime($t1) AND o.valid_from <= localdatetime($t2)
       AND (o.valid_to IS NULL OR o.valid_to > localdatetime($t2)))
   OR (o.valid_from <= localdatetime($t1)
       AND o.valid_to IS NOT NULL
       AND o.valid_to > localdatetime($t1)
       AND o.valid_to <= localdatetime($t2))
RETURN a.__KEY__, b.__TARGET_KEY__,
       o.valid_from > localdatetime($t1) AS opened,
       o.valid_from, o.valid_to
ORDER BY a.__KEY__, b.__TARGET_KEY__, o.valid_from
"""

# The episodes about the kinds asked for that opened, or closed, between t1 and t2: each
# found through the index on its time.
EPISODE_DIFF_QUERY = """
MATCH (ep:Episode) WHERE ep.__WHEN__ > localdatetime($t1) AND ep.__WHEN__ <= localdatetime($t2)
MATCH (ep)-[:ABOUT]->(e) WHERE any(l IN labels(e) WHERE l IN $labels)
RETURN DISTINCT ep.id ORDER BY ep.id
"""

SNAPSHOT_EDGES_QUERY = """
MATCH (a:__LABEL__)-[o:__REL__]->(b:__TARGET_LABEL__)
WHERE o.valid_from <= localdatetime($at)
  AND (o.valid_to IS NULL OR o.valid_to > localdatetime($at))
RETURN DISTINCT a.__KEY__, b.__TARGET_KEY__ ORDER BY a.__KEY__, b.__TARGET_KEY__
"""

SNAPSHOT_NODES_QUERY = """
MATCH (e:__LABEL__)-[:HAS_STATE]->(s:State)
WHERE s.valid_from <= localdatetime($at)
RETURN DISTINCT e.__KEY__ ORDER BY e.__KEY__
"""


def _check_kinds(kinds) -> list[Kind]:
    if not isinstance(kinds, (list, tuple)) or not all(isinstance(k, Kind) for k in kinds):
        raise TypeError("kinds must be a list of Kind")
    if not kinds:
        raise ValueError("at least one kind is required")
    seen, unique = set(), []
    for kind in kinds:
        if kind.label not in seen:
            seen.add(kind.label)
            unique.append(kind)
    return unique


def _clean_state(props: dict | None) -> dict:
    if not props:
        return {}
    return {k: v for k, v in props.items() if k not in ENGINE_PROPERTIES}


def diff_between(graph, kinds, t1, t2) -> dict:
    """Computes the structural delta across `kinds` between `t1` and `t2`."""
    checked_kinds = _check_kinds(kinds)
    s1 = stamp(t1)
    s2 = stamp(t2)
    if s1 is None or s2 is None:
        raise ValueError("t1 and t2 must be valid times")
    if s1 > s2:
        raise ValueError("t1 must not be later than t2")

    entities_added = []
    values_changed = []
    relations_opened = []
    relations_closed = []

    for kind in checked_kinds:
        q_state = STATE_DIFF_QUERY.replace("__LABEL__", kind.label).replace("__KEY__", kind.key)
        for key, added, st1, st2 in pages(graph, q_state, {"t1": s1, "t2": s2}):
            if added:
                entities_added.append({"entity": (kind.label, key), "values": _clean_state(st2)})
            elif st1 is not None and st2 is not None:
                before = _clean_state(st1)
                after = _clean_state(st2)
                if before != after:
                    changed_keys = sorted(
                        k for k in set(before) | set(after) if before.get(k) != after.get(k)
                    )
                    values_changed.append(
                        {
                            "entity": (kind.label, key),
                            "before": before,
                            "after": after,
                            "changed_keys": changed_keys,
                        }
                    )

        for rel_name, target_kind in kind.relations.items():
            q_rel = (
                RELATION_DIFF_QUERY.replace("__LABEL__", kind.label)
                .replace("__KEY__", kind.key)
                .replace("__REL__", rel_name)
                .replace("__TARGET_LABEL__", target_kind.label)
                .replace("__TARGET_KEY__", target_kind.key)
            )
            for src_key, dst_key, opened, v_from, v_to in pages(graph, q_rel, {"t1": s1, "t2": s2}):
                item = {
                    "from": (kind.label, src_key),
                    "relation": rel_name,
                    "to": (target_kind.label, dst_key),
                }
                if opened:
                    relations_opened.append(item | {"since": v_from})
                else:
                    relations_closed.append(item | {"until": v_to})

    labels = [k.label for k in checked_kinds]
    episodes = {
        when: [
            ep_id
            for (ep_id,) in pages(
                graph,
                EPISODE_DIFF_QUERY.replace("__WHEN__", when),
                {"labels": labels, "t1": s1, "t2": s2},
            )
        ]
        for when in ("opened_at", "closed_at")
    }
    episodes_opened, episodes_closed = episodes["opened_at"], episodes["closed_at"]

    return {
        "from_time": s1,
        "to_time": s2,
        "entities_added": entities_added,
        "values_changed": values_changed,
        "relations_opened": relations_opened,
        "relations_closed": relations_closed,
        "episodes_opened": episodes_opened,
        "episodes_closed": episodes_closed,
    }


def _groups(nodes: set[tuple], edges: set[tuple]) -> list[dict]:
    """The sets of two or more that the edges join, largest first."""
    sets = joined(sorted(nodes), edges)
    return [{"size": len(m), "members": m} for m in sets if len(m) >= 2]


def _rank(nodes: set[tuple], edges: set[tuple]) -> dict[tuple, float]:
    order = sorted(nodes)
    return dict(zip(order, ranked(order, [e for e in edges if e[1] in nodes]), strict=True))


def what_if(
    graph, kinds, hypothetical_rows: list[tuple[Kind, list[dict]]], at=None, situation=None
) -> dict:
    """Simulates `hypothetical_rows` in memory without writing to the database."""
    checked_kinds = _check_kinds(kinds)
    at_str = now() if at is None else stamp(at)
    if at_str is None:
        raise ValueError("at must be a time")
    if not isinstance(hypothetical_rows, (list, tuple)):
        raise TypeError("hypothetical_rows must be a list of (Kind, rows) pairs")

    nodes: set[tuple] = set()
    rel_map: dict[tuple, set[tuple]] = {}

    for kind in checked_kinds:
        q_nodes = SNAPSHOT_NODES_QUERY.replace("__LABEL__", kind.label).replace("__KEY__", kind.key)
        for (k,) in pages(graph, q_nodes, {"at": at_str}):
            nodes.add((kind.label, k))
        for rel_name, target_kind in kind.relations.items():
            q_edges = (
                SNAPSHOT_EDGES_QUERY.replace("__LABEL__", kind.label)
                .replace("__KEY__", kind.key)
                .replace("__REL__", rel_name)
                .replace("__TARGET_LABEL__", target_kind.label)
                .replace("__TARGET_KEY__", target_kind.key)
            )
            for src_k, dst_k in pages(graph, q_edges, {"at": at_str}):
                src = (kind.label, src_k)
                dst = (target_kind.label, dst_k)
                nodes.add(src)
                nodes.add(dst)
                rel_map.setdefault((src, rel_name), set()).add(dst)

    before_edges = {(src, dst) for (src, _), targets in rel_map.items() for dst in targets}
    sim_nodes = set(nodes)
    sim_rel_map = {k: set(v) for k, v in rel_map.items()}

    for pair in hypothetical_rows:
        if (
            not isinstance(pair, (tuple, list))
            or len(pair) != 2
            or not isinstance(pair[0], Kind)
            or not isinstance(pair[1], (list, tuple))
        ):
            raise ValueError("hypothetical_rows: each item must be (Kind, rows)")
        kind, rows = pair
        for row in rows:
            if not isinstance(row, dict) or not is_key(row.get("key")):
                raise ValueError("hypothetical_rows: each row must be a map with a valid key")
            src = (kind.label, row["key"])
            sim_nodes.add(src)
            given_rels = row.get("relations") or {}
            if not isinstance(given_rels, dict):
                raise TypeError("hypothetical_rows: the relations of a row must be a map")
            for rel_name, target_kind in kind.relations.items():
                sim_rel_map[(src, rel_name)] = set()
                raw_targets = given_rels.get(rel_name)
                if raw_targets is None:
                    continue
                target_list = (
                    raw_targets if isinstance(raw_targets, (list, tuple, set)) else [raw_targets]
                )
                for tk in target_list:
                    if not is_key(tk):
                        raise ValueError(f"hypothetical_rows: a target of {rel_name} is not a key")
                    dst = (target_kind.label, tk)
                    sim_nodes.add(dst)
                    sim_rel_map[(src, rel_name)].add(dst)

    after_edges = {(src, dst) for (src, _), targets in sim_rel_map.items() for dst in targets}
    pr_before = _rank(nodes, before_edges)
    pr_after = _rank(sim_nodes, after_edges)
    shifts = sorted(
        [
            {
                "entity": ent,
                "before": pr_before.get(ent, 0.0),
                "after": pr_after.get(ent, 0.0),
                "delta": pr_after.get(ent, 0.0) - pr_before.get(ent, 0.0),
            }
            for ent in sim_nodes | nodes
        ],
        key=lambda item: (-abs(item["delta"]), item["entity"]),
    )

    matching_playbooks = playbooks_for(graph, situation) if situation is not None else []

    return {
        "at": at_str,
        "groups_before": _groups(nodes, before_edges),
        "groups_after": _groups(sim_nodes, after_edges),
        "rank_shifts": shifts[:10],
        "playbooks": matching_playbooks,
    }
