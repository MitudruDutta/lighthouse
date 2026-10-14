"""Conversations: what was said in the sessions of a user, in order.

  (Session)-[:HAS]->(Message)-[:NEXT]->(Message)   what was said, in the order it was written
  (Message)-[:MENTIONS]->(Reference)               what a message is about, by name

A session belongs to one user, and every call names that user. The key of a session holds
the user, so a session of another user is not found, whatever id is asked for. The first
message opens the session. A message takes its number in the query that links it after the
last one, so messages written at the same moment still get one order. A message that
cannot be stored leaves a WriteFailure node.

A mention is a name: the label and the key of an entity or a record. It is not an edge to
the thing, and the thing is not looked up, because it may be in another graph, such as the
graph that all tenants share.

A long session has a summary: what its messages up to one number come to, in the words of
the application's model. The library holds no model. context() gives the summary and the
messages after it.

A session can be forgotten, and so can everything a user said. This is the one place where
the library deletes what was written; elsewhere, only a row that came late replaces the NEXT
link between two States. Whatever else in the graph relies on nothing being deleted is
told: each query that deletes gives the graph a new stamp.
"""

import json

from falkordb import Graph
from redis.exceptions import ResponseError

from lighthouse.clock import now
from lighthouse.episodes import evidence, moment, pairs, refuse
from lighthouse.read import READ_TIMEOUT
from lighthouse.recall.text import words
from lighthouse.values import (
    MAX_SIZE,
    MAX_TEXT,
    WORDS,
    indexed,
    is_storable,
    named,
    properties,
    whole_number,
    without_words,
)

# Properties of a message that the library sets, or adds when the message is read. The
# values of a message cannot use these names.
MESSAGE_PROPERTIES = {"key", "session", "user", "seq", "role", "text", "at", "recorded_at", "by"}
MESSAGE_PROPERTIES |= {"mentions", "score", WORDS}

# The session counts its messages. The next message takes the next number in the same
# query that links it after the last one, so two writers cannot take the same place.
SAY = """
MERGE (s:Session {key: $session})
  ON CREATE SET s.id = $id, s.user = $user, s.opened_at = localdatetime($at), s.message_count = 0
WITH s, s.message_count + 1 AS seq, localdatetime($at) AS t
OPTIONAL MATCH (last:Message {key: s.key + '/' + toString(seq - 1)})
SET s.message_count = seq, s.active_at = localdatetime($now)
CREATE (s)-[:HAS]->(m:Message {key: s.key + '/' + toString(seq), session: $id, user: $user,
                              seq: seq, role: $role, text: $text, at: t,
                              recorded_at: localdatetime($now), by: $by})
SET m += $values, m += $words
FOREACH (l IN CASE WHEN last IS NULL THEN [] ELSE [last] END | CREATE (l)-[:NEXT]->(m))
FOREACH (r IN $mentions |
  MERGE (x:Reference {key: r[0]}) ON CREATE SET x.label = r[1], x.id = r[2]
  CREATE (m)-[:MENTIONS]->(x))
RETURN seq
"""

# A message is found by its key, so a window costs the same in a session of any length.
WINDOW = """
MATCH (s:Session {key: $session})
WITH s, CASE WHEN $before IS NULL OR $before > s.message_count
             THEN s.message_count + 1 ELSE $before END AS stop
UNWIND range(stop - $last, stop - 1) AS n
MATCH (m:Message {key: s.key + '/' + toString(n)})
OPTIONAL MATCH (m)-[:MENTIONS]->(r:Reference)
WITH m, collect([r.label, r.id]) AS mentions
RETURN m, mentions ORDER BY m.seq
"""

NEWEST = "m.at DESC, m.session, m.seq DESC"

SUM = """
MATCH (s:Session {key: $session})
WITH s,
  CASE
    WHEN $upto > s.message_count THEN 'invalid'
    WHEN $upto < coalesce(s.summary_upto, 0) THEN 'stale'
    ELSE 'summed'
  END AS status
FOREACH (_ IN CASE WHEN status = 'summed' THEN [1] ELSE [] END |
  SET s.summary = $text, s.summary_upto = $upto, s.summary_by = $by,
      s.summary_at = localdatetime($now))
RETURN status
"""

