"""The free-text path: what agents wrote in entries becomes rows, off the write path.

The library holds no model. The application passes a function, the extractor, that reads
one entry and gives the rows it finds in it. extract() runs it over entries that it has not
read yet for a kind, and writes the rows by the write rule, each with the entry as the
evidence of what it adds:

  (State)-[:FROM]->(Entry)-[:READ_BY {kind, at, rows}]->(Agent)

An entry is read once for each kind. What the extractor gives is input like any other: the
write rule checks each row, and a row that is refused leaves a WriteFailure.

Messages of conversations are not read: they can be erased, and facts drawn from them would
stay. An application that wants them read writes what it takes from them as entries.
"""

from collections import Counter

from falkordb import Graph

from lighthouse.clock import now
from lighthouse.kinds import Kind
from lighthouse.values import (
    MAX_ITEMS,
    WORDS,
    describe,
    is_name,
    named,
    whole_number,
    without_words,
)
from lighthouse.write import remember

# Entries with text that were not read for this kind yet, oldest first.
# Limit: this reads every entry with text on each call. Keep a mark of how far the reading
# came if a graph grows past what one read should carry.
WAITING = f"""
MATCH (n:Entry) WHERE n.{WORDS} IS NOT NULL AND ($types IS NULL OR n.type IN $types)
  AND NOT (n)-[:READ_BY {{kind: $kind}}]->(:Agent)
"""

READ = """
MATCH (n:Entry {id: $id})
MERGE (a:Agent {id: $by})
CREATE (n)-[:READ_BY {kind: $kind, at: localdatetime($now), rows: $rows}]->(a)
"""


def extract(graph: Graph, kind: Kind, extractor, by: str, types=None, limit: int = 100) -> dict:
    """Read entries with text that were not read for `kind` yet, oldest first, at most
    `limit` of them, and write the rows that `extractor` finds in each.

      extractor  a function of one entry (its properties: id, type, at, by, and its values)
                 that returns a list of rows of `kind`, as remember() takes them. A row
                 without "t" is true from the time of the entry. Its "entry" is the entry.
      types      the types of entries to read, such as ["observation"] (default: all)

    Returns {"read", "rows", "waiting"}: how many entries were read, how many rows came back
    with each status of remember(), and how many entries still wait. An extractor that
    raises stops the call; the entry it read stays waiting, and the ones before it are done.
    """
    named(by=by)
    if not callable(extractor):
        raise TypeError("extractor must be a function of one entry")
    if types is not None and (
        not isinstance(types, (list, tuple)) or not all(is_name(t) for t in types)
    ):
        raise ValueError(f"types must be a list of entry types, got {describe(types)}")
    params = {"kind": kind.label, "types": None if types is None else list(types)}
    found = graph.ro_query(
        f"{WAITING} RETURN n ORDER BY n.at, n.id LIMIT $limit",
        params | {"limit": whole_number(limit, "limit", 1_000)},
    ).result_set
    statuses: Counter = Counter()
    read = 0
    for (node,) in found:
        entry = without_words(node.properties)
        rows = extractor(dict(entry))
        if not isinstance(rows, list) or len(rows) > MAX_ITEMS:
            raise TypeError(f"the extractor must give a list of at most {MAX_ITEMS} rows")
        rows = [
            {"t": entry["at"], **row, "entry": entry["id"]} if isinstance(row, dict) else row
            for row in rows
        ]
        receipts = remember(graph, kind, rows, by)
        statuses.update(receipt["status"] for receipt in receipts)
        # The entry is marked once its rows are written. If the call stops in between, the
        # entry is read again, and the same rows are then unchanged.
        mark = {"id": entry["id"], "rows": len(rows), "kind": kind.label, "by": by, "now": now()}
        graph.query(READ, mark)
        read += 1
    waiting = graph.ro_query(f"{WAITING} RETURN count(n)", params).result_set[0][0]
    return {"read": read, "rows": dict(statuses), "waiting": waiting}
