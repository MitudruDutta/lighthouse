"""Playbooks: what to do when a situation comes again. The procedural memory.

  (Playbook)-[:WHEN]->(Trigger)                the situation it is for
  (Playbook)-[:HAS_STEP]->(Step)               what to do, in order
  (Playbook)-[:SUPPORTED_BY]->(Episode)        the episodes it was drawn from
  (Playbook)-[:RAN_IN {succeeded}]->(Episode)  where it ran, and how that ended
  (Playbook)-[:REPLACES]->(Playbook)           the version before it
  (Agent)-[:WROTE]->(Playbook)

Writing what an agent will do is riskier than writing what it knows. So a playbook needs a
number of episodes that ended, it is never changed, only replaced by a next version, it can
be switched off, and it switches itself off after failures in a row. The library writes no
playbook of its own: the application says what the steps are.
"""

import json

from falkordb import Graph
from redis.exceptions import ResponseError

from lighthouse.clock import now
from lighthouse.episodes import moment, refuse
from lighthouse.read import pages
from lighthouse.values import MAX_REFERENCES, MAX_SIZE, describe, is_name, named, properties

NEEDS = 3  # episodes a playbook rests on, unless the caller asks for more or fewer
STOP_AFTER = 3  # failures in a row that switch a playbook off
MAX_STEPS = 50
MAX_TRIGGER = 20  # properties of a trigger

# Properties of a playbook that the library sets.
PLAYBOOK_PROPERTIES = {"id", "name", "version", "by", "at", "recorded_at", "enabled"}
PLAYBOOK_PROPERTIES |= {"runs", "succeeded", "failed", "failed_in_a_row", "stopped_at"}
PLAYBOOK_PROPERTIES |= {"switched_at", "switched_by", "trigger", "steps", "supported_by"}

# The newest version of a playbook is the one that no version replaces.
NEWEST = "NOT (:Playbook)-[:REPLACES]->(pb)"

WRITE = f"""
OPTIONAL MATCH (pb:Playbook {{name: $name}}) WHERE {NEWEST}
WITH pb AS last
OPTIONAL MATCH (ep:Episode) WHERE ep.id IN $episodes AND ep.closed_at IS NOT NULL
WITH last, collect(ep) AS proof, coalesce(last.version, 0) + 1 AS version,
     localdatetime($at) AS t
WITH last, proof, version, t,
  CASE
    WHEN size(proof) < size($episodes) THEN 'missing'
    WHEN size(proof) < $needs THEN 'unsupported'
    ELSE 'written'
  END AS status
FOREACH (_ IN CASE WHEN status = 'written' THEN [1] ELSE [] END |
  CREATE (new:Playbook {{id: $name + '#' + toString(version), name: $name, version: version,
                        by: $by, at: t, recorded_at: localdatetime($now), enabled: true,
                        runs: 0, succeeded: 0, failed: 0, failed_in_a_row: 0}})
  CREATE (new)-[:WHEN]->(trigger:Trigger)
  SET trigger += $trigger
  MERGE (a:Agent {{id: $by}})
  CREATE (a)-[:WROTE]->(new)
  FOREACH (ep IN proof | CREATE (new)-[:SUPPORTED_BY {{at: t, by: $by}}]->(ep))
  FOREACH (step IN $steps |
    CREATE (new)-[:HAS_STEP]->(s:Step {{seq: step.seq}})
    SET s += step.values)
  FOREACH (old IN CASE WHEN last IS NULL THEN [] ELSE [last] END |
    CREATE (new)-[:REPLACES]->(old)
    SET old.enabled = false)
)
RETURN status, version
"""

SWITCH = f"""
MATCH (pb:Playbook {{name: $name}}) WHERE {NEWEST}
WITH pb, CASE WHEN pb.enabled = $on THEN 'exists' WHEN $on THEN 'on' ELSE 'off' END AS status
FOREACH (_ IN CASE WHEN status <> 'exists' THEN [1] ELSE [] END |
  SET pb.enabled = $on, pb.failed_in_a_row = 0,
      pb.switched_at = localdatetime($now), pb.switched_by = $by)
RETURN status, pb.id
"""

