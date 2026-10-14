"""Recall by text: the words of a question, and never its query language."""

import pytest
from devices import DEVICE, MANUAL, count, when

from lighthouse import (
    Kind,
    close_episode,
    ensure_schema,
    episode,
    open_episode,
    record,
    remember,
    search,
    search_entries,
    search_history,
)
from lighthouse.recall.text import MAX_WORDS, words


def manual(code, title, body, minute=0) -> dict:
    return {"key": code, "t": when(minute), "values": {"title": title, "body": body, "pages": 10}}


@pytest.fixture
def graph(graph):
    rows = [
        manual("m1", "Pump service", "Check the seal of the pump. Replace a worn seal."),
        manual("m2", "Valve service", "Close the valve before service. The pump must be off."),
        manual("m3", "Cooling tanks", "Tankers deliver coolant. Élan brand filters fit."),
        manual("m4", "Safety", "Wear gloves."),
    ]
    assert {r["status"] for r in remember(graph, MANUAL, rows, by="library")} == {"created"}
    return graph


def keys(found) -> list:
    return [item["key"] for item in found]


# --- finding --------------------------------------------------------------------------


def test_search_finds_entities_by_the_words_of_their_text(graph):
    found = search(graph, MANUAL, "pump seal")
    assert keys(found) == ["m1"]
    assert found[0]["values"] == {
        "title": "Pump service",
        "body": "Check the seal of the pump. Replace a worn seal.",
        "pages": 10,
    }
    assert found[0]["score"] > 0
    assert keys(search(graph, MANUAL, "PUMP")) == ["m1", "m2"]  # the title counts for more
    assert keys(search(graph, MANUAL, "gloves")) == ["m4"]
    assert search(graph, MANUAL, "turbine") == []


def test_every_word_must_match_unless_any_is_asked_for(graph):
    assert keys(search(graph, MANUAL, "valve seal")) == []
    assert sorted(keys(search(graph, MANUAL, "valve seal", match="any"))) == ["m1", "m2"]
    assert sorted(keys(search(graph, MANUAL, "service"))) == ["m1", "m2"]


def test_words_match_in_their_base_form_and_whatever_their_case(graph):
    assert keys(search(graph, MANUAL, "tanker")) == ["m3"]  # the text says "Tankers"
    assert keys(search(graph, MANUAL, "seals")) == ["m1"]
    assert keys(search(graph, MANUAL, "élan")) == ["m3"]


def test_best_matches_come_first_up_to_the_limit(graph):
    best = search(graph, MANUAL, "pump", limit=1)
    assert keys(best) == ["m1"]
    scores = [item["score"] for item in search(graph, MANUAL, "pump service", match="any")]
    assert scores == sorted(scores, reverse=True) and len(scores) == 2
    assert keys(search(graph, MANUAL, "valve service", match="any")) == [
        "m2",
        "m1",
    ]  # by score, not by key


def test_search_sees_the_current_text_only(graph):
    remember(graph, MANUAL, [manual("m4", "Protection", "Wear a helmet.", minute=5)], by="library")
    assert search(graph, MANUAL, "gloves") == [] and search(graph, MANUAL, "safety") == []
    assert keys(search(graph, MANUAL, "helmet")) == ["m4"]
    assert keys(search(graph, MANUAL, "protection")) == ["m4"]


def test_search_reads_the_text_properties_only(graph):
    assert search(graph, MANUAL, "10") == []  # `pages` is not text
    assert search(graph, MANUAL, "m1") == []  # neither is the key


# --- earlier versions -------------------------------------------------------------------


def test_search_history_finds_what_an_entity_said_at_any_time(graph):
    remember(graph, MANUAL, [manual("m4", "Protection", "Wear a helmet.", minute=5)], by="library")
    (old,) = search_history(graph, MANUAL, "gloves")
    assert old["key"] == "m4" and old["score"] > 0
    assert (old["state"]["valid_from"], old["state"]["valid_to"]) == (when(0), when(5))
    assert old["state"]["body"] == "Wear gloves."
    (new,) = search_history(graph, MANUAL, "helmet")
    assert new["state"]["valid_from"] == when(5) and "valid_to" not in new["state"]
    assert [found["key"] for found in search_history(graph, MANUAL, "wear")] == ["m4", "m4"]


def test_search_history_reads_the_text_of_its_own_kind_only(graph):
    note = Kind("Note", key="id", text=("body",))
    tag = Kind("Tag", key="id")
    ensure_schema(graph, [MANUAL, note, tag])
    remember(graph, tag, [{"key": "t1", "t": when(0), "values": {"title": "pump"}}], by="x")
    row = {"key": "n1", "t": when(0), "values": {"title": "pump", "body": "nothing"}}
    remember(graph, note, [row], by="x")
    assert keys(search_history(graph, MANUAL, "pump")) == ["m1", "m2"]  # no Tag
    assert search_history(graph, note, "pump") == []  # the title of a Note is not its text
    assert keys(search_history(graph, note, "nothing")) == ["n1"]


