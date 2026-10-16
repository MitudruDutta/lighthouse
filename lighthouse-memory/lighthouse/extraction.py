"""The free-text path: what agents wrote in entries becomes rows, off the write path.

The library holds no model. The application passes a function, the extractor, that reads
one entry and gives the rows it finds in it. extract() runs it over entries that it has not
read yet for a kind, and writes the rows by the write rule, each with the entry as the
evidence of what it adds:

  (State)-[:FROM]->(Entry)-[:READ_BY {kind, at, rows}]->(Agent)

An entry is read once for each kind. What the extractor gives is input like any other: the
write rule checks each row, and a row that is refused leaves a WriteFailure.

A call reads the entries stored since its mark, by their serial: the mark is kept on the
graph's stamp for each kind and set of types, and moves past the entries a call has done.
So a call costs what came since, not every entry of the graph.
"""

import hashlib
import json
from collections import Counter

from falkordb import Graph

from lighthouse.clock import now
from lighthouse.graphs import entries_after, entries_waiting, set_mark
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

# Entries with text of the types asked for that were not read for this kind yet.
WAITING = (
    f"n.{WORDS} IS NOT NULL AND ($types IS NULL OR n.type IN $types) "
    "AND NOT (n)-[:READ_BY {kind: $kind}]->(:Agent)"
)

READ = """
MATCH (n:Entry {id: $id})
MERGE (a:Agent {id: $by})
CREATE (n)-[:READ_BY {kind: $kind, at: localdatetime($now), rows: $rows}]->(a)
"""


def extract(graph: Graph, kind: Kind, extractor, by: str, types=None, limit: int = 100) -> dict:
    """Read entries with text that were not read for `kind` yet, in the order they were
    stored, at most `limit` of them, and write the rows that `extractor` finds in each.

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
    asked = None if types is None else sorted(set(types))
    digest = hashlib.sha256(json.dumps(asked).encode()).hexdigest()[:16]
    name = f"read_{kind.label}_{digest}"
    params = {"kind": kind.label, "types": asked}
    found, done = entries_after(graph, name, WAITING, params, whole_number(limit, "limit", 1_000))
    statuses: Counter = Counter()
    read = 0
    for node in found:
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
    set_mark(graph, name, done)
    left = entries_waiting(graph, done, WAITING, params)
    return {"read": read, "rows": dict(statuses), "waiting": left}
