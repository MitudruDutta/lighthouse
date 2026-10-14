"""Recall by the graph: what points at an entity, and what shares its surroundings.

Nothing here matches text or vectors. Two entities are alike when they point at the same
things: the same owner, the same room, the same customer. The answer says which things,
so the reason for a recall can be shown.
"""

from falkordb import Graph

from lighthouse.clock import stamp
from lighthouse.kinds import Kind
from lighthouse.read import READ_TIMEOUT, pages
from lighthouse.values import MAX_REFERENCES, describe, is_key


def _relation(kind: Kind, relation) -> Kind:
    if not isinstance(relation, str) or relation not in kind.relations:
        raise ValueError(f"{kind.label} has no relation {describe(relation)}")
    return kind.relations[relation]


def _key(key):
    if not is_key(key):
        raise ValueError(f"key must be a name or an integer, got {describe(key)}")
    return key


def pointing_at(graph: Graph, kind: Kind, relation: str, key, when=None) -> list:
    """Keys of the entities of `kind` whose `relation` pointed at `key` at `when` (default:
    now). The reverse of related(): related() asks where one entity points, this asks what
    points at one target."""
    target = _relation(kind, relation)
    window, params = "o.valid_to IS NULL", {"key": _key(key)}
    if when is not None:
        window = (
            "o.valid_from <= localdatetime($when) "
            "AND (o.valid_to IS NULL OR o.valid_to > localdatetime($when))"
        )
        params["when"] = stamp(when)
        if params["when"] is None:
            raise ValueError("when (the time to read) is missing")
    query = (
        f"MATCH (x:{kind.label})-[o:{relation}]->(:{target.label} {{{target.key}: $key}}) "
        f"WHERE {window} RETURN x.{kind.key} ORDER BY x.{kind.key}"
    )
    return [row[0] for row in pages(graph, query, params)]


def similar(graph: Graph, kind: Kind, key, relations=None, limit: int = 10) -> list[dict]:
    """Entities of the same kind that share relation targets with this one, most shared
    first: [{"key", "shared", "through"}]. "through" lists what is shared, as
    (relation, key of the target), so the reason can be shown.

    This entity's current relations are compared with every relation the others ever had,
    so entities of the past are found. `relations` narrows the relations that count.
    """
    names = list(kind.relations) if relations is None else relations
    if not isinstance(names, (list, tuple)) or not names or len(names) > MAX_REFERENCES:
        raise ValueError(f"relations must be a list of relations of {kind.label}")
    key_of = {name: _relation(kind, name).key for name in names}
    if type(limit) is not int or not 1 <= limit <= 1_000:
        raise ValueError("limit must be a whole number from 1 to 1000")
    query = f"""
MATCH (e:{kind.label} {{{kind.key}: $key}})-[mine]->(shared)<-[theirs]-(other:{kind.label})
WHERE type(mine) IN $relations AND type(theirs) = type(mine)
  AND mine.valid_to IS NULL AND id(other) <> id(e)
WITH DISTINCT other, type(mine) AS relation, shared
WITH other, count(shared) AS shared_count,
     collect([relation, shared[$key_of[relation]]]) AS through
RETURN other.{kind.key}, shared_count, through
ORDER BY shared_count DESC, other.{kind.key} LIMIT $limit
"""
    params = {"key": _key(key), "relations": list(key_of), "key_of": key_of, "limit": limit}
    rows = graph.ro_query(query, params, timeout=READ_TIMEOUT).result_set
    return [
        {"key": other, "shared": shared, "through": sorted(map(tuple, through), key=str)}
        for other, shared, through in rows
    ]
