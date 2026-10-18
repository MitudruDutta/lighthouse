"""Recall by text: entities, past States, and entries whose text has the words of a question.

The indexes are FalkorDB's full-text indexes, on the `words` that a node keeps of its text
(values.indexed()). The one of a kind holds the current text of its entities: a value that
changed is found by its new words only. The one of States holds every version, so
search_history() finds what an entity said at any time. Entries and messages keep the words
of their values and text in the same way.

The question is never sent as it is. The index has a query language of its own (`*`, `-`,
`|`, `@field:`, `"..."`), and a question in that language could list every entity or fail.
Only the words of the question are sent.
"""

from falkordb import Graph

from lighthouse.kinds import Kind
from lighthouse.read import READ_TIMEOUT, version
from lighthouse.values import WORD, without_words

MAX_QUESTION = 1_000  # characters of a question that are read
MAX_WORDS = 20  # words of a question that are used
MAX_WORD = 50  # characters of one word


def words(question: str) -> list[str]:
    """The words of a question, in lower case, without doubles: letters and digits only."""
    found = WORD.findall(question[:MAX_QUESTION].lower())
    return list(dict.fromkeys(word[:MAX_WORD] for word in found))[:MAX_WORDS]


def _terms(question, limit, match) -> list[str]:
    """The words of a question, after the checks every search makes."""
    if not isinstance(question, str):
        raise TypeError("question must be text")
    if match not in ("all", "any"):
        raise ValueError('match must be "all" or "any"')
    if type(limit) is not int or not 1 <= limit <= 1_000:
        raise ValueError("limit must be a whole number from 1 to 1000")
    return words(question)


def _join(terms: list[str], match: str) -> str:
    return (" " if match == "all" else "|").join(terms)


def search(
    graph: Graph, kind: Kind, question: str, limit: int = 10, match: str = "all"
) -> list[dict]:
    """Entities of `kind` whose text has the words of `question`, best first:
    [{"key", "score", "values"}]. "values" holds the current values of the entity.

      match  "all": every word must be there. "any": one word is enough.

    Words are matched whole and in their base form: "sensors" finds "sensor". A question
    without a letter or digit finds nothing.
    """
    _searchable(kind)
    terms = _terms(question, limit, match)
    if not terms:
        return []
    query = (
        f"CALL db.idx.fulltext.queryNodes('{kind.label}', $terms) YIELD node, score "
        f"RETURN node, score ORDER BY score DESC, node.{kind.key} LIMIT $limit"
    )
    params = {"terms": _join(terms, match), "limit": limit}
    rows = graph.ro_query(query, params, timeout=READ_TIMEOUT).result_set
    return [
        {
            "key": node.properties[kind.key],
            "score": score,
            "values": without_words({k: v for k, v in node.properties.items() if k != kind.key}),
        }
        for node, score in rows
    ]


def _searchable(kind: Kind) -> None:
    if not kind.text:
        raise ValueError(
            f"{kind.label} has no text to search: name the properties in Kind(text=...)"
        )


def search_history(
    graph: Graph, kind: Kind, question: str, limit: int = 10, match: str = "all"
) -> list[dict]:
    """States of entities of `kind` whose text had the words of `question`, the current one
    or an earlier one, best first: [{"key", "score", "state"}]. "state" is the State as
    history() gives it, with its validity window.

    Words are matched as search() matches them.
    """
    _searchable(kind)
    terms = _terms(question, limit, match)
    if not terms:
        return []
    # States of every kind share one index. A State counts only when an entity of this kind
    # has it.
    query = (
        "CALL db.idx.fulltext.queryNodes('State', $terms) YIELD node AS s, score "
        f"MATCH (e:{kind.label})-[:HAS_STATE]->(s) "
        f"WITH e, s, score ORDER BY score DESC, e.{kind.key}, s.valid_from LIMIT $limit "
        "OPTIONAL MATCH (s)-[:FROM]->(n:Entry) "
        f"RETURN s, n.id, e.{kind.key}, score ORDER BY score DESC, e.{kind.key}, s.valid_from"
    )
    params = {"terms": _join(terms, match), "limit": limit}
    rows = graph.ro_query(query, params, timeout=READ_TIMEOUT).result_set
    return [
        {"key": key, "score": score, "state": version(s, entry)} for s, entry, key, score in rows
    ]


def search_entries(graph: Graph, question: str, limit: int = 10, match: str = "all") -> list[dict]:
    """Entries of episodes whose values had the words of `question`, best first:
    [{"id", "score", "entry"}]. "entry" holds the properties of the entry, as episode()
    gives them, without its evidence."""
    terms = _terms(question, limit, match)
    if not terms:
        return []
    query = (
        "CALL db.idx.fulltext.queryNodes('Entry', $terms) YIELD node, score "
        "RETURN node, score ORDER BY score DESC, node.id LIMIT $limit"
    )
    params = {"terms": _join(terms, match), "limit": limit}
    rows = graph.ro_query(query, params, timeout=READ_TIMEOUT).result_set
    return [
        {"id": node.properties["id"], "score": score, "entry": without_words(node.properties)}
        for node, score in rows
    ]
