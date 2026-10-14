"""The write path: rows become versions. No LLM is involved.

  (entity)-[:HAS_STATE]->(State)-[:NEXT]->(State)        history of the values
  (entity)-[:RELATION {valid_from, valid_to}]->(entity)  history of the relations
  (State)-[:FROM]->(Entry)                               the evidence for a State

A row is the full picture of one entity at one time. The entity node holds the current
values. Each State is one version of them, with a validity window. A row that differs from
the current State closes it and adds the next one, and closes or opens the relation edges
that changed. A row that comes late, with a time inside an earlier State, is put in at its
time: the history is the same in whatever order the rows arrive. Values are never
overwritten. A row that is not stored leaves a WriteFailure node.

  rows.py      a caller's row, checked and made ready for a query
  batches.py   remember(): rows in waves and queries, each a State after the current one
  late.py      rows that came late, put into the history at their time
  partial.py   update(): some values or relations change, the rest stays
  failures.py  record_failure(): what was not written is stored, never lost
"""

from lighthouse.write.batches import remember
from lighthouse.write.failures import record_failure
from lighthouse.write.partial import update

__all__ = ["record_failure", "remember", "update"]
