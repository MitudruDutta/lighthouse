"""The graph as it was at one time, and the algorithms over it.

FalkorDB's algorithms see every relation that was ever true: they cannot keep to the edges
that held at one time. So for a time, the relations that held then are read in one query
each, and the algorithms run here, on what was read:

  groups      sets that the relations joined then             union-find
  important   PageRank over the entities and relations then   power iteration
  between     paths through each entity then                  Brandes, from a sample
  connection  the shortest chain of relations then            breadth-first search

They follow the rules of the algorithms in algorithms.py, so for a time when every
relation held, they give the same answers. An entity counts from its first State, and
whatever a relation that held pointed at counts too. Answers are not kept: a row that came
late can change what held at a time without a node or an edge more.
"""

import operator
import random
from collections import deque

from falkordb import Graph

from lighthouse.clock import stamp
from lighthouse.episodes import RECORD_EDGES, RECORDS
from lighthouse.kinds import ENTITY
from lighthouse.read import READ_TIMEOUT

MOST = 1_000_000  # relations, and entities, that one answer reads at most
# between() here follows each relation once for each entity it counts paths from, in
# Python: about 1 s for this many steps.
WORK = 2_000_000
DAMPING = 0.85

_LABEL = f"[l IN labels(n) WHERE l <> '{ENTITY}'][0]"
_HELD = (
    "o.valid_from <= localdatetime($at) AND (o.valid_to IS NULL OR o.valid_to > localdatetime($at))"
)


def _time(at) -> str:
    when = stamp(at)
    if when is None:
        raise ValueError("at (the time to look at) is missing")
    return when


def _either(name: str, labels: list[str]) -> str:
    return "(" + " OR ".join(f"{name}:{label}" for label in labels) + ")"


def _read(graph: Graph, labels: list[str], types: list[str] | None, at: str):
    """The entities of the labels that existed at `at`, and the relations of the types that
    held then between them, each pair once: (ids, pairs). Without types, every relation.
    """
    if set(types or ()) & set(RECORD_EDGES):
        raise ValueError("records have no time: at a time, only relations of entities count")
    edge = f"[o:{'|'.join(types)}]" if types else "[o]"
    query = f"""
MATCH (a)-{edge}->(b) WHERE {_either("a", labels)} AND {_either("b", labels)} AND {_HELD}
WITH DISTINCT id(a) AS a, id(b) AS b LIMIT $most RETURN collect(a), collect(b)
"""
    params = {"at": _time(at), "most": MOST + 1}
    # Two flat lists: the client reads them in half the time of a list of pairs.
    sources, targets = graph.ro_query(query, params, timeout=READ_TIMEOUT).result_set[0]
    pairs = list(zip(sources, targets, strict=True))
    ids = set()
    for label in labels:
        found = graph.ro_query(
            f"MATCH (e:{label})-[:HAS_STATE]->(s:State) WHERE s.valid_from <= localdatetime($at) "
            "WITH DISTINCT id(e) AS e LIMIT $most RETURN collect(e)",
            params,
            timeout=READ_TIMEOUT,
        ).result_set[0][0]
        ids.update(found)
    ids.update(sources)
    ids.update(targets)
    if len(pairs) > MOST or len(ids) > MOST:
        raise ValueError(f"more than {MOST} relations or entities at that time: name fewer")
    return sorted(ids), pairs


def _names(graph: Graph, ids: list[int], key_of: dict) -> dict[int, tuple]:
    """(label, key) of nodes by id. The key is None for a label that has none here."""
    rows = graph.ro_query(
        f"UNWIND $ids AS i MATCH (n) WHERE id(n) = i WITH i, n "
        f"RETURN i, {_LABEL}, CASE WHEN $key_of[{_LABEL}] IS NULL THEN NULL "
        f"ELSE n[$key_of[{_LABEL}]] END",
        {"ids": ids, "key_of": key_of},
    ).result_set
    return {i: (label, key) for i, label, key in rows}


