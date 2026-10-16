"""Recall by meaning: entities whose text is close to a question, by vectors.

The library has no model. The application passes in the function that turns texts into
vectors, and names the model, so vectors of two models are never compared. What the
function returns is checked like any other input.

Vectors are made off the write path, by embed(). A vector belongs to the text it was made
from: the write that changes the text takes the vector out of the index and gives the
entity the label ThingToEmbed, and embed() makes a new one. embed() reads only entities
with that label, so a call costs what waits, not what the kind holds. A vector is stored
only if the text is still what it was made from.

Entries never change. embed_entries() reads the entries stored since its mark, by their
serial, so a call costs what came since.

  (entity)-[:EMBEDDED_AS]->(ThingVector {vector, model, at})
  (Entry)-[:EMBEDDED_AS]->(EntryVector {vector, model, at})

An entry never changes, so its vector stands for its text for good. Entries get vectors only
in a graph whose schema gives them an index: ensure_schema(..., entry_dimensions=N).
"""

import hashlib
import math

from falkordb import Graph

from lighthouse.clock import now
from lighthouse.episodes import ENTRY_PROPERTIES
from lighthouse.graphs import entries_after, entries_waiting, mark, set_mark
from lighthouse.kinds import TO_EMBED, VECTOR, Kind
from lighthouse.read import READ_TIMEOUT
from lighthouse.values import MAX_TEXT, describe, named, without_words

BATCH = 50  # vectors in one write query
MARK_PAGE = 10_000  # entities marked in one write, after a change of model
MOST = 1_000  # vectors that one search reads at most


def text_of(kind: Kind, values: dict) -> str:
    """The text of an entity that its vector stands for: its text values, one per line."""
    parts = (values.get(name) for name in kind.text)
    return "\n".join(part for part in parts if isinstance(part, str) and part.strip())


def vectors(embedder, texts: list[str], dimensions: int) -> list[list[float]]:
    """Call the application's function, and trust nothing it gives back: one vector for
    each text, each of the declared size, each of finite numbers, none of length zero."""
    made = embedder(list(texts))
    if not isinstance(made, (list, tuple)) or len(made) != len(texts):
        raise ValueError(f"the embedder must give one vector for each text, got {describe(made)}")
    checked = []
    for vector in made:
        if not isinstance(vector, (list, tuple)) or len(vector) != dimensions:
            raise ValueError(f"the embedder must give vectors of {dimensions} numbers")
        if not all(type(x) in (int, float) and math.isfinite(x) for x in vector):
            raise ValueError("the embedder gave a vector with something that is not a number")
        if not any(vector):
            raise ValueError("the embedder gave a vector of zeros")
        checked.append([float(x) for x in vector])
    return checked


def _ready(kind: Kind, embedder, model: str, limit: int) -> None:
    if not kind.dimensions:
        raise ValueError(f"{kind.label} has no vectors: set Kind(text=..., dimensions=...)")
    _checked(embedder, model, limit)


def _checked(embedder, model: str, limit: int) -> None:
    if not callable(embedder):
        raise TypeError("embedder must be a function from a list of texts to a list of vectors")
    named(model=model)
    if type(limit) is not int or not 1 <= limit <= 1_000:
        raise ValueError("limit must be a whole number from 1 to 1000")


def _digest(name: str) -> str:
    """A short name for a mark, from any text: a model may be named anything."""
    return hashlib.sha256(name.encode()).hexdigest()[:16]


def _all_wait(graph: Graph, kind: Kind, model: str) -> None:
    """After a change of model, every entity with text waits for a vector of the new one:
    one pass over the kind, once for each change. So does every entity of a graph that was
    written before entities waited by label."""
    name = f"embedded_{kind.label}"
    if mark(graph, name) == _digest(model):
        return
    waits = f"{kind.label}{TO_EMBED}"
    worded = " OR ".join(f"e.{text} IS NOT NULL" for text in kind.text)
    # A write blocks every other writer of the graph, so the labels go on a page at a time.
    while graph.query(
        f"MATCH (e:{kind.label}) WHERE ({worded}) AND NOT e:{waits} "
        f"WITH e LIMIT {MARK_PAGE} SET e:{waits} RETURN count(e)"
    ).result_set[0][0]:
        pass
    set_mark(graph, name, _digest(model))


