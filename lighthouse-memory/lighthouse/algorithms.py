"""Algorithms over the graph: what belongs together, what is central, and how two things
are connected.

  groups      sets of things that are linked, directly or through other things
  important   entities that much points at, most of all when that is important itself
  between     entities that lie on the shortest paths between other entities
  connection  the shortest chain of relations from one thing to another

FalkorDB computes all four. A relation edge is never deleted, and these searches cannot
tell an open edge from a closed one: they see every relation that was ever true.
connection() says for each step whether it still holds. With `at`, each of them sees the
relations that held at that time, and nothing else: see snapshot.py.

FalkorDB cannot stop groups, important, or between while they run. The first two take time
in proportion to the size of the graph. between takes that time once for each entity it
counts paths from, so it counts from as many as a fixed amount of work allows.

An answer of those three is kept, and given again while the graph has not grown where the
call reads it. A graph only grows, so the numbers of its nodes and edges tell whether it
did, and FalkorDB has those numbers at hand. The stamp of the graph tells whether it is
still the same graph: a graph without a stamp gets a new answer every time, and each query
of the library that deletes gives the graph a new stamp: the forgetting of a session, and a
row that came late and takes the place of the NEXT link between two States.
"""

import weakref

from falkordb import Graph

from lighthouse import snapshot
from lighthouse.episodes import RECORD_EDGES, RECORDS, evidence
from lighthouse.kinds import ENTITY, STAMP, Kind, all_kinds
from lighthouse.read import READ_TIMEOUT
from lighthouse.values import MAX_REFERENCES, describe, whole_number

MAX_HOPS = 10
# between() follows every relation once for each entity it counts paths from: 5 ms for one
# entity and 550,000 relations. WORK is the number of relations it may follow for one answer,
# about 0.1 s. It counts from at least SAMPLE entities, whatever that costs.
WORK = 10_000_000
SAMPLE = 32
MAX_SAMPLE = 1_000

# Answers that were computed, by client and then by graph and call: (stamp and numbers of
# the whole graph, numbers of what the call reads, answer).
_ANSWERS = weakref.WeakKeyDictionary()
MAX_ANSWERS = 64  # kept for one client
MAX_KEPT = 10_000  # (label, key) pairs in an answer that is kept

_NODES = "MATCH (n{0}) RETURN count(n)"
_EDGES = "MATCH ()-[e{0}]->() RETURN count(e)"

# The order of the labels of a node is not fixed. The label of its kind is the other one.
_LABEL = f"[l IN labels({{0}}) WHERE l <> '{ENTITY}'][0]"
# The best are picked before they are named: to name every node costs more than the search.
_TOP = f"""WITH node, score ORDER BY score DESC, id(node) LIMIT $limit
RETURN {_LABEL.format("node")}, node[$key_of[{_LABEL.format("node")}]], score, id(node)"""


def _kinds(kinds) -> dict[str, Kind]:
    """The given kinds and every kind they point at, by label."""
    if not isinstance(kinds, (list, tuple)) or not all(isinstance(kind, Kind) for kind in kinds):
        raise TypeError("kinds must be a list of Kind")
    return all_kinds(kinds)


def _key_of(kinds: dict[str, Kind], records=()) -> dict[str, str]:
    """The property that identifies a node, by label. Never empty: with no label to keep
    to, FalkorDB takes every node of the graph."""
    if not isinstance(records, (list, tuple)):
        raise TypeError("records must be a list of labels")
    for label in records:
        if not isinstance(label, str) or label not in RECORDS:
            raise ValueError(f"not a record: {describe(label)}. Records are {sorted(RECORDS)}")
    key_of = {label: kind.key for label, kind in kinds.items()}
    key_of |= {label: RECORDS[label] for label in records}
    if not key_of:
        raise ValueError("name at least one kind")
    return key_of


def _relations(kinds: dict[str, Kind], relations, records: bool = False) -> list[str]:
    """The edge types to follow, checked. Never empty: with no type to keep to, FalkorDB
    follows every edge of the graph."""
    declared = {name for kind in kinds.values() for name in kind.relations}
    if relations is None:
        chosen = declared | set(RECORD_EDGES) if records else declared
    elif isinstance(relations, (list, tuple)) and len(relations) <= MAX_REFERENCES:
        known = declared | set(RECORD_EDGES)
        for name in relations:
            if not isinstance(name, str) or name not in known:
                raise ValueError(f"not a relation of these kinds: {describe(name)}")
        chosen = set(relations)
    else:
        raise ValueError("relations must be a list of relations of these kinds")
    if not chosen:
        raise ValueError("there is no relation to follow")
    return sorted(chosen)


