"""Tasks that agents hand to each other through the graph.

  (Task)-[:AFTER]->(Task)               a task waits until the tasks it comes after are done
  (Task)-[:CLAIMED_BY {at}]->(Agent)    every claim of the task; `owner` names the last

FalkorDB runs one write query at a time per graph and a query is atomic. A claim is one
query that finds a free task and gives it an owner, so two agents cannot win the same task.
A task is free when it is open, or when its claim ran past the lease the claimer took, and
when every task it comes after is done.
"""

from datetime import UTC, datetime, timedelta

from falkordb import Graph

from lighthouse.clock import now, stamp
from lighthouse.values import MAX_REFERENCES, describe, is_key, is_name, named, whole_number

MAX_LEASE = 7 * 24 * 3600  # seconds: the longest claim that can run out

# A task comes after tasks that exist: so the order of tasks has no cycle.
ADD = """
OPTIONAL MATCH (old:Task {id: $id})
OPTIONAL MATCH (before:Task) WHERE before.id IN $after
WITH old, collect(before) AS before
WITH old, before,
  CASE
    WHEN old IS NOT NULL THEN 'exists'
    WHEN size(before) < size($after) THEN 'missing'
    ELSE 'added'
  END AS status
FOREACH (_ IN CASE WHEN status = 'added' THEN [1] ELSE [] END |
  CREATE (t:Task {id: $id, kind: $kind, status: 'open', ref: $ref,
                  created_at: localdatetime($now)})
  FOREACH (b IN before | CREATE (t)-[:AFTER]->(b)))
RETURN status
"""

# No free task of this kind: no row comes back and nothing is written, the Agent included.
CLAIM = """
MATCH (t:Task {kind: $kind})
WHERE (t.status = 'open' OR (t.status = 'claimed' AND t.until < localdatetime($now)))
  AND NOT (t)-[:AFTER]->(:Task {status: 'open'})
  AND NOT (t)-[:AFTER]->(:Task {status: 'claimed'})
WITH t ORDER BY t.created_at, t.id LIMIT 1
MERGE (a:Agent {id: $agent})
SET t.status = 'claimed', t.owner = $agent, t.until = localdatetime($until)
CREATE (t)-[:CLAIMED_BY {at: localdatetime($now)}]->(a)
RETURN t.id, t.kind, t.ref, t.until
"""

COMPLETE = """
MATCH (t:Task {id: $id, status: 'claimed', owner: $agent})
SET t.status = 'done', t.done_at = localdatetime($now), t.until = NULL
RETURN t.id
"""

RELEASE = """
MATCH (t:Task {id: $id, status: 'claimed', owner: $agent})
SET t.status = 'open', t.owner = NULL, t.until = NULL
RETURN t.id
"""


def add_task(graph: Graph, task_id: str, kind: str, ref=None, after=()) -> bool:
    """Add an open task. `ref` is the key of the graph entity the task is about. `after`
    lists the ids of tasks that must be done before this one can be claimed.

    Returns False, and changes nothing, if a task with this id exists. Raises ValueError,
    and adds nothing, if a task in `after` does not exist."""
    named(task_id=task_id, kind=kind)
    if ref is not None and not is_key(ref):
        raise ValueError("ref must be the key of an entity: a name or an integer")
    if not isinstance(after, (list, tuple)) or len(after) > MAX_REFERENCES:
        raise ValueError(f"after must be a list of at most {MAX_REFERENCES} task ids")
    if not all(is_name(item) for item in after):
        raise ValueError(f"after must hold task ids, got {describe(after)}")
    params = {"id": task_id, "kind": kind, "ref": ref, "after": list(dict.fromkeys(after))}
    status = graph.query(ADD, params | {"now": now()}).result_set[0][0]
    if status == "missing":
        raise ValueError(f"a task in after does not exist: {describe(after)}")
    return status == "added"


def claim(graph: Graph, agent: str, kind: str, lease: int | None = None) -> dict | None:
    """Give the oldest free task of `kind` to `agent`: {"id", "kind", "ref", "until"}. None if
    no task is free.

    `lease` is how many seconds the claim holds (default: until it is done or released).
    After that, another agent can claim the task, and the first can no longer complete it.
    "until" is the time the lease runs out, or None."""
    named(agent=agent, kind=kind)
    until = None
    if lease is not None:
        lease = whole_number(lease, "lease", MAX_LEASE)
        until = stamp(datetime.now(UTC) + timedelta(seconds=lease))
    params = {"agent": agent, "kind": kind, "until": until, "now": now()}
    rows = graph.query(CLAIM, params).result_set
    return dict(zip(("id", "kind", "ref", "until"), rows[0])) if rows else None


def complete(graph: Graph, agent: str, task_id: str) -> bool:
    """Mark a task done. Only its owner can, once; returns False otherwise. An owner whose
    lease ran out can still complete the task while no other agent has claimed it."""
    named(agent=agent, task_id=task_id)
    rows = graph.query(COMPLETE, {"agent": agent, "id": task_id, "now": now()}).result_set
    return bool(rows)


def release(graph: Graph, agent: str, task_id: str) -> bool:
    """Give a claimed task back, open for another agent. Only its owner can; returns False
    otherwise."""
    named(agent=agent, task_id=task_id)
    return bool(graph.query(RELEASE, {"agent": agent, "id": task_id}).result_set)