REFUSED = {
    "unknown": "the user has no such session",
    "stale": "the summary that is there reaches further",
    "invalid": "upto is past the last message of the session",
}

# FalkorDB cannot stop a write, so one query deletes a bounded number of things.
BATCH = 200

# Other parts of the library keep answers while a graph only grows. A query that deletes
# gives the graph a new stamp in the same step, so none of those answers is given again.
RESTAMP = """OPTIONAL MATCH (stamp:Stamp)
SET stamp.id = randomUUID()"""

# The last messages go first, and the session counts down with them. So after every query
# the session is a shorter session that reads right, and it goes with its last message.
FORGET = f"""
MATCH (s:Session {{key: $session}})
WITH s, s.message_count AS held
UNWIND range(held - $batch + 1, held) AS n
OPTIONAL MATCH (m:Message {{key: s.key + '/' + toString(n)}})
OPTIONAL MATCH (m)-[:MENTIONS]->(r:Reference)
WITH s, held, collect(DISTINCT m) AS gone, collect(DISTINCT r.key) AS mentioned
WITH s, held - size(gone) AS left, gone, mentioned
{RESTAMP}, s.message_count = left
FOREACH (m IN gone | DETACH DELETE m)
FOREACH (_ IN CASE WHEN left <= 0 THEN [1] ELSE [] END | DETACH DELETE s)
RETURN size(gone), left, mentioned
"""

# A reference that no message mentions any more goes too: it may name the user.
ORPHANS = f"""
UNWIND $keys AS k
MATCH (r:Reference {{key: k}})
OPTIONAL MATCH (r)<-[e:MENTIONS]-()
WITH r, count(e) AS left WHERE left = 0
{RESTAMP}
DELETE r
"""

# What a refused message or summary held is kept in a WriteFailure with its owner.
FAILURES = f"""
MATCH (f:WriteFailure {{owner: $user}}) WHERE $id IS NULL OR f.key = $id
WITH f LIMIT $batch
{RESTAMP}
DELETE f
RETURN count(f)
"""

ABOUT = f"""
MATCH (:Reference {{key: $reference}})<-[:MENTIONS]-(m:Message) WHERE m.user = $user
WITH m ORDER BY {NEWEST} LIMIT $limit
OPTIONAL MATCH (m)-[:MENTIONS]->(r:Reference)
WITH m, collect([r.label, r.id]) AS mentions
RETURN m, mentions ORDER BY {NEWEST}
"""

FIND = f"""
CALL db.idx.fulltext.queryNodes('Message', $terms) YIELD node, score
WITH node AS m, score WHERE m.user = $user
WITH m, score ORDER BY score DESC, {NEWEST} LIMIT $limit
OPTIONAL MATCH (m)-[:MENTIONS]->(r:Reference)
WITH m, score, collect([r.label, r.id]) AS mentions
RETURN m, mentions, score ORDER BY score DESC, {NEWEST}
"""


def _session(user: str, session_id: str) -> str:
    """The key of a session in the graph: the user and the id, in a form that no other
    user and id can give."""
    return json.dumps([user, session_id])


def _message(node, mentions) -> dict:
    values = {k: v for k, v in without_words(node.properties).items() if k not in ("key", "user")}
    return {**values, "mentions": pairs(mentions)}