def _count(graph: Graph, query: str, name: str = "") -> int:
    """Nodes of one label or edges of one type; of all of them without a name. Each count
    is a query of its own: FalkorDB answers it without a scan only when it stands alone."""
    return graph.ro_query(query.format(f":{name}" if name else "")).result_set[0][0]


def _answer(graph: Graph, call: tuple, labels: list, types, compute) -> list[dict]:
    """The answer to a call: the one that was kept, or a new one from compute() when the
    graph has grown where the call reads it. `types` is None for a call that reads every
    edge. compute() gets the numbers of the nodes and of the edges that the call reads."""
    kept = _ANSWERS.setdefault(graph.client, {})
    key = (graph.name, *call)
    stamp = graph.ro_query(f"MATCH (s:{STAMP}) RETURN s.id").result_set
    whole = (stamp and stamp[0][0], _count(graph, _NODES), _count(graph, _EDGES))
    found = kept.pop(key, None)
    if found is None or found[0] != whole:
        nodes = tuple(_count(graph, _NODES, label) for label in labels)
        edges = whole[2:] if types is None else tuple(_count(graph, _EDGES, t) for t in types)
        # The numbers are read before the answer is computed. So an answer is never older
        # than the numbers it is kept with.
        if found is None or found[0][0] != whole[0] or found[1] != (nodes, edges):
            found = (whole, (nodes, edges), compute(nodes, edges))
        found = (whole, *found[1:])
    if stamp and sum(len(item.get("members", ())) + 1 for item in found[2]) <= MAX_KEPT:
        if len(kept) >= MAX_ANSWERS:
            kept.pop(next(iter(kept), None), None)  # the one that was used longest ago
        kept[key] = found
    # A caller may change what it gets, so it gets lists and maps of its own.
    return [
        {name: list(value) if isinstance(value, list) else value for name, value in item.items()}
        for item in found[2]
    ]


def _scores(rows: list, scale: float = 1.0) -> list[dict]:
    rows.sort(key=lambda row: (-row[2], row[3]))
    return [{"entity": (label, key), "score": score * scale} for label, key, score, _ in rows]


def groups(
    graph: Graph,
    kinds,
    relations=None,
    records=(),
    at_least: int = 2,
    limit=100,
    show=100,
    at=None,
) -> list[dict]:
    """Sets of things that are linked, directly or through other things, largest first:
    [{"size", "members"}]. Two things are in one set when a chain of relations joins them,
    whichever way the relations point.

    kinds      the entities that take part: these kinds and every kind they point at
    records    labels of records that take part too: Episode, Entry, Lesson, Playbook
    relations  the edge types that link. Default: every relation of the kinds, and with
               records also what a record is about, has, cites, and rests on
    at_least   the smallest set that is listed. 1 lists what is linked to nothing as well
    "members" holds up to `show` members as (label, key) pairs, oldest first. Sets of one
    size come in the order of their oldest members.

    With records=["Episode"] and relations=["ABOUT"], a set holds the episodes that are
    about the same entities, and those entities.

    With `at`, the sets that the relations joined at that time, of the entities that existed
    then. Records have no time: they cannot take part.
    """
    known = _kinds(kinds)
    key_of = _key_of(known, records)
    labels, types = sorted(key_of), _relations(known, relations, bool(records))
    label = _LABEL.format("n")
    # The largest sets are picked before their members are named.
    query = f"""
CALL algo.WCC($config) YIELD node, componentId
WITH componentId, node ORDER BY id(node)
WITH componentId, collect(node) AS members WHERE size(members) >= $at_least
WITH members ORDER BY size(members) DESC, id(members[0]) LIMIT $limit
RETURN size(members), id(members[0]), [n IN members[..$show] | [{label}, n[$key_of[{label}]]]]
"""
    params = {
        "config": {"nodeLabels": labels, "relationshipTypes": types},
        "key_of": key_of,
        "at_least": whole_number(at_least, "at_least", 1_000_000),
        "show": whole_number(show, "show", 1_000),
        "limit": whole_number(limit, "limit", 1_000),
    }
    if at is not None:
        if records:
            raise ValueError("at a time, only entities take part, not records")
        args = (params["at_least"], params["limit"], params["show"])
        return snapshot.groups(graph, key_of, types, at, *args)

    def compute(_nodes, _edges):
        rows = graph.ro_query(query, params, timeout=READ_TIMEOUT).result_set
        rows.sort(key=lambda row: (-row[0], row[1]))
        return [
            {"size": size, "members": [tuple(pair) for pair in shown]} for size, _, shown in rows
        ]

    call = ("groups", *sorted(key_of.items()), *types, at_least, limit, show)
    return _answer(graph, call, labels, types, compute)