# What a run changes is worked out before any write: a FOREACH sees what an earlier one set.
RAN = f"""
MATCH (pb:Playbook {{name: $name}}) WHERE {NEWEST}
OPTIONAL MATCH (ep:Episode {{id: $episode}})
OPTIONAL MATCH (pb)-[run:RAN_IN]->(ep)
WITH pb, ep, run, localdatetime($at) AS t,
  CASE
    WHEN ep IS NULL THEN 'missing'
    WHEN run IS NULL THEN 'recorded'
    WHEN run.succeeded IS NULL AND $succeeded IS NOT NULL THEN 'judged'
    ELSE 'exists'
  END AS status
WITH pb, ep, run, t, status,
  status IN ['recorded', 'judged'] AND $succeeded = true AS won,
  status IN ['recorded', 'judged'] AND $succeeded = false AS lost
WITH pb, ep, run, t, status, won, lost,
  lost AND pb.failed_in_a_row + 1 >= $stop_after AS stops
FOREACH (_ IN CASE WHEN status = 'recorded' THEN [1] ELSE [] END |
  CREATE (pb)-[:RAN_IN {{at: t, by: $by, succeeded: $succeeded}}]->(ep)
  SET pb.runs = pb.runs + 1)
FOREACH (r IN CASE WHEN status = 'judged' THEN [run] ELSE [] END |
  SET r.succeeded = $succeeded, r.judged_by = $by)
FOREACH (_ IN CASE WHEN won THEN [1] ELSE [] END |
  SET pb.succeeded = pb.succeeded + 1, pb.failed_in_a_row = 0)
FOREACH (_ IN CASE WHEN lost THEN [1] ELSE [] END |
  SET pb.failed = pb.failed + 1, pb.failed_in_a_row = pb.failed_in_a_row + 1)
FOREACH (_ IN CASE WHEN stops THEN [1] ELSE [] END |
  SET pb.enabled = false, pb.stopped_at = t)
RETURN status, pb.id, pb.enabled AND NOT stops
"""

REFUSED = {
    "missing": "an episode does not exist or has not ended",
    "unsupported": "it rests on too few episodes that ended",
    "unknown": "there is no such playbook",
}


def _steps(steps) -> list[dict]:
    if not isinstance(steps, (list, tuple)) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError(f"steps must be a list of 1 to {MAX_STEPS} steps")
    return [
        {"seq": n, "values": properties(step, {"seq"}, f"step {n}")}
        for n, step in enumerate(steps, start=1)
    ]


def write_playbook(
    graph: Graph, name: str, by: str, trigger, steps, supported_by, needs: int = NEEDS, at=None
) -> dict:
    """Write the next version of a playbook. The version before it is switched off.

      trigger       the situation it is for: properties that must all be there
      steps         what to do, in order: a list of property maps
      supported_by  ids of the episodes it was drawn from. All must have ended.
      needs         how many episodes it must rest on (default 3)

    Returns a receipt. {"id", "version", "status": "written"} when stored. Otherwise
    {"id": None, "status", "reason"} with status
      missing      an episode in `supported_by` does not exist or has not ended
      unsupported  it rests on fewer episodes than it needs
      invalid      no trigger, no steps, or something that cannot be stored
      failed       the database refused the query
    and a WriteFailure node that holds the refused playbook.
    """
    named(name=name, by=by)
    content = {"trigger": trigger, "steps": steps, "supported_by": supported_by, "needs": needs}
    try:
        if type(needs) is not int or not 1 <= needs <= MAX_REFERENCES:
            raise ValueError(f"needs must be a whole number from 1 to {MAX_REFERENCES}")
        if not isinstance(supported_by, (list, tuple)) or len(supported_by) > MAX_REFERENCES:
            raise ValueError(f"supported_by must be a list of at most {MAX_REFERENCES} episode ids")
        if not all(is_name(item) for item in supported_by):
            raise ValueError(f"supported_by: not an episode id in {describe(supported_by)}")
        when = properties(trigger, set(), "trigger")
        if not 1 <= len(when) <= MAX_TRIGGER:
            raise ValueError(f"trigger must have 1 to {MAX_TRIGGER} properties")
        params = {
            "name": name,
            "by": by,
            "trigger": when,
            "steps": _steps(steps),
            "episodes": list(dict.fromkeys(supported_by)),
            "needs": needs,
            "at": moment(at),
            "now": now(),
        }
        if len(json.dumps([params["trigger"], params["steps"]])) > MAX_SIZE:
            raise ValueError(f"the playbook is larger than {MAX_SIZE} characters")
        status, version = graph.query(WRITE, params).result_set[0]
    except (TypeError, ValueError) as exc:
        return refuse(graph, "Playbook", name, "invalid", str(exc), content)
    except ResponseError as exc:
        return refuse(graph, "Playbook", name, "failed", str(exc), content)
    if status != "written":
        return refuse(graph, "Playbook", name, status, REFUSED[status], content)
    return {"id": f"{name}#{version}", "version": version, "status": status}