def embed(graph: Graph, kind: Kind, embedder, model: str, limit: int = 100) -> dict:
    """Give a vector to entities of `kind` whose text has none, or whose text or model has
    changed since. At most `limit` in one call. Returns {"embedded", "waiting"}: how many
    got a vector now, and how many still wait. Run it off the write path until none wait.

    `embedder` takes a list of texts and returns one vector for each, of kind.dimensions
    numbers. `model` names what made them. A call with another model than the last one
    reads the kind once, to give every entity with text a vector of the new model.
    """
    _ready(kind, embedder, model, limit)
    label = f"{kind.label}{VECTOR}"
    waits = f"{kind.label}{TO_EMBED}"
    _all_wait(graph, kind, model)
    rows = graph.ro_query(
        f"MATCH (e:{waits}) OPTIONAL MATCH (e)-[:EMBEDDED_AS]->(v:{label}) "
        f"RETURN e, v.model, v.vector IS NOT NULL ORDER BY e.{kind.key} LIMIT $limit",
        {"limit": limit},
    ).result_set
    chosen, done = [], []
    for entity, made_by, has_vector in rows:
        values = entity.properties
        if text_of(kind, values) and not (has_vector and made_by == model):
            chosen.append(values)
        else:  # no text to stand for, or a vector of this model already: nothing to make
            done.append(values)
    # The model was asked outside any query. A text that changed in the meantime gets no
    # vector here, and keeps its label: the vector would stand for words it no longer has.
    same = " AND ".join(f"coalesce(e.{name}, '') = r.text.{name}" for name in kind.text)

    def text(values: dict) -> dict:
        return {name: values.get(name, "") for name in kind.text}

    if done:
        graph.query(
            f"UNWIND $rows AS r MATCH (e:{waits} {{{kind.key}: r.key}}) WHERE {same} "
            f"REMOVE e:{waits}",
            {"rows": [{"key": values[kind.key], "text": text(values)} for values in done]},
        )
    written = 0
    if chosen:
        texts = [text_of(kind, values)[:MAX_TEXT] for values in chosen]
        fresh = [
            {"key": values[kind.key], "vector": vector, "text": text(values)}
            for values, vector in zip(chosen, vectors(embedder, texts, kind.dimensions))
        ]
        for start in range(0, len(fresh), BATCH):
            result = graph.query(
                f"UNWIND $rows AS r MATCH (e:{kind.label} {{{kind.key}: r.key}}) WHERE {same} "
                f"MERGE (e)-[:EMBEDDED_AS]->(v:{label}) "
                "SET v.vector = vecf32(r.vector), v.model = $model, v.at = localdatetime($now) "
                f"REMOVE e:{waits} RETURN count(v)",
                {"rows": fresh[start : start + BATCH], "model": model, "now": now()},
            )
            written += result.result_set[0][0]
    waiting = graph.ro_query(f"MATCH (e:{waits}) RETURN count(e)").result_set[0][0]
    return {"embedded": written, "waiting": waiting}


def nearest(
    graph: Graph, kind: Kind, question: str, embedder, model: str, limit: int = 10
) -> list[dict]:
    """Entities of `kind` whose text is closest in meaning to `question`, closest first:
    [{"key", "score", "values"}]. The score is the cosine similarity: 1 for the same
    direction, 0 for none in common.

    An entity whose text changed after its vector was made is left out until embed() runs
    again. So is a vector of another model. A question without text finds nothing.
    At most 1,000 vectors are read: after a change of model, run embed() to the end first.
    """
    _ready(kind, embedder, model, limit)
    vector = _question(question, embedder, kind.dimensions)
    found = _closest(graph, f"{kind.label}{VECTOR}", kind.label, kind.key, vector, model, limit)
    return [
        {
            "key": entity.properties[kind.key],
            "score": score,
            "values": without_words({n: v for n, v in entity.properties.items() if n != kind.key}),
        }
        for entity, score in found
    ]


def _question(question, embedder, dimensions: int) -> list[float] | None:
    """The vector of a question, or None for a question without text."""
    if not isinstance(question, str):
        raise TypeError("question must be text")
    if not question.strip():
        return None
    (vector,) = vectors(embedder, [question[:MAX_TEXT]], dimensions)
    return vector