def test_search_history_gives_the_evidence_of_a_state(graph):
    open_episode(graph, "read", "reader")
    entry = record(graph, "read", "observation", "reader", {"saw": "a new manual"})["id"]
    found = manual("m5", "Boiler", "Bleed the boiler.")
    remember(graph, MANUAL, [found | {"entry": entry}], by="reader")
    assert search_history(graph, MANUAL, "boiler")[0]["state"]["entry"] == entry


def test_search_history_gives_the_best_first_up_to_the_limit(graph):
    assert keys(search_history(graph, MANUAL, "pump", limit=1)) == ["m1"]
    found = search_history(graph, MANUAL, "valve service", match="any")
    assert keys(found) == ["m2", "m1"]
    assert found[0]["score"] >= found[1]["score"]
    assert search_history(graph, MANUAL, "valve seal") == []


def test_search_history_keeps_its_order_when_some_states_have_evidence(graph):
    open_episode(graph, "read", "reader")
    entry = record(graph, "read", "observation", "reader", {"saw": "notes"})["id"]
    found = manual("m5", "Notes", "Somewhere a word about a pump, among many other words here.")
    remember(graph, MANUAL, [found | {"entry": entry}], by="reader")
    result = search_history(graph, MANUAL, "pump")
    assert keys(result)[-1] == "m5" and result[-1]["state"]["entry"] == entry  # the weakest
    scores = [item["score"] for item in result]
    assert scores == sorted(scores, reverse=True)


# FalkorDB's index does not split words at these. The library indexes the words alone.
SPLIT = "Line\nbreak first_word\u00a0second\u2028third\r\nfourth\ttab"
SPLIT_WORDS = ("line", "break", "first", "word", "second", "third", "fourth", "tab")


def test_words_next_to_a_line_break_or_an_underscore_are_found(graph):
    remember(graph, MANUAL, [manual("m9", "Notes", SPLIT)], by="x")
    for word in SPLIT_WORDS:
        assert keys(search(graph, MANUAL, word)) == ["m9"], word
        assert keys(search_history(graph, MANUAL, word)) == ["m9"], word
    assert search(graph, MANUAL, "notes")[0]["values"]["body"] == SPLIT  # the text as given
    open_episode(graph, "note", "eye")
    entry = record(graph, "note", "observation", "eye", {"saw": SPLIT})["id"]
    for word in SPLIT_WORDS:
        assert [e["id"] for e in search_entries(graph, word)] == [entry], word


# --- entries ----------------------------------------------------------------------------


def test_search_entries_finds_entries_by_the_words_of_their_values(graph):
    open_episode(graph, "leak", "eye")
    first = record(graph, "leak", "observation", "eye", {"saw": "oil under the pump", "litres": 3})
    second = record(graph, "leak", "action", "eye", {"steps": ["closed the valve", "called"]})
    close_episode(graph, "leak", "eye", {"cause": "a worn seal"})
    (found,) = search_entries(graph, "pump oil")
    assert found["id"] == first["id"] and found["score"] > 0
    assert found["entry"]["saw"] == "oil under the pump" and "words" not in found["entry"]
    assert [e["id"] for e in search_entries(graph, "valve")] == [second["id"]]  # in a list
    assert [e["id"] for e in search_entries(graph, "seal")] == ["leak/3"]  # the outcome
    assert search_entries(graph, "3") == []  # a number is not text
    assert [e["id"] for e in search_entries(graph, "valve seal", match="any")] == [
        "leak/2",
        "leak/3",
    ]
    assert all("words" not in entry for entry in episode(graph, "leak")["entries"])


def test_entry_value_cannot_take_the_name_of_its_words(graph):
    open_episode(graph, "leak", "eye")
    receipt = record(graph, "leak", "observation", "eye", {"words": "anything"})
    assert receipt["status"] == "invalid"


# --- the question is words, not a query -----------------------------------------------


def test_words_of_a_question():
    assert words("Pump-seal, PUMP & (valve)!") == ["pump", "seal", "valve"]
    assert words("ro-ro ferry_boat 2nd") == ["ro", "ferry", "boat", "2nd"]
    assert words('* -x |y @title:z "q r" ~s %t%') == ["x", "y", "title", "z", "q", "r", "s", "t"]
    assert words("") == [] and words(" *-|@\"'()~%${}[]\\ ") == []
    assert words("a\x00b\ud800c") == ["a", "b", "c"]
    assert len(words(" ".join(f"w{n}" for n in range(500)))) == MAX_WORDS
    assert words("x" * 5_000) == ["x" * 50]
    assert words("é" * 3 + " Ünïcode") == ["ééé", "ünïcode"]