def say(
    graph: Graph,
    user: str,
    session_id: str,
    role: str,
    text: str,
    by: str,
    mentions=(),
    values=None,
    at=None,
) -> dict:
    """Add one message to a session of `user`. The first message opens the session.

      role      who speaks, as the application names it: the user, an agent, a tool
      by        the agent or user that wrote the message
      mentions  what the message is about: entities as (Kind, key), records as (label, id)
      values    more properties of the message
      at        when it was said (default: now)

    Returns a receipt. {"id", "seq", "status": "said"} when stored: the id of the session
    and the number of the message in it. Otherwise {"id": None, "status", "reason"} with
      invalid  the text, the mentions, the values, or the time cannot be stored
      failed   the database refused the query
    and a WriteFailure node that holds the refused message.
    """
    named(user=user, session_id=session_id, role=role, by=by)
    content = {"user": user, "role": role, "by": by, "text": text, "mentions": mentions}
    content |= {"values": values, "at": at}
    try:
        if not isinstance(text, str) or not is_storable(text):
            raise ValueError(f"text must be text of at most {MAX_TEXT} characters")
        params = {
            "session": _session(user, session_id),
            "id": session_id,
            "user": user,
            "role": role,
            "text": text,
            "by": by,
            "mentions": [
                [json.dumps([label, key]), label, key]
                for label, _, keys in evidence(mentions, "mentions")
                for key in keys
            ],
            "values": properties(values, MESSAGE_PROPERTIES, "values"),
            "words": indexed([text]),
            "at": moment(at),
            "now": now(),
        }
        if len(text) + len(json.dumps(params["values"])) > MAX_SIZE:
            raise ValueError(f"the message is larger than {MAX_SIZE} characters")
        seq = graph.query(SAY, params).result_set[0][0]
    except (TypeError, ValueError) as exc:
        return refuse(graph, "Message", session_id, "invalid", str(exc), content, user)
    except ResponseError as exc:
        return refuse(graph, "Message", session_id, "failed", str(exc), content, user)
    return {"id": session_id, "seq": seq, "status": "said"}


def messages(graph: Graph, user: str, session_id: str, last: int = 20, before=None) -> list[dict]:
    """The last messages of a session of `user`, oldest first, at most `last` of them. Each
    has "mentions": the (label, key) pairs it names. `before` is the number of a message:
    the messages just before that one are given, to read further back.

    A session that the user does not have gives nothing.
    """
    named(user=user, session_id=session_id)
    params = {"session": _session(user, session_id), "last": whole_number(last, "last", 1_000)}
    params["before"] = None if before is None else whole_number(before, "before", 2**62)
    return [_message(node, found) for node, found in graph.ro_query(WINDOW, params).result_set]


def sessions(graph: Graph, user: str, limit: int = 20) -> list[dict]:
    """The sessions of `user`, the one written to last first: [{"id", "opened_at",
    "active_at", "messages"}]. "messages" is how many it holds."""
    named(user=user)
    rows = graph.ro_query(
        "MATCH (s:Session {user: $user}) "
        "RETURN s.id, s.opened_at, s.active_at, s.message_count "
        "ORDER BY s.active_at DESC, s.id LIMIT $limit",
        {"user": user, "limit": whole_number(limit, "limit", 1_000)},
    ).result_set
    names = ("id", "opened_at", "active_at", "messages")
    return [dict(zip(names, row, strict=True)) for row in rows]


def said_about(graph: Graph, user: str, reference, limit: int = 20) -> list[dict]:
    """The messages in the sessions of `user` that mention one thing, newest first.
    `reference` is (Kind, key) for an entity, or (label, id) for a record."""
    named(user=user)
    ((label, _, [key]),) = evidence([reference], "reference")
    params = {"reference": json.dumps([label, key]), "user": user}
    params["limit"] = whole_number(limit, "limit", 1_000)
    rows = graph.ro_query(ABOUT, params, timeout=READ_TIMEOUT).result_set
    return [_message(node, found) for node, found in rows]


def said(graph: Graph, user: str, question: str, limit: int = 10, match: str = "all") -> list[dict]:
    """The messages in the sessions of `user` whose text has the words of `question`, best
    first. Each has "score" and "mentions".

      match  "all": every word must be there. "any": one word is enough.

    Only the letters and digits of the question are used. A question without any finds
    nothing.
    """
    named(user=user)
    if not isinstance(question, str):
        raise TypeError("question must be text")
    if match not in ("all", "any"):
        raise ValueError('match must be "all" or "any"')
    terms = words(question)
    params = {"terms": (" " if match == "all" else "|").join(terms), "user": user}
    params["limit"] = whole_number(limit, "limit", 1_000)
    if not terms:
        return []
    rows = graph.ro_query(FIND, params, timeout=READ_TIMEOUT).result_set
    return [{**_message(node, found), "score": score} for node, found, score in rows]


