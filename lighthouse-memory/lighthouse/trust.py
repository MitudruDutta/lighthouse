"""Trust in an agent, read from what the graph already records about its work.

Four kinds of evidence, each counted for and against the agent:

  entries    entries it wrote, against those that were later invalidated
  episodes   closed episodes it wrote in that a lesson rests on, against those that
             contradict a lesson
  runs       playbook runs it recorded that succeeded, against those that failed
  versions   versions it wrote that held for at least QUICK seconds, against those that a
             later write replaced sooner: a value that keeps flipping

The score is the mean of the four rates, each smoothed as (for + 1) / (for + against + 2),
over the kinds of evidence the agent has. So a kind with many items, such as versions, does
not drown the others. With no evidence at all, the score is None: nothing is known.
"""

from lighthouse.values import named

QUICK = 60  # seconds: a version replaced sooner than this counts against its writer

ENTRIES = """
MATCH (:Agent {id: $agent})-[:WROTE]->(n:Entry)
RETURN count(n), sum(CASE WHEN n.invalidated_at IS NOT NULL THEN 1 ELSE 0 END)
"""

EPISODES = """
MATCH (:Agent {id: $agent})-[:WROTE]->(:Entry)<-[:HAS]-(ep:Episode)
WHERE ep.closed_at IS NOT NULL
WITH DISTINCT ep
OPTIONAL MATCH (l1:Lesson)-[:SUPPORTED_BY]->(ep) WHERE l1.retired_at IS NULL
WITH ep, count(DISTINCT l1) AS agree
OPTIONAL MATCH (l2:Lesson)-[:CONTRADICTED_BY]->(ep) WHERE l2.retired_at IS NULL
WITH ep, agree, count(DISTINCT l2) AS disagree
RETURN count(ep),
       sum(CASE WHEN agree > 0 THEN 1 ELSE 0 END),
       sum(CASE WHEN disagree > 0 THEN 1 ELSE 0 END)
"""

RUNS = """
MATCH (:Playbook)-[r:RAN_IN {by: $agent}]->(:Episode)
RETURN count(r),
       sum(CASE WHEN r.succeeded = true THEN 1 ELSE 0 END),
       sum(CASE WHEN r.succeeded = false THEN 1 ELSE 0 END)
"""

# The versions an agent wrote, found through the index on the writer of a State.
VERSIONS = """
MATCH (s:State {by: $agent})
RETURN count(s),
       sum(CASE WHEN s.valid_to IS NOT NULL
                 AND s.valid_to < s.valid_from + duration({seconds: $quick})
            THEN 1 ELSE 0 END)
"""


def _row(graph, query: str, params: dict) -> list[int]:
    return [int(value or 0) for value in graph.ro_query(query, params).result_set[0]]


def agent_trust(graph, agent: str) -> dict:
    """How far the work of `agent` held: the counts of each kind of evidence, and "score",
    from 0 to 1, or None for an agent with no evidence. The name is checked like every
    name; it is not looked up as anyone's identity."""
    named(agent=agent)
    params = {"agent": agent, "quick": QUICK}
    written, invalidated = _row(graph, ENTRIES, params)
    closed, corroborated, contradicted = _row(graph, EPISODES, params)
    runs, succeeded, failed = _row(graph, RUNS, params)
    versions, short_lived = _row(graph, VERSIONS, params)
    evidence = [
        (written - invalidated, invalidated),
        (corroborated, contradicted),
        (succeeded, failed),
        (versions - short_lived, short_lived),
    ]
    rates = [(good + 1) / (good + bad + 2) for good, bad in evidence if good + bad]
    return {
        "agent": agent,
        "score": round(sum(rates) / len(rates), 4) if rates else None,
        "entries_written": written,
        "entries_invalidated": invalidated,
        "closed_episodes": closed,
        "corroborated_episodes": corroborated,
        "contradicted_episodes": contradicted,
        "playbook_runs": runs,
        "runs_succeeded": succeeded,
        "runs_failed": failed,
        "states_written": versions,
        "states_short_lived": short_lived,
    }
