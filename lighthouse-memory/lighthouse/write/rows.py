"""Rows: what a caller gives, checked and turned into the parameters of a query, with a
fingerprint of its content. Nothing here talks to the graph."""

import hashlib
import json

from lighthouse.clock import is_ahead, stamp
from lighthouse.kinds import ENGINE_PROPERTIES, Kind
from lighthouse.values import (
    MAX_DETAIL,
    MAX_SIZE,
    describe,
    indexed,
    is_key,
    is_name,
    mapping,
    properties,
    references,
)


def checked(kind: Kind, row) -> dict:
    """A caller's row as query parameters. Raises ValueError or TypeError when it cannot
    be stored."""
    if not isinstance(row, dict):
        raise TypeError(f"a row must be a map, got {type(row).__name__}")
    unknown = set(row) - {"key", "t", "values", "relations", "entry"}
    if unknown:
        raise ValueError(f"unknown row fields: {describe(sorted(map(str, unknown)))}")
    if not is_key(row.get("key")):
        raise ValueError(f"key must be a name or an integer, got {describe(row.get('key'))}")
    t = stamp(row.get("t"))
    if t is None:
        raise ValueError("t (the time the row became true) is missing")
    if is_ahead(t):
        raise ValueError(f"t is in the future: {t}")
    if row.get("entry") is not None and not is_name(row["entry"]):
        raise ValueError(f"entry must be the id of an entry, got {describe(row['entry'])}")

    # Null means absent, so nulls are dropped. Declared times go their own way.
    values = dict(mapping(row.get("values"), "values"))
    times = {name: stamp(values.pop(name, None)) for name in kind.times}
    times = {name: value for name, value in times.items() if value is not None}
    values = properties(values, ENGINE_PROPERTIES | {kind.key}, "values")

    given = mapping(row.get("relations"), "relations")
    if set(given) - set(kind.relations):
        raise ValueError(f"relations must have types from {sorted(kind.relations)}")
    relations = {name: references(given.get(name), f"relations.{name}") for name in kind.relations}

    content = json.dumps([values, times, relations], sort_keys=True)
    if len(content) > MAX_SIZE:
        raise ValueError(f"the row is larger than {MAX_SIZE} characters")
    # The words of the text go on the entity and on its State, for search.
    words = indexed(values.get(name) for name in kind.text)
    return {
        "key": row["key"],
        "t": t,
        "entity": {kind.key: row["key"], **values, **words},
        "values": values | words,
        "times": times,
        "relations": relations,
        "entry": row.get("entry"),  # not in the fingerprint: it says where, not what
        # Equal fingerprint means the values and relations are the same.
        "fp": hashlib.sha256(content.encode()).hexdigest(),
        "refused": content[:MAX_DETAIL],  # what a WriteFailure keeps if the row is refused
    }