def joined(ids: list, pairs) -> list[list]:
    """The sets that the pairs join, whichever way they point, each in the order of `ids`,
    largest first, then by their first member. By union-find."""
    parent = {node: node for node in ids}

    def root(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for a, b in pairs:
        parent[root(a)] = root(b)
    sets: dict = {}
    for node in ids:  # in the order of ids: the oldest first
        sets.setdefault(root(node), []).append(node)
    return sorted(sets.values(), key=lambda members: (-len(members), members[0]))


def groups(graph, key_of, types, at, at_least, limit, show) -> list[dict]:
    ids, pairs = _read(graph, sorted(key_of), types, at)
    chosen = [members for members in joined(ids, pairs) if len(members) >= at_least][:limit]
    names = _names(graph, sorted({n for members in chosen for n in members[:show]}), key_of)
    return [
        {"size": len(members), "members": [names[n] for n in members[:show]]} for members in chosen
    ]


def _best(graph, score: dict, key_of: dict, limit: int, scale: float = 1.0) -> list[dict]:
    """The entities of the listed labels with the highest scores, oldest first of equals."""
    order = sorted(score, key=lambda node: (-score[node], node))
    found, start = [], 0
    while len(found) < limit and start < len(order):
        part = order[start : start + 4 * limit]
        names = _names(graph, part, key_of)
        found += [(node, names[node]) for node in part if names[node][0] in key_of]
        start += len(part)
    return [{"entity": name, "score": score[node] * scale} for node, name in found[:limit]]


def ranked(ids: list, pairs) -> list[float]:
    """PageRank of each of `ids`, in their order, by the rules of FalkorDB's: damping 0.85,
    and a node that points at nothing shares its rank among all."""
    if not ids:
        return []
    n, out = len(ids), _out(ids, pairs)
    alone = [i for i in range(n) if not out[i]]  # what points at nothing shares among all
    into: list[list[int]] = [[] for _ in range(n)]
    for i, targets in enumerate(out):
        for target in targets:
            into[target].append(i)
    width = [len(targets) or 1 for targets in out]
    rank = [1 / n] * n
    for _ in range(200):
        # Each node takes from what points at it: sum() over map() runs without a Python loop.
        part = [r / w for r, w in zip(rank, width, strict=True)]
        base = (1 - DAMPING + DAMPING * sum(rank[i] for i in alone)) / n
        step = [base + DAMPING * sum(map(part.__getitem__, sources)) for sources in into]
        change = sum(map(abs, map(operator.sub, step, rank)))
        rank = step
        if change < 1e-12:
            break
    return rank


def important(graph, key_of, relation, at, limit) -> list[dict]:
    # The rank is taken over every entity, as FalkorDB takes it, and listed for the kinds.
    ids, pairs = _read(graph, [ENTITY], relation and [relation], at)
    if not ids:
        return []
    return _best(graph, dict(zip(ids, ranked(ids, pairs), strict=True)), key_of, limit)


def between(graph, key_of, types, at, limit, sample, seed, least) -> list[dict]:
    ids, pairs = _read(graph, sorted(key_of), types, at)
    total, out = len(ids), _out(ids, pairs)
    sources = min(sample or max(least, WORK // max(len(pairs), 1)), max(total, 1))
    starts = range(total) if sources >= total else random.Random(seed).sample(range(total), sources)
    score = [0.0] * total
    for source in starts:  # Brandes: the paths from one source, then back along them
        far, ways, part = [-1] * total, [0] * total, [0.0] * total
        before: dict[int, list] = {source: []}
        far[source], ways[source], order, todo = 0, 1, [], deque([source])
        while todo:
            node = todo.popleft()
            order.append(node)
            for target in out[node]:
                if far[target] < 0:
                    far[target], before[target] = far[node] + 1, []
                    todo.append(target)
                if far[target] == far[node] + 1:
                    ways[target] += ways[node]
                    before[target].append(node)
        for node in reversed(order):
            for earlier in before[node]:
                part[earlier] += ways[earlier] / ways[node] * (1 + part[node])
            if node != source:
                score[node] += part[node]
    scale = total / sources if total else 1.0
    return _best(graph, dict(zip(ids, score, strict=True)), key_of, limit, scale)


def _out(ids: list[int], pairs: list) -> list[list[int]]:
    """What each node points at, by the place of the nodes in `ids`, in the order of ids. A
    relation to itself is kept: no shortest path runs through it."""
    place = {node: i for i, node in enumerate(ids)}
    out: list[list[int]] = [[] for _ in ids]
    for a, b in sorted(pairs):
        out[place[a]].append(place[b])
    return out


def _path(graph: Graph, a: int, b: int, edge: str, hops: int, at: str) -> list[int] | None:
    """The nodes of a shortest chain from `a` to `b` by relations that held at `at`, in
    either direction, or None. The search goes out from both ends, a step at a time from the
    end that has fewer to look at, and reads the neighbours of those only."""
    seen = [{a: None}, {b: None}]  # each node, and the node it was reached from
    ends, depth = [[a], [b]], [0, 0]
    while depth[0] + depth[1] < hops and ends[0] and ends[1]:
        side = 0 if len(ends[0]) <= len(ends[1]) else 1
        near = dict(
            graph.ro_query(
                f"UNWIND $ids AS i MATCH (x) WHERE id(x) = i WITH i, x "
                f"MATCH (x)-{edge}-(y) WHERE {_HELD} RETURN i, collect(DISTINCT id(y))",
                {"ids": ends[side], "at": at},
                timeout=READ_TIMEOUT,
            ).result_set
        )
        met, step = [], []
        for node in ends[side]:
            for other in sorted(near.get(node, ())):
                if other in seen[1 - side]:
                    met.append((node, other))
                if other not in seen[side]:
                    seen[side][other] = node
                    step.append(other)
        depth[side] += 1
        if met:
            # Every node met is at the far end of the other search: each chain is as short,
            # and the first by id is taken.
            node, other = min(met)
            here, there = (node, other) if side == 0 else (other, node)
            return _back(seen[0], here)[::-1] + _back(seen[1], there)
        if len(seen[0]) + len(seen[1]) > MOST:
            raise ValueError(f"more than {MOST} entities on the way: allow fewer steps")
        ends[side] = step
    return None


def _back(seen: dict, node: int) -> list[int]:
    """The way back from a node to where its search began."""
    way = [node]
    while seen[way[-1]] is not None:
        way.append(seen[way[-1]])
    return way


def connection(graph, start, end, types, hops, at, key_of) -> list[dict] | None:
    """The steps of the shortest chain from `start` to `end`, each (label, key property,
    key) of an entity, then."""
    if start[0] in RECORDS or end[0] in RECORDS:
        raise ValueError("records have no time: at a time, only entities are connected")
    a, b = graph.ro_query(
        f"OPTIONAL MATCH (a:{start[0]} {{{start[1]}: $start}}) "
        f"OPTIONAL MATCH (b:{end[0]} {{{end[1]}: $end}}) RETURN id(a), id(b)",
        {"start": start[2], "end": end[2]},
    ).result_set[0]
    if a is None or b is None:
        return None
    if set(types) & set(RECORD_EDGES):
        raise ValueError("records have no time: at a time, only relations of entities count")
    edge = f"[o:{'|'.join(types)}]"
    path = _path(graph, a, b, edge, hops, _time(at))
    if path is None:
        return None
    rows = graph.ro_query(
        "UNWIND range(0, size($path) - 2) AS i MATCH (x) WHERE id(x) = $path[i] WITH i, x "
        "MATCH (y) WHERE id(y) = $path[i + 1] WITH i, x, y "
        f"MATCH (x)-{edge}-(y) WHERE {_HELD} "
        "RETURN i, type(o), startNode(o) = x, o.valid_from, o.valid_to",
        {"path": path, "at": _time(at)},
        timeout=READ_TIMEOUT,
    ).result_set
    # Of the relations that held between two things then, the first by name, and the one
    # that points along the walk.
    chosen: dict[int, tuple] = {}
    for i, relation, forward, since, until in rows:
        if i not in chosen or (relation, not forward) < (chosen[i][0], not chosen[i][1]):
            chosen[i] = (relation, forward, since, until)
    names = _names(graph, path, key_of)
    return [
        {
            "from": names[path[i]],
            "relation": relation,
            "to": names[path[i + 1]],
            "forward": forward,
            "current": until is None,
            "since": since,
            "until": until,
        }
        for i, (relation, forward, since, until) in sorted(chosen.items())
    ]