HOSTILE = {
    "list everything": "*",
    "list everything by prefix": "s*",
    "exclude": "service -pump",
    "choose a field": "@body:pump",
    "phrase": '"the pump"',
    "open group": "(pump",
    "close group": "pump)",
    "fuzzy": "%pmup%",
    "optional": "~pump",
    "or": "valve|gloves",
    "cypher": "x') YIELD node MATCH (n) DETACH DELETE n //",
    "parameter": "$terms $limit",
    "backslash": "pump\\",
    "quote": "pump' \" `",
    "bad bytes": "pump\x00\ud800",
    "nothing but signs": "*|-@()~%\"'",
}


@pytest.mark.parametrize("name", HOSTILE)
@pytest.mark.parametrize("find", [search, search_history])
def test_question_in_the_query_language_of_the_index_is_read_as_words(graph, name, find):
    before = count(graph, "(n)")
    found = keys(find(graph, MANUAL, HOSTILE[name]))
    expected = {
        "list everything": [],
        "list everything by prefix": [],
        "exclude": ["m1", "m2"],  # both words, nothing excluded: m1 has pump in its title
        "choose a field": [],  # the words "body" and "pump": no text has the word "body"
        "phrase": ["m1", "m2"],
        "open group": ["m1", "m2"],
        "close group": ["m1", "m2"],
        "fuzzy": [],
        "optional": ["m1", "m2"],
        "or": [],  # both words must match: no manual has valve and gloves
        "cypher": [],
        "parameter": [],
        "backslash": ["m1", "m2"],
        "quote": ["m1", "m2"],
        "bad bytes": ["m1", "m2"],
        "nothing but signs": [],
    }[name]
    assert sorted(found) == sorted(expected), found
    assert count(graph, "(n)") == before


def test_long_question_is_cut_not_refused(graph):
    assert keys(search(graph, MANUAL, "pump " * 100_000)) == ["m1", "m2"]
    assert keys(
        search(graph, MANUAL, " ".join(["pump"] + [f"w{n}" for n in range(1000)]), match="any")
    ) == [
        "m1",
        "m2",
    ]


# --- what is refused ------------------------------------------------------------------


def test_kind_without_text_cannot_be_searched(graph):
    with pytest.raises(ValueError, match="no text"):
        search(graph, DEVICE, "pump")


@pytest.mark.parametrize("question", [None, 7, ["pump"], {"q": "pump"}, b"pump"])
def test_question_that_is_not_text_is_refused(graph, question):
    with pytest.raises(TypeError, match="question"):
        search(graph, MANUAL, question)


@pytest.mark.parametrize("limit", [0, -1, 1001, 1.5, "10", None, True])
def test_limit_of_a_wrong_form_is_refused(graph, limit):
    with pytest.raises(ValueError, match="limit"):
        search(graph, MANUAL, "pump", limit=limit)


@pytest.mark.parametrize("match", ["both", "", None, "ALL", "all|any"])
def test_match_of_a_wrong_form_is_refused(graph, match):
    with pytest.raises(ValueError, match="match"):
        search(graph, MANUAL, "pump", match=match)


@pytest.mark.parametrize("name", HOSTILE)
def test_question_for_entries_is_read_as_words(graph, name):
    open_episode(graph, "leak", "eye")
    record(graph, "leak", "observation", "eye", {"saw": "the pump seal leaks", "valve": "the pump"})
    before = count(graph, "(n)")
    found = search_entries(graph, HOSTILE[name])
    with_pump = name in ("phrase", "open group", "close group", "optional")
    with_pump |= name in ("backslash", "quote", "bad bytes")
    assert [e["id"] for e in found] == (["leak/1"] if with_pump else []), found
    assert count(graph, "(n)") == before


@pytest.mark.parametrize(
    "find", [search_history, lambda graph, kind, *a, **k: search_entries(graph, *a, **k)]
)
def test_searches_of_earlier_text_and_of_entries_check_what_they_are_given(graph, find):
    with pytest.raises(TypeError, match="question"):
        find(graph, MANUAL, None)
    with pytest.raises(ValueError, match="limit"):
        find(graph, MANUAL, "pump", limit=0)
    with pytest.raises(ValueError, match="match"):
        find(graph, MANUAL, "pump", match="both")
    assert find(graph, MANUAL, "*|-") == []


def test_kind_without_text_has_no_history_to_search(graph):
    with pytest.raises(ValueError, match="no text"):
        search_history(graph, DEVICE, "pump")