def important(graph: Graph, kinds, relation=None, limit: int = 10, at=None) -> list[dict]:
    """Entities by PageRank, highest first: [{"entity": (label, key), "score"}]. Of equal
    scores, the oldest entity comes first.

    An entity scores high when many entities point at it, and higher when those score high
    themselves. An entity shares its score evenly among what it points at; one that points
    at nothing shares it among all.

    The rank is taken over the entities of every kind and the edges of `relation` (default:
    every relation), so the scores of all entities add up to 1. Entities of `kinds`, and of
    the kinds they point at, are listed. With `at`, over the entities that existed and the
    relations that held at that time.
    """
    known = _kinds(kinds)
    key_of = _key_of(known)
    if relation is not None:
        [relation] = _relations(known, [relation])
    # FalkorDB fails when no node has the label yet, so the search starts from one that has.
    query = f"""
MATCH (e:{ENTITY}) WITH e LIMIT 1
CALL algo.pageRank('{ENTITY}', $relation) YIELD node, score
WITH node, score WHERE {" OR ".join(f"node:{label}" for label in sorted(key_of))}
{_TOP}
"""
    params = {"relation": relation, "key_of": key_of, "limit": whole_number(limit, "limit", 1_000)}
    if at is not None:
        return snapshot.important(graph, key_of, relation, at, params["limit"])

    def compute(_nodes, _edges):
        return _scores(graph.ro_query(query, params, timeout=READ_TIMEOUT).result_set)

    call = ("important", *sorted(key_of.items()), relation, limit)
    return _answer(graph, call, [ENTITY], relation and [relation], compute)