def summarize(graph: Graph, user: str, session_id: str, text: str, upto: int, by: str) -> dict:
    """Store what the messages of a session up to number `upto` come to. The text is the
    application's: the library holds no model. A session has one summary, and a later one
    takes its place.

    Returns a receipt. {"id", "upto", "status": "summed"} when stored. Otherwise
    {"id": None, "status", "reason"} with status
      unknown  the user has no such session
      stale    the summary that is there reaches further than `upto`
      invalid  the text cannot be stored, or `upto` is not the number of a message
      failed   the database refused the query
    and a WriteFailure node that holds the refused summary.
    """
    named(user=user, session_id=session_id, by=by)
    content = {"user": user, "by": by, "text": text, "upto": upto}
    try:
        if not isinstance(text, str) or not text.strip() or not is_storable(text):
            raise ValueError(f"text must be text of 1 to {MAX_TEXT} characters")
        params = {"session": _session(user, session_id), "text": text, "by": by, "now": now()}
        params["upto"] = whole_number(upto, "upto", 2**62)
        rows = graph.query(SUM, params).result_set
    except ValueError as exc:
        return refuse(graph, "Summary", session_id, "invalid", str(exc), content, user)
    except ResponseError as exc:
        return refuse(graph, "Summary", session_id, "failed", str(exc), content, user)
    status = rows[0][0] if rows else "unknown"
    if status != "summed":
        return refuse(graph, "Summary", session_id, status, REFUSED[status], content, user)
    return {"id": session_id, "upto": upto, "status": status}


def context(graph: Graph, user: str, session_id: str, last: int = 20) -> dict:
    """What a model needs to go on with a session: {"summary", "upto", "messages", "waiting"}.

      summary   what the messages up to number "upto" come to, or None
      messages  the messages after those, oldest first, at most `last`
      waiting   how many messages are in neither. Above 0, it is time to sum up again

    A session that the user does not have gives an empty context.
    """
    named(user=user, session_id=session_id)
    whole_number(last, "last", 1_000)
    rows = graph.ro_query(
        "MATCH (s:Session {key: $session}) "
        "RETURN s.summary, coalesce(s.summary_upto, 0), s.message_count",
        {"session": _session(user, session_id)},
    ).result_set
    summary, upto, held = rows[0] if rows else (None, 0, 0)
    fresh = held - upto  # messages that the summary does not hold
    shown = messages(graph, user, session_id, min(last, fresh)) if fresh > 0 else []
    return {
        "summary": summary,
        "upto": upto,
        "messages": shown,
        "waiting": max(0, fresh - last),
    }


def _forget_failures(graph: Graph, user: str, session_id=None) -> None:
    params = {"user": user, "id": session_id, "batch": BATCH}
    while graph.query(FAILURES, params).result_set[0][0]:
        pass


def forget_session(graph: Graph, user: str, session_id: str) -> dict:
    """Delete one session of `user`: its messages, its summary, the references that nothing
    else mentions, and what was kept of its refused messages.

    Returns {"id", "status", "messages"}: status "forgotten" with the number of messages
    that were deleted, or "unknown" when the user has no such session.

    Messages that are said while this runs are deleted with the rest. One that is said
    after the session is gone opens it again.
    """
    named(user=user, session_id=session_id)
    params = {"session": _session(user, session_id), "batch": BATCH}
    found, gone, left = False, 0, 1
    while left > 0:
        rows = graph.query(FORGET, params).result_set
        if not rows:
            break  # no such session, or it went with its last message
        found, (deleted, left, mentioned) = True, rows[0]
        gone += deleted
        for start in range(0, len(mentioned), BATCH):
            graph.query(ORPHANS, {"keys": mentioned[start : start + BATCH]})
    _forget_failures(graph, user, session_id)
    return {"id": session_id, "status": "forgotten" if found else "unknown", "messages": gone}


def forget_user(graph: Graph, user: str) -> dict:
    """Delete everything `user` said in this graph: every session, as forget_session()
    does, and what was kept of every refused message. Returns {"user", "sessions",
    "messages"} with how many were deleted."""
    count, gone = 0, 0
    while found := sessions(graph, user, limit=100):
        for session in found:
            gone += forget_session(graph, user, session["id"])["messages"]
        count += len(found)
    _forget_failures(graph, user)
    return {"user": user, "sessions": count, "messages": gone}