def switch(graph: Graph, name: str, by: str, on: bool) -> dict:
    """Switch the newest version of a playbook on or off. Switching on clears the count of
    failures in a row. Status: on, off, exists (it was so already), or unknown."""
    named(name=name, by=by)
    if type(on) is not bool:
        raise TypeError("on must be True or False")
    rows = graph.query(SWITCH, {"name": name, "by": by, "on": on, "now": now()}).result_set
    if not rows:
        return refuse(graph, "Playbook", name, "unknown", REFUSED["unknown"], {"by": by, "on": on})
    return {"id": rows[0][1], "status": rows[0][0]}


def ran(
    graph: Graph,
    name: str,
    by: str,
    episode_id: str,
    succeeded=None,
    stop_after: int = STOP_AFTER,
    at=None,
) -> dict:
    """Record that the newest version of a playbook ran in an episode. `succeeded` says how
    it ended: True, False, or None while that is not known. It can be said once, in this
    call or a later one. After `stop_after` failures in a row the playbook switches off.

    Returns {"id", "status", "enabled"} with status recorded, judged, or exists; or a
    refusal with status missing (the episode) or unknown (the playbook).
    """
    named(name=name, by=by, episode_id=episode_id)
    if succeeded is not None and type(succeeded) is not bool:
        raise TypeError("succeeded must be True, False, or None")
    if type(stop_after) is not int or stop_after < 1:
        raise ValueError("stop_after must be a whole number from 1")
    content = {"by": by, "episode": episode_id, "succeeded": succeeded}
    params = {"name": name, "by": by, "episode": episode_id, "succeeded": succeeded}
    try:
        rows = graph.query(RAN, params | {"stop_after": stop_after, "at": moment(at)}).result_set
    except (TypeError, ValueError) as exc:
        return refuse(graph, "Playbook", name, "invalid", str(exc), content)
    if not rows:
        return refuse(graph, "Playbook", name, "unknown", REFUSED["unknown"], content)
    status, playbook_id, enabled = rows[0]
    if status == "missing":
        return refuse(graph, "Playbook", name, status, "the episode does not exist", content)
    return {"id": playbook_id, "status": status, "enabled": enabled}


def _whole(node, trigger, steps, proof) -> dict:
    return {
        **node.properties,
        "trigger": dict(trigger.properties),
        "steps": [{k: v for k, v in step.properties.items() if k != "seq"} for step in steps],
        "supported_by": sorted(proof),
    }


READ = """
OPTIONAL MATCH (pb)-[:HAS_STEP]->(s:Step)
WITH pb, trigger, s ORDER BY s.seq
WITH pb, trigger, collect(s) AS steps
OPTIONAL MATCH (pb)-[:SUPPORTED_BY]->(ep:Episode)
RETURN pb, trigger, steps, collect(ep.id) ORDER BY pb.name
"""


def playbook(graph: Graph, name: str, version: int | None = None) -> dict | None:
    """One version of a playbook with its trigger, steps, counts, and the episodes it rests
    on. The newest version by default. None if there is none."""
    named(name=name)
    if version is not None and type(version) is not int:
        raise ValueError("version must be a whole number")
    which = NEWEST if version is None else "pb.version = $version"
    rows = graph.ro_query(
        f"MATCH (pb:Playbook {{name: $name}})-[:WHEN]->(trigger:Trigger) WHERE {which} {READ}",
        {"name": name, "version": version},
    ).result_set
    return _whole(*rows[0]) if rows else None


def playbooks_for(graph: Graph, situation: dict) -> list[dict]:
    """The playbooks that are switched on and whose trigger fits a situation: every property
    of the trigger is in the situation with the same value. Best record first: successes
    minus failures, then runs."""
    facts = properties(situation, set(), "situation")
    rows = pages(
        graph,
        # Only the newest version of a playbook can be switched on. The trigger is compared
        # in the query, so only the playbooks that fit come back. A property the situation
        # lacks reads as null, which fits nothing; a value fits only a value of its own type.
        "MATCH (pb:Playbook {enabled: true})-[:WHEN]->(trigger:Trigger) "
        f"WHERE all(name IN keys(trigger) WHERE trigger[name] = $situation[name]) {READ}",
        {"situation": facts},
    )
    fitting = [_whole(*row) for row in rows]
    return sorted(fitting, key=lambda pb: (pb["failed"] - pb["succeeded"], -pb["runs"], pb["name"]))
