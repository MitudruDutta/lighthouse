"""Partial updates: a change to some values or relations of one entity, from a time on. The
rest is what the current State says.

update() reads the current State, makes the full row, and writes it by the write rule. The
row carries the State it was made from. If another writer has added a State since, the row
is not written and update() reads again: a change is never written over one it did not see.
"""

from falkordb import Graph

from lighthouse.clock import stamp
from lighthouse.kinds import ENGINE_PROPERTIES, Kind
from lighthouse.values import WORDS, describe, is_key, mapping, named
from lighthouse.write.batches import send
from lighthouse.write.failures import record_failure
from lighthouse.write.rows import checked

ATTEMPTS = 5  # reads and writes of one update while other writers change the entity


def _current(graph: Graph, kind: Kind, key) -> tuple[dict, dict, dict]:
    """The current State of an entity, as (values, relations, base). For an entity that
    does not exist: no values, no relations, and a base that says so."""
    rows = graph.ro_query(
        f"MATCH (e:{kind.label} {{{kind.key}: $key}})-[:HAS_STATE]->(s:State) "
        "WHERE s.valid_to IS NULL "
        "OPTIONAL MATCH (e)-[o]->(x) WHERE o.valid_to IS NULL AND type(o) IN $types "
        "RETURN s, collect([type(o), x])",
        {"key": key, "types": list(kind.relations)},
    ).result_set
    if not rows:
        return {}, {}, {"from": None}
    state, edges = rows[0]
    values = {
        name: value
        for name, value in state.properties.items()
        if name not in ENGINE_PROPERTIES | {WORDS}
    }
    relations = {name: [] for name in kind.relations}
    for name, target in edges:
        if name is not None:
            relations[name].append(target.properties[kind.relations[name].key])
    base = {"from": stamp(state.properties["valid_from"])}
    return values, relations, base


def update(
    graph: Graph, kind: Kind, key, t, by: str, values=None, relations=None, entry=None
) -> dict:
    """Change the values and relations it names, from time `t` on. A value of None removes
    it. A relation that it names gets the targets it gives, and keeps none other. The rest
    stays as the current State says. An entity that does not exist starts with what the
    update names.

    Returns a receipt as remember() does. Besides, it can say
      stale  `t` is before the current State: an update changes what is current. Send the
             full row of that time to remember() instead.
      busy   other writers changed the entity each time it was read: refused
    """
    named(by=by)
    try:
        if not is_key(key):
            raise ValueError(f"key must be a name or an integer, got {describe(key)}")
        changes = dict(mapping(values, "values"))
        targets = dict(mapping(relations, "relations"))
        time = stamp(t)
        if time is None:
            raise ValueError("t (the time the change became true) is missing")
    except (TypeError, ValueError) as exc:
        record_failure(graph, "invalid", kind.label, key if is_key(key) else None, str(exc))
        return {"key": key if is_key(key) else None, "status": "invalid", "reason": str(exc)}

    for _ in range(ATTEMPTS):
        current, held, base = _current(graph, kind, key)
        if base["from"] is not None and time < base["from"]:
            reason = f"t is before the current State, which began at {base['from']}"
            record_failure(graph, "stale", kind.label, key, f"{reason}: {describe(changes)}")
            return {"key": key, "status": "stale", "reason": reason}
        row = {
            "key": key,
            "t": time,
            "values": current | changes,
            "relations": held | targets,
            "entry": entry,
        }
        try:
            ready = checked(kind, row) | {"base": base}
        except (TypeError, ValueError) as exc:
            record_failure(graph, "invalid", kind.label, key, str(exc))
            return {"key": key, "status": "invalid", "reason": str(exc)}
        (receipt,) = send(graph, kind, [(0, ready)], by, [None])
        if receipt["status"] != "moved":
            return receipt
    reason = f"the entity changed each of {ATTEMPTS} times it was read"
    record_failure(graph, "busy", kind.label, key, f"{reason}: {describe(changes)}")
    return {"key": key, "status": "busy", "reason": reason}
