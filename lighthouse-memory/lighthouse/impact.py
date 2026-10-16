"""Causal blast-radius analysis and non-destructive entry invalidation.

When a late row rewrites history or an observation entry turns out to be faulty,
these functions trace the forward causal graph (`CITES`, `FROM`, `POINTS_TO`,
and `SUPPORTED_BY`) to find every downstream entry, state, handoff, lesson, and
playbook that relied on the superseded evidence.
"""

from datetime import UTC, datetime, timedelta

from redis.exceptions import ResponseError

from lighthouse.clock import now, stamp
from lighthouse.kinds import Kind
from lighthouse.values import (
    MAX_NAME,
    describe,
    is_key,
    is_name,
    named,
)
from lighthouse.write.failures import record_failure

MAX_REASON = 2_000
FUTURE_SECONDS = 300

STATE_IMPACT_QUERY = """
MATCH (e:__LABEL__ {__KEY__: $key})
OPTIONAL MATCH (n:Entry)-[c:CITES]->(e)
WHERE c.as_of >= localdatetime($since) AND c.as_of < localdatetime($until)
WITH collect(DISTINCT n) AS direct
UNWIND (CASE WHEN size(direct) = 0 THEN [null] ELSE direct END) AS d
OPTIONAL MATCH (d)<-[:CITES*1..6]-(downstream:Entry)
WITH direct, collect(DISTINCT downstream) AS down
WITH direct, [x IN down WHERE x IS NOT NULL AND NOT x IN direct] AS down_only,
     direct + [x IN down WHERE x IS NOT NULL AND NOT x IN direct] AS all_entries
UNWIND (CASE WHEN size(all_entries) = 0 THEN [null] ELSE all_entries END) AS en
OPTIONAL MATCH (ep:Episode)-[:HAS]->(en)
OPTIONAL MATCH (st:State)-[:FROM]->(en)
OPTIONAL MATCH (ent:Entity)-[:HAS_STATE]->(st)
WITH direct, down_only, all_entries,
     collect(DISTINCT ep) AS episodes,
     collect(DISTINCT [
         [l IN labels(ent) WHERE l <> 'Entity'][0],
         st.valid_from,
         en.id
     ]) AS states
RETURN [x IN direct WHERE x IS NOT NULL | x.id] AS direct_ids,
       [x IN down_only WHERE x IS NOT NULL | x.id] AS downstream_ids,
       [x IN episodes WHERE x IS NOT NULL | x.id] AS episode_ids,
       [s IN states WHERE s[0] IS NOT NULL] AS derived_states
"""

HANDOFF_IMPACT_QUERY = """
MATCH (h:Handoff)-[p:POINTS_TO]->(target)
WHERE h.accepted_at IS NULL
  AND (
      (
          $label IN labels(target)
          AND target.__KEY__ = $key
          AND p.as_of >= localdatetime($since)
          AND p.as_of < localdatetime($until)
      )
      OR (target:Entry AND target.id IN $entry_ids)
      OR (target:Episode AND target.id IN $episode_ids)
  )
RETURN DISTINCT h.id ORDER BY h.id
"""

LESSON_RISK_QUERY = """
UNWIND $episode_ids AS ep_id
MATCH (l:Lesson)-[:SUPPORTED_BY]->(ep:Episode {id: ep_id})
WHERE l.retired_at IS NULL
WITH l, count(DISTINCT ep) AS tainted
RETURN l.id, l.support, tainted, (l.support - tainted) < 1 AS at_risk
ORDER BY l.id
"""

PLAYBOOK_RISK_QUERY = """
UNWIND $episode_ids AS ep_id
MATCH (pb:Playbook {enabled: true})-[:SUPPORTED_BY]->(ep:Episode {id: ep_id})
WITH pb, count(DISTINCT ep) AS tainted
OPTIONAL MATCH (pb)-[:SUPPORTED_BY]->(all_ep:Episode)
WITH pb, tainted, count(DISTINCT all_ep) AS total_support
RETURN pb.id, pb.name, pb.version, total_support, tainted,
       (total_support - tainted) < 3 AS at_risk
ORDER BY pb.id
"""