def between(
    graph: Graph,
    kinds,
    relations=None,
    limit: int = 10,
    sample: int | None = None,
    seed: int = 1,
    at=None,
) -> list[dict]:
    """Entities by the shortest paths between other entities that run through them, highest
    first: [{"entity": (label, key), "score"}]. The score is the number of such paths; where
    several shortest paths join two entities, each counts for its part. Of equal scores,
    the oldest entity comes first.

    A path follows the direction of the relations. So an entity scores only when relations
    lead into it and out of it: a relation from a kind to itself, or a chain of kinds. Where
    one kind only points at another, every score is 0.

    Paths are counted from `sample` entities picked at random, and the counts are scaled up
    to all: an estimate, and the same one for the same `seed`. It finds the entities that
    stand out; it cannot order entities whose scores are close. The count is exact when the
    sample is as large as the number of entities. Without `sample`, it is as large as WORK
    allows and at least SAMPLE, so a small graph gets the exact count.

    With `at`, over the relations that held at that time. The paths are counted here, not in
    FalkorDB: from fewer entities for the same work, picked by `seed` in another way.
    """
    known = _kinds(kinds)
    key_of = _key_of(known)
    labels, types = sorted(key_of), _relations(known, relations)
    if sample is not None:
        whole_number(sample, "sample", MAX_SAMPLE)
    whole_number(seed, "seed", 2**31 - 1)  # 0 would pick by the time
    query = f"CALL algo.betweenness($config) YIELD node, score\n{_TOP}"
    limit = whole_number(limit, "limit", 1_000)
    if at is not None:
        return snapshot.between(graph, key_of, types, at, limit, sample, seed, SAMPLE)

    def compute(nodes, edges):
        total = sum(nodes)
        sources = min(sample or max(SAMPLE, WORK // max(sum(edges), 1)), max(total, 1))
        config = {"nodeLabels": labels, "relationshipTypes": types}
        config |= {"samplingSize": sources, "samplingSeed": seed}
        params = {"config": config, "key_of": key_of, "limit": limit}
        rows = graph.ro_query(query, params, timeout=READ_TIMEOUT).result_set
        # FalkorDB gives the sum over the sample as it is. Each entity it started from
        # stands for total / sources entities.
        return _scores(rows, total / sources)

    call = ("between", *sorted(key_of.items()), *types, limit, sample, seed)
    return _answer(graph, call, labels, types, compute)


def connection(
    graph: Graph, start, end, kinds=(), relations=None, max_hops: int = 6, at=None
) -> list[dict] | None:
    """The shortest chain of relations from `start` to `end`, as its steps in order. None
    when no chain of up to `max_hops` steps joins them, or one of them is not known. The
    same thing twice is no step: [].

    start, end  references: (Kind, key) for an entity, (label, id) for a record
    kinds       more kinds whose relations may be followed. The kinds of start and end,
                and every kind they point at, are followed already: name a kind that
                points at both
    relations   the edge types to follow, in either direction. Default: every relation of
                those kinds. Name ABOUT, CITES, and the like to go through records as well

    A step is {"from", "relation", "to", "forward", "current", "since", "until"}.
      from, to  (label, key) pairs in the order of the walk. The key is None for an entity
                of a kind that was not given
      forward   False when the relation points from "to" to "from"
      current   whether the relation holds now. "since" and "until" are the start and the
                end of the last time it held; "until" is None while it holds
    Where several relations join the two things of a step, the step tells of one that holds
    now, and if none does, of the one that ended last.

    With `at`, the shortest chain of relations that held at that time, between entities.
    A step tells of a relation that held then; "current" and "until" say whether it holds
    now, and when it ended.
    """
    (start_label, start_key, [a]), (end_label, end_key, [b]) = (
        evidence([item], what)[0] for item, what in ((start, "start"), (end, "end"))
    )
    if not isinstance(kinds, (list, tuple)):
        raise TypeError("kinds must be a list of Kind")
    known = _kinds([*kinds, *(item[0] for item in (start, end) if isinstance(item[0], Kind))])
    types = _relations(known, relations)
    hops = whole_number(max_hops, "max_hops", MAX_HOPS)
    if (start_label, a) == (end_label, b):
        return []
    key_of = RECORDS | {label: kind.key for label, kind in known.items()}
    if at is not None:
        ends = (start_label, start_key, a), (end_label, end_key, b)
        return snapshot.connection(graph, *ends, types, hops, at, key_of)
    # The search takes any one of the edges between two nodes, closed or open, so which
    # one it took says nothing. Every relation between the two nodes of a step is read, one
    # row for each type and direction. The type and the direction get their names before
    # the aggregates: computed beside them, every aggregate came back as the first one.
    x, y = _LABEL.format("x"), _LABEL.format("y")
    query = f"""
MATCH (a:{start_label} {{{start_key}: $start}}), (b:{end_label} {{{end_key}: $end}})
WITH shortestPath((a)-[:{"|".join(types)}*..{hops}]-(b)) AS p WHERE p IS NOT NULL
UNWIND range(0, length(p) - 1) AS i
WITH i, nodes(p)[i] AS x, nodes(p)[i + 1] AS y
MATCH (x)-[o]-(y) WHERE type(o) IN $types
WITH i, x, y, o, type(o) AS relation, startNode(o) = x AS forward
WITH i, x, y, relation, forward, max(o.valid_from) AS since,
     max(o.valid_to) AS until, count(CASE WHEN o.valid_to IS NULL THEN 1 END) AS open
RETURN i, {x}, CASE WHEN $key_of[{x}] IS NULL THEN NULL ELSE x[$key_of[{x}]] END,
       relation, forward,
       {y}, CASE WHEN $key_of[{y}] IS NULL THEN NULL ELSE y[$key_of[{y}]] END,
       since, until, open
"""
    params = {"start": a, "end": b, "key_of": key_of, "types": types}
    rows = graph.ro_query(query, params, timeout=READ_TIMEOUT).result_set
    if not rows:
        return None
    # One row for each step: a relation that holds now, or else the one that ended last.
    # Of equals, the first by name, and the one that points along the walk.
    steps: dict[int, tuple] = {}
    for (
        i,
        from_label,
        from_key,
        relation,
        forward,
        to_label,
        to_key,
        since,
        until,
        still_open,
    ) in rows:
        ended = still_open == 0
        rank = (ended, -until.timestamp() if ended else 0, relation, not forward)
        step = {
            "from": (from_label, from_key),
            "relation": relation,
            "to": (to_label, to_key),
            "forward": forward,
            "current": not ended,
            "since": since,
            "until": until if ended else None,
        }
        if i not in steps or rank < steps[i][0]:
            steps[i] = (rank, step)
    return [step for _, (_, step) in sorted(steps.items())]