def _closest(graph: Graph, index: str, label: str, key: str, vector, model: str, limit: int):
    """The nodes with the label whose vectors of this model are closest to `vector`: [(node,
    similarity)]. The similarity is 1 minus the cosine distance that the index gives."""
    if vector is None:
        return []
    # Vectors of another model share the index until they are replaced. They are read and
    # left out, so the search widens until it has enough or has read them all.
    k = limit
    while True:
        rows = graph.ro_query(
            f"CALL db.idx.vector.queryNodes('{index}', 'vector', $k, vecf32($q)) "
            f"YIELD node, score MATCH (node)<-[:EMBEDDED_AS]-(o:{label}) "
            f"RETURN o, node.model, score ORDER BY score, o.{key}",
            {"k": k, "q": vector},
            timeout=READ_TIMEOUT,
        ).result_set
        found = [(owner, 1 - distance) for owner, made_by, distance in rows if made_by == model]
        if len(found) >= limit or len(rows) < k or k >= MOST:
            return found[:limit]
        k = min(k * 4, MOST)


ENTRY_VECTOR = "EntryVector"


def entry_text(entry: dict) -> str:
    """The text of an entry that its vector stands for: its text values in the order of their
    names, one per line. A list of texts counts as its texts."""
    parts = []
    for name in sorted(set(entry) - ENTRY_PROPERTIES):
        value = entry[name]
        parts += value if isinstance(value, list) else [value]
    return "\n".join(part for part in parts if isinstance(part, str) and part.strip())


def _entry_dimensions(graph: Graph) -> int:
    found = graph.ro_query(
        "CALL db.indexes() YIELD label, options WHERE label = $label RETURN options.vector.dimension",
        {"label": ENTRY_VECTOR},
    ).result_set
    if not found:
        raise ValueError(
            "entries have no vector index: call ensure_schema(..., entry_dimensions=N)"
        )
    return found[0][0]


def _ready_for_entries(graph: Graph, embedder, model: str, limit: int) -> int:
    _checked(embedder, model, limit)
    return _entry_dimensions(graph)


# Entries with text that have no vector of this model. Entries without text have none.
WAITING = f"n.words IS NOT NULL AND NOT (n)-[:EMBEDDED_AS]->(:{ENTRY_VECTOR} {{model: $model}})"


def embed_entries(graph: Graph, embedder, model: str, limit: int = 100) -> dict:
    """Give a vector to entries whose text has none of this model, at most `limit` in one
    call, in the order they were stored. Returns {"embedded", "waiting"}, as embed() does.
    Run it off the write path until none wait.

    It reads the entries stored since its mark for this model: a model it has not seen
    starts from the first entry."""
    dimensions = _ready_for_entries(graph, embedder, model, limit)
    name = f"embedded_entries_{_digest(model)}"
    params = {"model": model}
    chosen, done = entries_after(graph, name, WAITING, params, limit)
    entries = [node.properties for node in chosen]
    if entries:
        texts = [entry_text(entry)[:MAX_TEXT] for entry in entries]
        made = vectors(embedder, texts, dimensions)
        rows = [{"id": entry["id"], "vector": v} for entry, v in zip(entries, made)]
        for start in range(0, len(rows), BATCH):
            graph.query(
                f"UNWIND $rows AS r MATCH (n:Entry {{id: r.id}}) "
                f"MERGE (n)-[:EMBEDDED_AS]->(v:{ENTRY_VECTOR}) "
                "SET v.vector = vecf32(r.vector), v.model = $model, v.at = localdatetime($now)",
                {"rows": rows[start : start + BATCH], "model": model, "now": now()},
            )
    set_mark(graph, name, done)
    return {"embedded": len(entries), "waiting": entries_waiting(graph, done, WAITING, params)}


def nearest_entries(graph: Graph, question: str, embedder, model: str, limit: int = 10) -> list:
    """Entries whose text is closest in meaning to `question`, closest first:
    [{"id", "score", "entry"}], with the score as nearest() gives it. Vectors of another
    model are left out, and at most 1,000 vectors are read."""
    dimensions = _ready_for_entries(graph, embedder, model, limit)
    vector = _question(question, embedder, dimensions)
    found = _closest(graph, ENTRY_VECTOR, "Entry", "id", vector, model, limit)
    return [
        {"id": entry.properties["id"], "score": score, "entry": without_words(entry.properties)}
        for entry, score in found
    ]
