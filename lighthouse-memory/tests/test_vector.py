"""Recall by meaning, with an embedder that the test passes in. The library has no model."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import connect
from devices import DEVICE, MANUAL, count, when

from lighthouse import (
    embed,
    embed_entries,
    ensure_schema,
    nearest,
    nearest_entries,
    open_episode,
    record,
    remember,
)
from lighthouse.recall.vector import entry_text
from lighthouse.values import MAX_TEXT

VOCABULARY = ("pump", "seal", "valve", "service", "tank", "coolant", "glove", "safety")


class Embedder:
    """Counts eight words. Good enough to tell texts apart, and it records what it was asked."""

    def __init__(self):
        self.asked = []

    def __call__(self, texts):
        self.asked.append(list(texts))
        return [[float(text.lower().count(word)) for word in VOCABULARY] for text in texts]


def manual(code, title, body, minute=0, pages=10) -> dict:
    return {
        "key": code,
        "t": when(minute),
        "values": {"title": title, "body": body, "pages": pages},
    }


@pytest.fixture
def graph(graph):
    rows = [
        manual("m1", "Pump service", "Check the seal of the pump. Replace a worn seal."),
        manual("m2", "Valve service", "Close the valve before service. The pump must be off."),
        manual("m3", "Cooling tanks", "Tankers deliver coolant."),
        manual("m4", "Safety", "Wear gloves."),
        {"key": "m5", "t": when(0), "values": {"pages": 3}},  # no text at all
    ]
    assert {r["status"] for r in remember(graph, MANUAL, rows, by="library")} == {"created"}
    return graph


def keys(found) -> list:
    return [item["key"] for item in found]


# --- making vectors -------------------------------------------------------------------


def test_embed_gives_a_vector_to_every_entity_with_text(graph):
    embedder = Embedder()
    assert embed(graph, MANUAL, embedder, model="count-8") == {"embedded": 4, "waiting": 0}
    assert embedder.asked == [
        [
            "Pump service\nCheck the seal of the pump. Replace a worn seal.",
            "Valve service\nClose the valve before service. The pump must be off.",
            "Cooling tanks\nTankers deliver coolant.",
            "Safety\nWear gloves.",
        ]
    ]
    stored = graph.ro_query(
        "MATCH (m:Manual)-[:EMBEDDED_AS]->(v:ManualVector) "
        "RETURN m.code, v.vector, v.model ORDER BY m.code"
    ).result_set
    assert stored[0] == ["m1", [2.0, 2.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0], "count-8"]
    assert [row[0] for row in stored] == ["m1", "m2", "m3", "m4"]  # m5 has no text


def test_embed_again_does_nothing(graph):
    embedder = Embedder()
    embed(graph, MANUAL, embedder, model="count-8")
    assert embed(graph, MANUAL, embedder, model="count-8") == {"embedded": 0, "waiting": 0}
    assert len(embedder.asked) == 1 and count(graph, "(v:ManualVector)") == 4


def test_embed_takes_a_limited_number_in_one_call(graph):
    embedder = Embedder()
    assert embed(graph, MANUAL, embedder, model="count-8", limit=3) == {"embedded": 3, "waiting": 1}
    assert embed(graph, MANUAL, embedder, model="count-8", limit=3) == {"embedded": 1, "waiting": 0}
    assert [len(batch) for batch in embedder.asked] == [3, 1]


def test_many_vectors_are_written_in_several_queries(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.recall.vector.BATCH", 3)
    assert embed(graph, MANUAL, Embedder(), model="count-8") == {"embedded": 4, "waiting": 0}
    assert count(graph, "(:Manual)-[e:EMBEDDED_AS]->(:ManualVector)", "e") == 4


def test_two_jobs_at_once_leave_one_vector_for_each_entity(graph):
    def job():
        return embed(connect().select_graph(graph.name), MANUAL, Embedder(), model="count-8")

    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in [pool.submit(job) for _ in range(4)]:
            future.result()
    assert count(graph, "(v:ManualVector)") == 4
    assert count(graph, "(:Manual)-[e:EMBEDDED_AS]->(:ManualVector)", "e") == 4


# --- finding by meaning ---------------------------------------------------------------


def test_nearest_ranks_by_meaning_and_gives_the_similarity(graph):
    embedder = Embedder()
    embed(graph, MANUAL, embedder, model="count-8")
    found = nearest(graph, MANUAL, "The seal of my pump leaks", embedder, model="count-8")
    assert keys(found) == ["m1", "m2", "m3", "m4"]
    assert found[0]["score"] == pytest.approx(
        4 / (3 * 2**0.5), abs=1e-4
    )  # cosine of the two vectors
    assert found[1]["score"] == pytest.approx(1 / (3 * 2**0.5), abs=1e-4)
    assert found[2]["score"] == pytest.approx(0, abs=1e-4)
    assert found[0]["values"]["title"] == "Pump service" and "code" not in found[0]["values"]
    assert "words" not in found[0]["values"]  # the words are for the index only
    assert embedder.asked[-1] == ["The seal of my pump leaks"]
    assert keys(nearest(graph, MANUAL, "safety gloves", embedder, model="count-8", limit=1)) == [
        "m4"
    ]


def test_entity_without_a_vector_is_not_found(graph):
    embedder = Embedder()
    assert nearest(graph, MANUAL, "pump", embedder, model="count-8") == []
    embed(graph, MANUAL, embedder, model="count-8", limit=1)
    assert keys(nearest(graph, MANUAL, "pump", embedder, model="count-8")) == ["m1"]


def test_text_that_changed_is_left_out_until_it_has_a_new_vector(graph):
    embedder = Embedder()
    embed(graph, MANUAL, embedder, model="count-8")
    remember(
        graph, MANUAL, [manual("m1", "Glove care", "Wash a glove after use.", minute=5)], by="x"
    )
    found = nearest(graph, MANUAL, "pump seal", embedder, model="count-8")
    assert "m1" not in keys(found)  # its vector still says pump and seal; the text does not
    assert embed(graph, MANUAL, embedder, model="count-8") == {"embedded": 1, "waiting": 0}
    assert keys(nearest(graph, MANUAL, "glove", embedder, model="count-8"))[0] == "m1"
    assert count(graph, "(v:ManualVector)") == 4  # the vector was replaced, not added


def test_vector_leaves_the_index_in_the_write_that_changes_the_text(graph):
    embedder = Embedder()
    embed(graph, MANUAL, embedder, model="count-8")
    remember(graph, MANUAL, [manual("m1", "Pump service", "Other words.", minute=5)], by="x")
    indexed = graph.ro_query(
        "MATCH (m:Manual)-[:EMBEDDED_AS]->(v:ManualVector) WHERE v.vector IS NOT NULL RETURN m.code ORDER BY m.code"
    ).result_set
    assert indexed == [["m2"], ["m3"], ["m4"]]  # only the body of m1 changed: that is enough
    assert count(graph, "(v:ManualVector)") == 4  # the node waits for the next vector


def test_text_that_changes_while_the_model_works_gets_no_vector(graph):
    # The model is asked outside any query. If the text changes in that time, the vector
    # that comes back stands for words the entity no longer has.
    def slow(texts):
        row = manual("m1", "Glove care", "Wash a glove after use.", minute=5)
        remember(graph, MANUAL, [row], by="x")
        return Embedder()(texts)

    assert embed(graph, MANUAL, slow, model="count-8") == {"embedded": 3, "waiting": 1}
    embedder = Embedder()
    assert "m1" not in keys(nearest(graph, MANUAL, "pump seal", embedder, model="count-8"))
    assert embed(graph, MANUAL, embedder, model="count-8") == {"embedded": 1, "waiting": 0}
    assert keys(nearest(graph, MANUAL, "glove", embedder, model="count-8"))[0] == "m1"


def test_change_of_a_value_that_is_not_text_keeps_the_vector(graph):
    embedder = Embedder()
    embed(graph, MANUAL, embedder, model="count-8")
    row = manual(
        "m1", "Pump service", "Check the seal of the pump. Replace a worn seal.", minute=5, pages=99
    )
    assert remember(graph, MANUAL, [row], by="x")[0]["status"] == "changed"
    assert embed(graph, MANUAL, embedder, model="count-8") == {"embedded": 0, "waiting": 0}
    found = nearest(graph, MANUAL, "pump seal", embedder, model="count-8")
    assert keys(found)[0] == "m1" and found[0]["values"]["pages"] == 99


def test_vectors_of_another_model_are_never_compared(graph):
    old, new = Embedder(), Embedder()
    embed(graph, MANUAL, old, model="count-8")
    assert nearest(graph, MANUAL, "pump", new, model="count-9") == []
    assert embed(graph, MANUAL, new, model="count-9", limit=2) == {"embedded": 2, "waiting": 2}
    assert keys(nearest(graph, MANUAL, "pump", new, model="count-9")) == ["m1", "m2"]
    assert sorted(keys(nearest(graph, MANUAL, "pump", old, model="count-8"))) == ["m3", "m4"]
    assert count(graph, "(v:ManualVector)") == 4


def test_many_vectors_of_another_model_do_not_hide_the_good_ones(graph):
    old, new = Embedder(), Embedder()
    remember(
        graph,
        MANUAL,
        [manual(f"x{n}", "Pump seal pump seal", "pump seal") for n in range(30)],
        by="x",
    )
    embed(graph, MANUAL, old, model="count-8")
    embed(graph, MANUAL, new, model="count-9", limit=4)  # m1 to m4 come first by key
    # 30 vectors of the old model are nearer to the question than m1 is.
    assert keys(nearest(graph, MANUAL, "pump seal", new, model="count-9", limit=1)) == ["m1"]
    assert keys(nearest(graph, MANUAL, "pump seal", new, model="count-9", limit=2)) == ["m1", "m2"]


def test_search_reads_a_bounded_number_of_vectors(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.recall.vector.MOST", 8)
    old, new = Embedder(), Embedder()
    remember(
        graph,
        MANUAL,
        [manual(f"x{n}", "Pump seal pump seal", "pump seal") for n in range(30)],
        by="x",
    )
    embed(graph, MANUAL, old, model="count-8")
    embed(graph, MANUAL, new, model="count-9", limit=4)
    asked = []
    real = graph.ro_query
    graph.ro_query = lambda query, params=None, **more: (
        (asked.append(params["k"]) if params and "k" in params else None)
        or real(query, params, **more)
    )
    try:
        assert nearest(graph, MANUAL, "pump seal", new, model="count-9", limit=2) == []
    finally:
        del graph.ro_query
    assert asked == [2, 8]  # wider once, then the bound


def test_many_stale_vectors_do_not_hide_the_good_ones(graph):
    embedder = Embedder()
    rows = [manual(f"x{n}", "Pump seal pump seal", "pump seal") for n in range(30)]
    remember(graph, MANUAL, rows, by="x")
    embed(graph, MANUAL, embedder, model="count-8")
    stale = [manual(f"x{n}", "Other", "nothing", minute=5) for n in range(30)]
    remember(graph, MANUAL, stale, by="x")  # 30 vectors nearer than m1 now stand for old text
    assert keys(nearest(graph, MANUAL, "pump seal", embedder, model="count-8", limit=1)) == ["m1"]


def test_question_without_text_finds_nothing_and_asks_no_model(graph):
    embedder = Embedder()
    embed(graph, MANUAL, embedder, model="count-8")
    asked = len(embedder.asked)
    assert nearest(graph, MANUAL, "", embedder, model="count-8") == []
    assert nearest(graph, MANUAL, "  \n ", embedder, model="count-8") == []
    assert len(embedder.asked) == asked


def test_long_question_is_cut_before_the_model_sees_it(graph):
    embedder = Embedder()
    embed(graph, MANUAL, embedder, model="count-8")
    nearest(graph, MANUAL, "pump " * 1_000_000, embedder, model="count-8")
    assert len(embedder.asked[-1][0]) == MAX_TEXT


# --- what the embedder gives back is not trusted --------------------------------------

GOOD = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
BAD_ANSWERS = {
    "nothing": lambda texts: None,
    "text": lambda texts: "vectors",
    "too few vectors": lambda texts: [GOOD] * (len(texts) - 1),
    "too many vectors": lambda texts: [GOOD] * (len(texts) + 1),
    "a vector too short": lambda texts: [GOOD[:7]] * len(texts),
    "a vector too long": lambda texts: [[*GOOD, 0.0]] * len(texts),
    "a vector that is text": lambda texts: ["12345678"] * len(texts),
    "a vector that is a map": lambda texts: [dict(enumerate(GOOD))] * len(texts),
    "not a number": lambda texts: [[float("nan"), *GOOD[1:]]] * len(texts),
    "infinity": lambda texts: [[float("inf"), *GOOD[1:]]] * len(texts),
    "text in a vector": lambda texts: [["1", *GOOD[1:]]] * len(texts),
    "nothing in a vector": lambda texts: [[None, *GOOD[1:]]] * len(texts),
    "a boolean in a vector": lambda texts: [[True, *GOOD[1:]]] * len(texts),
    "a list in a vector": lambda texts: [[[1.0], *GOOD[1:]]] * len(texts),
    "only zeros": lambda texts: [[0.0] * 8] * len(texts),
    "a generator": lambda texts: (GOOD for _ in texts),
}


@pytest.mark.parametrize("name", BAD_ANSWERS)
def test_bad_answer_of_the_embedder_is_refused_and_nothing_is_stored(graph, name):
    with pytest.raises(ValueError, match="embedder"):
        embed(graph, MANUAL, BAD_ANSWERS[name], model="count-8")
    assert count(graph, "(v:ManualVector)") == 0
    embed(graph, MANUAL, Embedder(), model="count-8")
    with pytest.raises(ValueError, match="embedder"):
        nearest(graph, MANUAL, "pump", BAD_ANSWERS[name], model="count-8")


def test_whole_numbers_are_taken_as_numbers(graph):
    assert embed(
        graph, MANUAL, lambda texts: [[1, 0, 0, 0, 0, 0, 0, 2]] * len(texts), model="ints"
    ) == {
        "embedded": 4,
        "waiting": 0,
    }
    stored = graph.ro_query("MATCH (v:ManualVector) RETURN v.vector LIMIT 1").result_set
    assert stored[0][0] == [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0]


def test_embedder_that_fails_stores_nothing(graph):
    def broken(texts):
        raise ConnectionError("the model is away")

    with pytest.raises(ConnectionError):
        embed(graph, MANUAL, broken, model="count-8")
    assert count(graph, "(v:ManualVector)") == 0


def test_embedder_cannot_change_what_the_library_holds(graph):
    def greedy(texts):
        vectors = [[1.0] + [0.0] * 7 for _ in texts]
        texts.clear()  # the list it was given is a copy
        return vectors

    assert embed(graph, MANUAL, greedy, model="count-8") == {"embedded": 4, "waiting": 0}
    assert count(graph, "(v:ManualVector)") == 4


# --- what is refused ------------------------------------------------------------------


def test_kind_without_dimensions_has_no_vectors(graph):
    for call in (
        lambda: embed(graph, DEVICE, Embedder(), model="count-8"),
        lambda: nearest(graph, DEVICE, "pump", Embedder(), model="count-8"),
    ):
        with pytest.raises(ValueError, match="no vectors"):
            call()


@pytest.mark.parametrize("embedder", [None, "model", 7, [1.0], {"a": 1}])
def test_embedder_must_be_a_function(graph, embedder):
    with pytest.raises(TypeError, match="embedder"):
        embed(graph, MANUAL, embedder, model="count-8")
    with pytest.raises(TypeError, match="embedder"):
        nearest(graph, MANUAL, "pump", embedder, model="count-8")


@pytest.mark.parametrize("model", [None, "", 7, "a\x00b", " padded ", "x" * 201])
def test_model_must_have_a_name(graph, model):
    with pytest.raises(ValueError, match="model"):
        embed(graph, MANUAL, Embedder(), model=model)
    with pytest.raises(ValueError, match="model"):
        nearest(graph, MANUAL, "pump", Embedder(), model=model)


@pytest.mark.parametrize("limit", [0, -1, 1001, 1.5, "10", None, True])
def test_limit_of_a_wrong_form_is_refused(graph, limit):
    with pytest.raises(ValueError, match="limit"):
        embed(graph, MANUAL, Embedder(), model="count-8", limit=limit)
    with pytest.raises(ValueError, match="limit"):
        nearest(graph, MANUAL, "pump", Embedder(), model="count-8", limit=limit)


@pytest.mark.parametrize("question", [None, 7, ["pump"], b"pump"])
def test_question_that_is_not_text_is_refused(graph, question):
    with pytest.raises(TypeError, match="question"):
        nearest(graph, MANUAL, question, Embedder(), model="count-8")


# --- entries -----------------------------------------------------------------------------


@pytest.fixture
def notes(graph):
    """Entries with text, in a graph whose entries have an index of eight dimensions."""
    ensure_schema(graph, [DEVICE, MANUAL], entry_dimensions=8)
    open_episode(graph, "leak", "eye")
    for values in (
        {"saw": "oil under the pump", "litres": 3},
        {"steps": ["closed the valve", "called service"]},
        {"litres": 4},  # no text: no vector
        {"saw": "a torn glove", "note": "safety first"},
    ):
        assert record(graph, "leak", "observation", "eye", values)["status"] == "recorded"
    return graph


def ids(found) -> list:
    return [item["id"] for item in found]


def test_entries_get_vectors_and_are_found_by_meaning(notes):
    embedder = Embedder()
    assert embed_entries(notes, embedder, "words-v1", limit=2) == {"embedded": 2, "waiting": 1}
    assert embed_entries(notes, embedder, "words-v1") == {"embedded": 1, "waiting": 0}
    assert embed_entries(notes, embedder, "words-v1") == {"embedded": 0, "waiting": 0}
    assert embedder.asked[0] == ["oil under the pump", "closed the valve\ncalled service"]
    found = nearest_entries(notes, "the pump", embedder, "words-v1")
    assert ids(found)[0] == "leak/1" and found[0]["score"] == pytest.approx(1.0)
    assert "words" not in found[0]["entry"] and found[0]["entry"]["saw"] == "oil under the pump"
    assert ids(nearest_entries(notes, "glove safety", embedder, "words-v1", limit=1)) == ["leak/4"]
    assert count(notes, "(v:EntryVector)") == 3


def test_entry_vectors_of_another_model_are_not_used(notes):
    embed_entries(notes, Embedder(), "words-v1")
    assert nearest_entries(notes, "pump", Embedder(), "words-v2") == []
    assert embed_entries(notes, Embedder(), "words-v2") == {"embedded": 3, "waiting": 0}
    assert ids(nearest_entries(notes, "pump", Embedder(), "words-v2", limit=1)) == ["leak/1"]
    assert count(notes, "(v:EntryVector)") == 3  # one vector for each entry, of the new model


def test_entries_have_no_vectors_without_an_index(graph):
    with pytest.raises(ValueError, match="entry_dimensions"):
        embed_entries(graph, Embedder(), "words-v1")
    with pytest.raises(ValueError, match="entry_dimensions"):
        nearest_entries(graph, "pump", Embedder(), "words-v1")


def test_entry_search_checks_what_it_is_given(notes):
    with pytest.raises(TypeError, match="embedder"):
        embed_entries(notes, "not a function", "words-v1")
    with pytest.raises(ValueError, match="limit"):
        embed_entries(notes, Embedder(), "words-v1", limit=0)
    with pytest.raises(ValueError):
        embed_entries(notes, Embedder(), "")
    with pytest.raises(ValueError, match="vectors of 8"):
        embed_entries(notes, lambda texts: [[1.0] * 3 for _ in texts], "words-v1")
    assert count(notes, "(v:EntryVector)") == 0  # a bad answer stores nothing
    with pytest.raises(TypeError, match="question"):
        nearest_entries(notes, None, Embedder(), "words-v1")
    assert nearest_entries(notes, "   ", Embedder(), "words-v1") == []


def test_text_of_an_entry_is_its_text_values():
    entry = {"id": "e/1", "type": "observation", "words": "x", "b": "two", "a": ["one", 1], "n": 5}
    assert entry_text(entry) == "one\ntwo"
    assert entry_text({"id": "e/1", "n": 5, "s": "  "}) == ""


# --- what waits for a vector ----------------------------------------------------------


def waiting_labels(graph) -> list:
    rows = graph.ro_query("MATCH (e:ManualToEmbed) RETURN e.code ORDER BY e.code").result_set
    return [key for (key,) in rows]


def test_an_entity_waits_by_label_from_the_write_that_gives_it_text(graph):
    assert waiting_labels(graph) == ["m1", "m2", "m3", "m4"]  # m5 has no text
    embed(graph, MANUAL, Embedder(), model="count-8")
    assert waiting_labels(graph) == []
    remember(graph, MANUAL, [manual("m6", "Gaskets", "Fit the gasket.")], by="library")
    remember(graph, MANUAL, [{"key": "m6", "t": when(1), "values": {"pages": 1}}], by="library")
    assert "m6" not in waiting_labels(graph)  # its text went before it was embedded
    rows = [
        manual("m1", "Pump service", "Check the seal.", minute=1),  # the text changes
        manual(
            "m2",
            "Valve service",
            "Close the valve before service. The pump must be off.",
            minute=1,
            pages=12,
        ),  # only a value that is not text
        {"key": "m3", "t": when(1), "values": {"pages": 2}},  # the text goes
    ]
    remember(graph, MANUAL, rows, by="library")
    assert waiting_labels(graph) == ["m1"]
    embedder = Embedder()
    assert embed(graph, MANUAL, embedder, model="count-8") == {"embedded": 1, "waiting": 0}
    assert embedder.asked == [["Pump service\nCheck the seal."]]


def test_a_graph_written_before_labels_or_a_new_model_waits_once(graph):
    embed(graph, MANUAL, Embedder(), model="count-8")
    # As a graph written by an earlier version: no labels and no mark.
    graph.query("MATCH (s:Stamp) REMOVE s.embedded_Manual")
    assert embed(graph, MANUAL, Embedder(), model="count-8") == {"embedded": 0, "waiting": 0}
    assert waiting_labels(graph) == []
    embedder = Embedder()
    assert embed(graph, MANUAL, embedder, model="other-8", limit=3) == {
        "embedded": 3,
        "waiting": 1,
    }
    assert embed(graph, MANUAL, embedder, model="other-8") == {"embedded": 1, "waiting": 0}
    assert embed(graph, MANUAL, embedder, model="other-8") == {"embedded": 0, "waiting": 0}


def test_text_of_only_spaces_gets_no_vector_and_does_not_wait(graph):
    remember(graph, MANUAL, [manual("m7", "  ", "\n ")], by="library")
    embedder = Embedder()
    assert embed(graph, MANUAL, embedder, model="count-8") == {"embedded": 4, "waiting": 0}
    assert all("  " not in text for asked in embedder.asked for text in asked)


def test_entry_vectors_are_made_from_the_mark_on(db):
    import uuid

    from lighthouse.graphs import mark

    graph = db.select_graph(f"test_{uuid.uuid4().hex}")
    try:
        ensure_schema(graph, [], entry_dimensions=8)
        open_episode(graph, "e", "eye")
        for n in range(3):
            record(graph, "e", "observation", "eye", {"saw": f"pump {n}"})
        embed_entries(graph, Embedder(), model="count-8", limit=2)
        name = next(
            k
            for k in graph.ro_query("MATCH (s:Stamp) RETURN properties(s)").result_set[0][0]
            if k.startswith("embedded_entries_")
        )
        assert mark(graph, name) == 2  # the serial of the last entry it did
        embed_entries(graph, Embedder(), model="count-8")
        assert mark(graph, name) == 3
    finally:
        graph.delete()