ENTRY_IMPACT_QUERY = """
MATCH (root:Entry {id: $entry_id})
OPTIONAL MATCH (root)<-[:CITES*1..6]-(down:Entry)
WITH root, [x IN collect(DISTINCT down) WHERE x IS NOT NULL] AS down_only
WITH root, down_only, [root] + down_only AS all_entries
UNWIND all_entries AS en
OPTIONAL MATCH (ep:Episode)-[:HAS]->(en)
OPTIONAL MATCH (st:State)-[:FROM]->(en)
OPTIONAL MATCH (ent:Entity)-[:HAS_STATE]->(st)
WITH root, down_only,
     collect(DISTINCT ep.id) AS episode_ids,
     collect(DISTINCT [
         [l IN labels(ent) WHERE l <> 'Entity'][0],
         st.valid_from,
         en.id
     ]) AS states
RETURN root.id,
       root.invalidated_at IS NOT NULL AS invalidated,
       [x IN down_only | x.id] AS downstream_ids,
       [x IN episode_ids WHERE x IS NOT NULL] AS episodes,
       [s IN states WHERE s[0] IS NOT NULL] AS derived_states
"""

INVALIDATE_QUERY = """
MATCH (n:Entry {id: $entry_id})
WITH n, n.invalidated_at IS NOT NULL AS already
FOREACH (_ IN CASE WHEN already THEN [] ELSE [1] END |
    SET n.invalidated_at = localdatetime($at),
        n.invalidated_by = $by,
        n.invalidated_why = $reason
    MERGE (a:Agent {id: $by})
    CREATE (a)-[:INVALIDATED {at: localdatetime($at), reason:$reason}]->(n)
)
RETURN already
"""


def _check_window(since, until) -> tuple[str, str]:
    s_time = stamp(since)
    u_time = stamp(until)
    if s_time is None:
        raise ValueError("since must be a time")
    if u_time is None:
        raise ValueError("until must be a time")
    if s_time >= u_time:
        raise ValueError("since must be earlier than until")
    return s_time, u_time


def _risk_records(graph, entry_ids: list[str], episode_ids: list[str]) -> tuple[list, list]:
    if not episode_ids:
        return [], []
    lesson_rows = graph.ro_query(LESSON_RISK_QUERY, {"episode_ids": episode_ids}).result_set
    lessons = [
        {
            "id": lid,
            "support": int(support),
            "tainted_support": int(tainted),
            "at_risk": bool(at_risk),
        }
        for lid, support, tainted, at_risk in lesson_rows
    ]
    pb_rows = graph.ro_query(PLAYBOOK_RISK_QUERY, {"episode_ids": episode_ids}).result_set
    playbooks = [
        {
            "id": pid,
            "name": name,
            "version": int(version),
            "support": int(support),
            "tainted_support": int(tainted),
            "at_risk": bool(at_risk),
        }
        for pid, name, version, support, tainted, at_risk in pb_rows
    ]
    return lessons, playbooks


def impact_of_state(graph, kind: Kind, key, since, until) -> dict:
    """Finds every record that relied on `(kind, key)` during `[since, until)`.

    Returns direct entries, transitive downstream entries, derived entity states,
    affected episodes, waiting handoffs, and lessons or playbooks placed at risk.
    """
    if not isinstance(kind, Kind):
        raise TypeError("kind must be a Kind")
    if not is_key(key):
        raise ValueError("key must be a valid key")
    s_time, u_time = _check_window(since, until)

    query = STATE_IMPACT_QUERY.replace("__LABEL__", kind.label).replace("__KEY__", kind.key)
    rows = graph.ro_query(query, {"key": key, "since": s_time, "until": u_time}).result_set
    if not rows:
        return {
            "entity": (kind.label, key),
            "direct_entries": [],
            "downstream_entries": [],
            "derived_states": [],
            "episodes": [],
            "handoffs": [],
            "lessons": [],
            "playbooks": [],
        }

    direct_ids, downstream_ids, episode_ids, derived_raw = rows[0]
    direct_sorted = sorted(direct_ids)
    down_sorted = sorted(downstream_ids)
    ep_sorted = sorted(episode_ids)
    all_entries = direct_sorted + down_sorted

    handoff_query = HANDOFF_IMPACT_QUERY.replace("__KEY__", kind.key)
    handoff_rows = graph.ro_query(
        handoff_query,
        {
            "label": kind.label,
            "key": key,
            "since": s_time,
            "until": u_time,
            "entry_ids": all_entries,
            "episode_ids": ep_sorted,
        },
    ).result_set
    handoffs = [r[0] for r in handoff_rows]
    lessons, playbooks = _risk_records(graph, all_entries, ep_sorted)
    derived_states = sorted(
        [{"label": s[0], "valid_from": s[1], "from_entry": s[2]} for s in derived_raw],
        key=lambda item: (item["label"], str(item["valid_from"]), item["from_entry"]),
    )

    return {
        "entity": (kind.label, key),
        "direct_entries": direct_sorted,
        "downstream_entries": down_sorted,
        "derived_states": derived_states,
        "episodes": ep_sorted,
        "handoffs": handoffs,
        "lessons": lessons,
        "playbooks": playbooks,
    }


def impact_of_entry(graph, entry_id: str) -> dict | None:
    """Traces every downstream record that cited or derived from `entry_id`."""
    named(entry_id=entry_id)
    rows = graph.ro_query(ENTRY_IMPACT_QUERY, {"entry_id": entry_id}).result_set
    if not rows:
        return None
    root_id, invalidated, downstream_ids, episode_ids, derived_raw = rows[0]
    down_sorted = sorted(downstream_ids)
    ep_sorted = sorted(episode_ids)
    all_entries = [root_id, *down_sorted]

    handoff_rows = graph.ro_query(
        "MATCH (h:Handoff)-[:POINTS_TO]->(t) "
        "WHERE h.accepted_at IS NULL "
        "  AND ((t:Entry AND t.id IN $entries) OR (t:Episode AND t.id IN$episodes)) "
        "RETURN DISTINCT h.id ORDER BY h.id",
        {"entries": all_entries, "episodes": ep_sorted},
    ).result_set
    lessons, playbooks = _risk_records(graph, all_entries, ep_sorted)
    derived_states = sorted(
        [{"label": s[0], "valid_from": s[1], "from_entry": s[2]} for s in derived_raw],
        key=lambda item: (item["label"], str(item["valid_from"]), item["from_entry"]),
    )

    return {
        "id": root_id,
        "invalidated": bool(invalidated),
        "downstream_entries": down_sorted,
        "derived_states": derived_states,
        "episodes": ep_sorted,
        "handoffs": [r[0] for r in handoff_rows],
        "lessons": lessons,
        "playbooks": playbooks,
    }


def invalidate_entry(graph, entry_id: str, by: str, reason: str, at=None) -> dict:
    """Marks an entry as retracted without deleting it and returns its blast radius."""
    named(entry_id=entry_id, by=by)
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > MAX_REASON
        or "\x00" in reason
        or not is_name(reason.strip()[: min(len(reason.strip()), MAX_NAME)])
    ):
        detail = describe({"entry_id": entry_id, "by": by, "reason": reason})
        record_failure(graph, "invalid", "Entry", entry_id, detail)
        return {
            "id": None,
            "status": "invalid",
            "reason": "reason must be visible text of at most 2000 characters",
        }

    try:
        at_str = now() if at is None else stamp(at)
    except (TypeError, ValueError) as exc:
        record_failure(graph, "invalid", "Entry", entry_id, str(exc))
        return {"id": None, "status": "invalid", "reason": str(exc)}

    if at_str is None:
        record_failure(graph, "invalid", "Entry", entry_id, "at is empty")
        return {"id": None, "status": "invalid", "reason": "at must be a time"}

    max_future = stamp(datetime.now(UTC) + timedelta(seconds=FUTURE_SECONDS))
    if at_str > max_future:
        record_failure(graph, "invalid", "Entry", entry_id, "time in the future")
        return {
            "id": None,
            "status": "invalid",
            "reason": "at cannot be more than 5 minutes in the future",
        }

    try:
        rows = graph.query(
            INVALIDATE_QUERY,
            {"entry_id": entry_id, "by": by, "reason": reason.strip(), "at": at_str},
        ).result_set
    except ResponseError as exc:
        record_failure(graph, "failed", "Entry", entry_id, str(exc))
        return {"id": None, "status": "failed", "reason": str(exc)}

    if not rows:
        detail = describe({"entry_id": entry_id, "by": by, "reason": reason})
        record_failure(graph, "unknown", "Entry", entry_id, detail)
        return {"id": None, "status": "unknown", "reason": "the entry does not exist"}

    if rows[0][0]:
        return {"id": entry_id, "status": "exists"}

    return {
        "id": entry_id,
        "status": "invalidated",
        "impact": impact_of_entry(graph, entry_id),
    }
