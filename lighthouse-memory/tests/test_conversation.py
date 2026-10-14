"""Conversations: one order of messages, sessions that belong to their user, and refusals
that are stored."""

import itertools
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import connect
from devices import DEVICE, PERSON, ROOM, count, failures, shape, when

from lighthouse import (
    context,
    ensure_schema,
    forget_session,
    forget_user,
    groups,
    messages,
    record_failure,
    remember,
    said,
    said_about,
    say,
    sessions,
    summarize,
)
from lighthouse.conversation import MESSAGE_PROPERTIES


def talk(graph, *texts, user="ann", session="main", role="user", **more) -> list[int]:
    """Say each text in one session. Returns the numbers the messages got."""
    receipts = [say(graph, user, session, role, text, by=user, **more) for text in texts]
    assert {receipt["status"] for receipt in receipts} == {"said"}
    assert {receipt["id"] for receipt in receipts} == {session}
    return [receipt["seq"] for receipt in receipts]


def texts(found) -> list[str]:
    return [message["text"] for message in found]


def check_sessions(graph):
    """What must hold for every session, whatever was said and by how many at once."""
    for key, held in graph.ro_query("MATCH (s:Session) RETURN s.key, s.message_count").result_set:
        numbers = graph.ro_query(
            "MATCH (:Session {key: $key})-[h:HAS]->(m:Message) RETURN m.seq ORDER BY m.seq",
            {"key": key},
        ).result_set
        assert [n for (n,) in numbers] == list(range(1, held + 1)), "every place taken once"
        chain = graph.ro_query(
            "MATCH (:Session {key: $key})-[:HAS]->(a:Message)-[:NEXT]->(b:Message) "
            "RETURN a.seq, b.seq, a.session = b.session AND a.user = b.user ORDER BY a.seq",
            {"key": key},
        ).result_set
        assert chain == [[n, n + 1, True] for n in range(1, held)], "one chain, in order"
    assert count(graph, "(m:Message)") == count(graph, "(:Session)-[h:HAS]->(:Message)", "h")
    assert count(graph, "(m:Message)-[:NEXT]->() WITH m, count(*) AS n WHERE n > 1") == 0


# --- saying ---------------------------------------------------------------------------


def test_messages_keep_the_order_they_were_said_in(graph):
    assert say(graph, "ann", "main", "user", "is d1 hot?", by="ann", at=when(1)) == {
        "id": "main",
        "seq": 1,
        "status": "said",
    }
    assert say(graph, "ann", "main", "helper", "yes, since noon", by="desk", at=when(2))["seq"] == 2
    assert say(graph, "ann", "main", "user", "thanks", by="ann", at=when(3))["seq"] == 3
    first, second, third = messages(graph, "ann", "main")
    assert first.pop("recorded_at") and first == {
        "session": "main",
        "seq": 1,
        "role": "user",
        "text": "is d1 hot?",
        "at": when(1),
        "by": "ann",
        "mentions": [],
    }
    assert (second["seq"], second["role"], second["by"]) == (2, "helper", "desk")
    assert (third["seq"], third["text"], third["at"]) == (3, "thanks", when(3))
    check_sessions(graph)


def test_first_message_opens_the_session(graph):
    assert sessions(graph, "ann") == [] and messages(graph, "ann", "main") == []
    talk(graph, "one", at=when(5))
    (opened,) = sessions(graph, "ann")
    assert (opened["id"], opened["opened_at"], opened["messages"]) == ("main", when(5), 1)
    talk(graph, "two", "three", at=when(9))
    (same,) = sessions(graph, "ann")
    assert (same["id"], same["opened_at"], same["messages"]) == ("main", when(5), 3)
    assert count(graph, "(s:Session)") == 1 and count(graph, "(m:Message)") == 3


def test_message_without_a_time_is_said_now(graph):
    talk(graph, "one")
    (message,) = messages(graph, "ann", "main")
    assert message["at"] == message["recorded_at"] and message["at"].year >= 2026


def test_values_of_every_storable_type_come_back(graph):
    values = {"model": "m1", "tokens": 12, "cost": 0.5, "cached": False, "tools": ["a", "b"]}
    talk(graph, "one", values=values)
    talk(graph, "two", values={"model": None})  # null means absent
    first, second = messages(graph, "ann", "main")
    assert {name: first[name] for name in values} == values
    assert "model" not in second


def test_messages_of_two_sessions_do_not_mix(graph):
    talk(graph, "a1", "a2", session="one")
    talk(graph, "b1", session="two")
    talk(graph, "a3", session="one")
    assert texts(messages(graph, "ann", "one")) == ["a1", "a2", "a3"]
    assert texts(messages(graph, "ann", "two")) == ["b1"]
    assert count(graph, "(a:Message {session: 'one'})-[:NEXT]->(b:Message {session: 'two'})") == 0
    check_sessions(graph)


def test_text_is_stored_as_it_is(graph):
    hostile = "'}) DETACH DELETE s // $session `x` \\ \" MATCH (n) \n\t <b>bold</b> 👍 ünï"
    talk(graph, hostile, "", " spaces kept ")
    assert texts(messages(graph, "ann", "main")) == [hostile, "", " spaces kept "]
    assert count(graph, "(s:Session)") == 1


# --- the window that is read ----------------------------------------------------------


def test_last_messages_are_given_and_the_ones_before_them_on_request(graph):
    talk(graph, *(f"m{n}" for n in range(1, 26)))
    assert texts(messages(graph, "ann", "main")) == [f"m{n}" for n in range(6, 26)]  # 20
    assert texts(messages(graph, "ann", "main", last=3)) == ["m23", "m24", "m25"]
    assert texts(messages(graph, "ann", "main", last=3, before=23)) == ["m20", "m21", "m22"]
    assert texts(messages(graph, "ann", "main", last=5, before=3)) == ["m1", "m2"]
    assert messages(graph, "ann", "main", before=1) == []
    assert texts(messages(graph, "ann", "main", last=1_000)) == [f"m{n}" for n in range(1, 26)]
    # A number after the end reads from the end.
    for after in (26, 27, 10**9):
        assert texts(messages(graph, "ann", "main", last=2, before=after)) == ["m24", "m25"]


def test_whole_session_can_be_read_back_in_pages(graph):
    talk(graph, *(f"m{n}" for n in range(1, 48)))
    read, before = [], None
    while page := messages(graph, "ann", "main", last=10, before=before):
        read = page + read
        before = page[0]["seq"]
    assert texts(read) == [f"m{n}" for n in range(1, 48)]
    assert [message["seq"] for message in read] == list(range(1, 48))


def test_session_that_the_user_does_not_have_gives_nothing(graph):
    talk(graph, "one")
    assert messages(graph, "ann", "other") == [] and messages(graph, "bob", "main") == []


# --- a session belongs to its user ----------------------------------------------------


def test_two_users_with_one_session_id_have_two_sessions(graph):
    talk(graph, "the pump of ann", user="ann", mentions=[(DEVICE, "d1")])
    talk(graph, "the pump of bob", "again the pump", user="bob", mentions=[(DEVICE, "d1")])
    assert texts(messages(graph, "ann", "main")) == ["the pump of ann"]
    assert texts(messages(graph, "bob", "main")) == ["the pump of bob", "again the pump"]
    assert [s["messages"] for s in sessions(graph, "ann")] == [1]
    assert [s["messages"] for s in sessions(graph, "bob")] == [2]
    assert texts(said(graph, "ann", "pump")) == ["the pump of ann"]
    assert texts(said_about(graph, "ann", (DEVICE, "d1"))) == ["the pump of ann"]
    assert sessions(graph, "eve") == [] and said(graph, "eve", "pump") == []
    assert said_about(graph, "eve", (DEVICE, "d1")) == []
    check_sessions(graph)


@pytest.mark.parametrize(
    "one, other",
    [
        (("a/b", "c"), ("a", "b/c")),
        (('a", "b', "c"), ("a", 'b", "c')),
        (("a", "main/1"), ("a", "main")),
        (('["a", "b"]', "c"), ("a", "b")),
        (("a\\", "b"), ("a", "\\b")),
        (("ann", "Main"), ("ann", "main")),
        (("ann ", "x") if False else ("änn", "x"), ("ann", "x")),
    ],
)
def test_users_and_ids_that_look_alike_are_apart(graph, one, other):
    talk(graph, "first", "second", user=one[0], session=one[1])
    talk(graph, "third", user=other[0], session=other[1])
    assert texts(messages(graph, *one)) == ["first", "second"]
    assert texts(messages(graph, *other)) == ["third"]
    assert count(graph, "(s:Session)") == 2
    check_sessions(graph)


def test_sessions_of_a_user_come_with_the_one_written_to_last_first(graph, monkeypatch):
    seconds = itertools.count(1)
    monkeypatch.setattr(
        "lighthouse.conversation.now", lambda: f"2026-03-01T00:00:{next(seconds):02}"
    )
    talk(graph, "a", session="old")
    talk(graph, "b", session="new")
    talk(graph, "c", session="mid", at=when(-500))  # said long ago, written now
    assert [s["id"] for s in sessions(graph, "ann")] == ["mid", "new", "old"]
    talk(graph, "d", session="old")
    assert [(s["id"], s["messages"]) for s in sessions(graph, "ann")] == [
        ("old", 2),
        ("mid", 1),
        ("new", 1),
    ]
    assert [s["id"] for s in sessions(graph, "ann", limit=2)] == ["old", "mid"]
    # The time a caller gives for a message does not move the session in this order.
    assert sessions(graph, "ann")[1]["opened_at"] == when(-500)


def test_sessions_written_in_one_second_come_by_id(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.conversation.now", lambda: "2026-03-01T00:00:00")
    for session in ("b", "c", "a"):
        talk(graph, "x", session=session)
    assert [s["id"] for s in sessions(graph, "ann")] == ["a", "b", "c"]


# --- what a message mentions ----------------------------------------------------------


def test_mentions_come_back_as_references(graph):
    talk(graph, "one", mentions=[(DEVICE, "d2"), (ROOM, "r1"), (DEVICE, "d1"), (DEVICE, "d2")])
    talk(graph, "two", mentions=[("Episode", "ep1"), "ep1/3", ("Lesson", "l1"), (ROOM, 7)])
    first, second = messages(graph, "ann", "main")
    assert first["mentions"] == [("Device", "d1"), ("Device", "d2"), ("Room", "r1")]
    assert second["mentions"] == [
        ("Entry", "ep1/3"),
        ("Episode", "ep1"),
        ("Lesson", "l1"),
        ("Room", 7),
    ]
    # A mention is a name. The thing is not looked up: it may be in another graph.
    assert count(graph, "(d:Device)") == 0 and count(graph, "(e:Episode)") == 0
    assert failures(graph) == []


def test_one_thing_is_one_reference_whoever_mentions_it(graph):
    talk(graph, "a", "b", mentions=[(DEVICE, "d1")])
    talk(graph, "c", user="bob", mentions=[(DEVICE, "d1"), (ROOM, "d1")])
    talk(graph, "d", mentions=[(ROOM, 7), (ROOM, "7")])  # a number is not its text
    found = graph.ro_query(
        "MATCH (r:Reference) OPTIONAL MATCH (r)<-[e:MENTIONS]-() "
        "RETURN r.label, r.id, count(e) ORDER BY r.key"
    ).result_set
    assert found == [["Device", "d1", 3], ["Room", "7", 1], ["Room", "d1", 1], ["Room", 7, 1]]


def test_messages_about_one_thing_newest_first(graph):
    talk(graph, "old", session="one", at=when(1), mentions=[(DEVICE, "d1")])
    talk(graph, "other thing", session="one", at=when(2), mentions=[(DEVICE, "d2")])
    talk(graph, "new", session="two", at=when(9), mentions=[(DEVICE, "d1"), (ROOM, "r1")])
    talk(graph, "mid", "mid again", session="one", at=when(5), mentions=[(DEVICE, "d1")])
    found = said_about(graph, "ann", (DEVICE, "d1"))
    assert texts(found) == ["new", "mid again", "mid", "old"]
    assert found[0]["mentions"] == [("Device", "d1"), ("Room", "r1")]
    assert (found[0]["session"], found[1]["session"], found[1]["seq"]) == ("two", "one", 4)
    assert texts(said_about(graph, "ann", (DEVICE, "d1"), limit=2)) == ["new", "mid again"]
    assert texts(said_about(graph, "ann", (ROOM, "r1"))) == ["new"]
    assert said_about(graph, "ann", (ROOM, "d1")) == []  # the same key of another kind
    assert said_about(graph, "ann", (DEVICE, "nope")) == []


def test_messages_of_one_moment_come_session_by_session(graph):
    for session in ("b", "a"):
        talk(graph, "pump", "pump", session=session, at=when(5), mentions=[(DEVICE, "d1")])
    newest = [("a", 2), ("a", 1), ("b", 2), ("b", 1)]
    assert [(m["session"], m["seq"]) for m in said_about(graph, "ann", (DEVICE, "d1"))] == newest
    assert [(m["session"], m["seq"]) for m in said(graph, "ann", "pump")] == newest
    assert [(m["session"], m["seq"]) for m in said(graph, "ann", "pump", limit=3)] == newest[:3]


def test_messages_about_a_record(graph):
    talk(graph, "see the episode", mentions=[("Episode", "ep1")])
    talk(graph, "see the entry", mentions=["ep1/2"])
    assert texts(said_about(graph, "ann", ("Episode", "ep1"))) == ["see the episode"]
    assert texts(said_about(graph, "ann", ("Entry", "ep1/2"))) == ["see the entry"]
    assert texts(said_about(graph, "ann", "ep1/2")) == ["see the entry"]


# --- what was said, by its words -------------------------------------------------------


@pytest.fixture
def spoken(graph):
    talk(graph, "the red pump leaks oil", "tankers wait at the gate", session="one", at=when(1))
    talk(graph, "pump pump pump", "nothing here", session="two", at=when(2))
    talk(graph, "the red pump of bob", user="bob")
    return graph


def test_messages_are_found_by_their_words(spoken):
    assert texts(said(spoken, "ann", "oil")) == ["the red pump leaks oil"]
    assert texts(said(spoken, "ann", "red pump")) == ["the red pump leaks oil"]
    assert set(texts(said(spoken, "ann", "pump"))) == {"the red pump leaks oil", "pump pump pump"}
    assert texts(said(spoken, "ann", "TANKER")) == ["tankers wait at the gate"]  # base form
    assert said(spoken, "ann", "submarine") == [] and said(spoken, "ann", "red gate") == []
    found = said(spoken, "ann", "red gate", match="any")
    assert set(texts(found)) == {"the red pump leaks oil", "tankers wait at the gate"}
    (message,) = said(spoken, "ann", "gate")
    assert message["score"] > 0 and message["mentions"] == [] and message["session"] == "one"
    assert "key" not in message and "user" not in message


def test_message_with_more_of_the_words_comes_first_up_to_the_limit(spoken):
    found = said(spoken, "ann", "red pump oil gate", match="any")
    assert texts(found)[0] == "the red pump leaks oil"  # three of the words
    assert set(texts(found)[1:]) == {"pump pump pump", "tankers wait at the gate"}
    ranked = [message["score"] for message in found]
    assert ranked == sorted(ranked, reverse=True) and ranked[0] > ranked[1]
    assert texts(said(spoken, "ann", "red pump oil gate", limit=1, match="any")) == [
        "the red pump leaks oil"
    ]


def test_equal_matches_come_newest_first(graph):
    talk(graph, "pump", session="one", at=when(1))
    talk(graph, "pump", "pump", session="two", at=when(5))
    talk(graph, "pump", session="one", at=when(9))
    found = said(graph, "ann", "pump")
    assert [(m["session"], m["seq"]) for m in found] == [
        ("one", 2),
        ("two", 2),
        ("two", 1),
        ("one", 1),
    ]
    assert [(m["session"], m["seq"]) for m in said(graph, "ann", "pump", limit=2)] == [
        ("one", 2),
        ("two", 2),
    ]


@pytest.mark.parametrize(
    "question",
    [
        "*",
        "p*",
        "-nothing",
        "@user:bob",
        "@text:pump | @user:bob",
        '"',
        "(",
        "~",
        "%pum%",
        "",
        "  ",
    ],
)
def test_question_in_the_language_of_the_index_is_read_as_words(spoken, question):
    found = said(spoken, "ann", question)
    assert all(message["session"] in ("one", "two") for message in found)
    assert len(found) <= 1  # never every message, and never a message of bob
    assert said(spoken, "ann", "@user:bob pump red of") == []


def test_question_without_a_word_asks_the_database_nothing(spoken, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a query was sent")

    monkeypatch.setattr(spoken, "ro_query", refuse)
    for question in ("", "   ", "?!", "*", "@:-|", "___"):
        assert said(spoken, "ann", question) == []


def test_question_must_be_text_and_the_match_one_of_two(spoken):
    for question in (None, 7, ["pump"]):
        with pytest.raises(TypeError, match="question must be text"):
            said(spoken, "ann", question)
    with pytest.raises(ValueError, match="match must be"):
        said(spoken, "ann", "pump", match="some")


# --- what is refused ------------------------------------------------------------------


@pytest.mark.parametrize("text", [7, None, ["a"], b"bytes", "a\x00b", "x" * 100_001, "bad \ud800"])
def test_text_that_cannot_be_stored_is_refused_and_stored(graph, text):
    receipt = say(graph, "ann", "main", "user", text, by="ann")
    assert receipt == {
        "id": None,
        "status": "invalid",
        "reason": "text must be text of at most 100000 characters",
    }
    assert count(graph, "(m:Message)") == 0 and count(graph, "(s:Session)") == 0
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("invalid", "Message", "main") and len(detail) <= 2_000
    assert talk(graph, "fine") == [1]  # the refused message took no number


def test_text_may_be_as_long_as_the_limit(graph):
    talk(graph, "x" * 100_000)
    assert len(messages(graph, "ann", "main")[0]["text"]) == 100_000


def test_text_and_values_together_have_a_limit(graph):
    long = "x" * 100_000
    talk(graph, long, values={"a": "y" * 60_000})  # 160,000 characters: stored
    receipt = say(
        graph, "ann", "main", "user", long, by="ann", values={"a": "y" * 60_000, "b": "y" * 60_000}
    )
    assert receipt["status"] == "invalid" and "larger than 200000" in receipt["reason"]
    assert [m["seq"] for m in messages(graph, "ann", "main")] == [1]


INVALID_MESSAGES = {
    "map as a value": {"values": {"a": {"b": 1}}},
    "values not a map": {"values": ["a"]},
    "unsafe value name": {"values": {"a b": 1}},
    "not a number": {"values": {"a": float("nan")}},
    "mentions not a list": {"mentions": "d1"},
    "mention by a label alone": {"mentions": [("Device", "d1")]},
    "mention of something that is no record": {"mentions": [("Session", "main")]},
    "mention with three parts": {"mentions": [(DEVICE, "d1", "extra")]},
    "empty mention": {"mentions": [""]},
    "too many mentions": {"mentions": [(DEVICE, f"d{n}") for n in range(201)]},
    "time that is not a time": {"at": "soon"},
    "time ahead of the clock": {"at": "2999-01-01T00:00:00Z"},
    "values larger than a message may be": {"values": {f"v{n}": "x" * 100_000 for n in range(3)}},
} | {f"value named {name}": {"values": {name: "x"}} for name in sorted(MESSAGE_PROPERTIES)}


@pytest.mark.parametrize("name", INVALID_MESSAGES)
def test_invalid_message_is_refused_and_stored(graph, name):
    talk(graph, "before")
    receipt = say(graph, "ann", "main", "user", "refused", by="ann", **INVALID_MESSAGES[name])
    assert receipt["status"] == "invalid" and receipt["id"] is None and receipt["reason"]
    assert texts(messages(graph, "ann", "main")) == ["before"]
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("invalid", "Message", "main") and receipt["reason"][
        :60
    ] in detail
    assert talk(graph, "after") == [2] and count(graph, "(r:Reference)") == 0
    check_sessions(graph)


def test_properties_that_the_library_sets_are_all_named():
    assert {"key", "session", "user", "seq", "role", "text", "at", "recorded_at", "by"} <= (
        MESSAGE_PROPERTIES
    )
    assert {"mentions", "score"} <= MESSAGE_PROPERTIES  # added when a message is read


@pytest.mark.parametrize("bad", [None, "", 7, " ann", "a\nb", "a\x00b", "x" * 201, ["ann"]])
def test_names_must_be_text(graph, bad):
    talk(graph, "one")
    for call in (
        lambda: say(graph, bad, "main", "user", "x", by="ann"),
        lambda: say(graph, "ann", bad, "user", "x", by="ann"),
        lambda: say(graph, "ann", "main", bad, "x", by="ann"),
        lambda: say(graph, "ann", "main", "user", "x", by=bad),
        lambda: messages(graph, bad, "main"),
        lambda: messages(graph, "ann", bad),
        lambda: sessions(graph, bad),
        lambda: said(graph, bad, "one"),
        lambda: said_about(graph, bad, (DEVICE, "d1")),
        lambda: summarize(graph, bad, "main", "sum", 1, by="desk"),
        lambda: summarize(graph, "ann", bad, "sum", 1, by="desk"),
        lambda: summarize(graph, "ann", "main", "sum", 1, by=bad),
        lambda: context(graph, bad, "main"),
        lambda: context(graph, "ann", bad),
        lambda: forget_session(graph, bad, "main"),
        lambda: forget_session(graph, "ann", bad),
        lambda: forget_user(graph, bad),
    ):
        with pytest.raises(ValueError, match="must be text"):
            call()
    assert count(graph, "(m:Message)") == 1 and failures(graph) == []
    assert context(graph, "ann", "main")["summary"] is None


@pytest.mark.parametrize("number", [0, -1, 1.5, "10", True, 1_001])
def test_number_of_a_wrong_form_is_refused(graph, number):
    talk(graph, "one", mentions=[(DEVICE, "d1")])
    for name, call in (
        ("last", lambda: messages(graph, "ann", "main", last=number)),
        ("before", lambda: messages(graph, "ann", "main", before=0 if number == 1_001 else number)),
        ("limit", lambda: sessions(graph, "ann", limit=number)),
        ("limit", lambda: said(graph, "ann", "one", limit=number)),
        ("limit", lambda: said(graph, "ann", "?", limit=number)),  # even when nothing is searched
        ("limit", lambda: said_about(graph, "ann", (DEVICE, "d1"), limit=number)),
        ("last", lambda: context(graph, "ann", "main", last=number)),
        ("last", lambda: context(graph, "ann", "nope", last=number)),
    ):
        with pytest.raises(ValueError, match=f"{name} must be a whole number"):
            call()
    assert len(messages(graph, "ann", "main", last=1_000)) == 1
    assert (
        len(sessions(graph, "ann", limit=1_000)) == 1 and len(said(graph, "ann", "one", 1_000)) == 1
    )


@pytest.mark.parametrize(
    "reference",
    [
        None,
        7,
        (DEVICE,),
        ("Device", "d1"),
        (DEVICE, None),
        (DEVICE, 1.5),
        ("Session", "s"),
        [DEVICE, "d1"],
    ],
)
def test_reference_of_a_wrong_form_is_refused(graph, reference):
    with pytest.raises(ValueError, match="reference: not a reference"):
        said_about(graph, "ann", reference)


def test_database_error_is_stored_and_reported(graph, monkeypatch):
    talk(graph, "before")
    with monkeypatch.context() as patch:
        patch.setattr("lighthouse.conversation.SAY", "RETURN no_such_function()")
        receipt = say(graph, "ann", "main", "user", "lost", by="ann")
    assert receipt["status"] == "failed" and "no_such_function" in receipt["reason"]
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("failed", "Message", "main") and "'text': 'lost'" in detail
    assert owners(graph) == [["ann", "Message", "main", "failed"]]  # so that it can be forgotten
    assert talk(graph, "after") == [2]
    assert texts(messages(graph, "ann", "main")) == ["before", "after"]


# --- many writers, and reads that write nothing ---------------------------------------


def test_many_writers_into_one_new_session_get_one_order(graph):
    receipts = []

    def writer(name):
        own = connect().select_graph(graph.name)
        for n in range(12):
            mentions = [(DEVICE, "d1")] if n % 2 else []
            receipts.append(
                say(own, "ann", "main", name, f"{name} {n}", by=name, mentions=mentions)
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in [pool.submit(writer, f"writer-{n}") for n in range(8)]:
            future.result()
    assert {receipt["status"] for receipt in receipts} == {"said"}
    assert sorted(receipt["seq"] for receipt in receipts) == list(range(1, 97))
    assert count(graph, "(s:Session)") == 1 and count(graph, "(r:Reference)") == 1
    read = messages(graph, "ann", "main", last=1_000)
    assert [message["seq"] for message in read] == list(range(1, 97))
    for name in (f"writer-{n}" for n in range(8)):  # each writer's own messages keep their order
        own = [message["text"] for message in read if message["by"] == name]
        assert own == [f"{name} {n}" for n in range(12)]
    check_sessions(graph)


def test_reads_change_nothing(graph):
    talk(graph, "the red pump", "again", mentions=[(DEVICE, "d1")])
    before = shape(graph)
    messages(graph, "ann", "main"), messages(graph, "ann", "nope"), sessions(graph, "ann")
    said(graph, "ann", "pump"), said_about(graph, "ann", (DEVICE, "d1"))
    said_about(graph, "ann", (DEVICE, "never mentioned"))
    assert shape(graph) == before


def test_conversation_needs_the_schema_of_no_kind(db):
    graph = db.select_graph("test_talk_alone")
    try:
        ensure_schema(graph)  # a graph of a tenant: no kind of its own
        talk(graph, "the pump", mentions=[(DEVICE, "d1")])
        assert texts(said(graph, "ann", "pump")) == ["the pump"]
        assert texts(said_about(graph, "ann", (DEVICE, "d1"))) == ["the pump"]
    finally:
        graph.delete()


# --- what a long session comes to ------------------------------------------------------


def owners(graph) -> list[list]:
    """Every stored failure: who owns what it held, its kind, its key, and its reason."""
    query = "MATCH (f:WriteFailure) RETURN f.owner, f.kind, f.key, f.reason ORDER BY f.owner, f.key"
    return graph.ro_query(query).result_set


def test_context_is_the_summary_and_the_messages_after_it(graph):
    talk(graph, *(f"m{n}" for n in range(1, 11)))
    assert context(graph, "ann", "main") == {
        "summary": None,
        "upto": 0,
        "messages": messages(graph, "ann", "main"),
        "waiting": 0,
    }
    assert summarize(graph, "ann", "main", "they spoke of pumps", upto=6, by="desk") == {
        "id": "main",
        "upto": 6,
        "status": "summed",
    }
    found = context(graph, "ann", "main")
    assert (found["summary"], found["upto"], found["waiting"]) == ("they spoke of pumps", 6, 0)
    assert texts(found["messages"]) == ["m7", "m8", "m9", "m10"]
    assert found["messages"] == messages(graph, "ann", "main", last=4)
    by, at = graph.ro_query("MATCH (s:Session) RETURN s.summary_by, s.summary_at").result_set[0]
    assert by == "desk" and at.year >= 2026


def test_context_says_how_many_messages_wait_for_a_summary(graph):
    talk(graph, *(f"m{n}" for n in range(1, 31)))
    found = context(graph, "ann", "main")
    assert texts(found["messages"]) == [f"m{n}" for n in range(11, 31)] and found["waiting"] == 10
    summarize(graph, "ann", "main", "the first five", upto=5, by="desk")
    found = context(graph, "ann", "main", last=10)
    assert texts(found["messages"]) == [f"m{n}" for n in range(21, 31)]
    assert (found["upto"], found["waiting"]) == (5, 15)  # m6 to m20 are in neither
    assert context(graph, "ann", "main", last=25)["waiting"] == 0
    assert context(graph, "ann", "main", last=24)["waiting"] == 1
    assert texts(context(graph, "ann", "main", last=1_000)["messages"])[0] == "m6"


def test_context_of_a_session_that_is_summed_to_its_end_has_no_messages(graph):
    talk(graph, "one", "two")
    summarize(graph, "ann", "main", "both", upto=2, by="desk")
    assert context(graph, "ann", "main") == {
        "summary": "both",
        "upto": 2,
        "messages": [],
        "waiting": 0,
    }
    talk(graph, "three")
    assert texts(context(graph, "ann", "main")["messages"]) == ["three"]


def test_later_summary_takes_the_place_of_the_one_before(graph):
    talk(graph, *(f"m{n}" for n in range(1, 11)))
    summarize(graph, "ann", "main", "first four", upto=4, by="desk")
    summarize(graph, "ann", "main", "first eight", upto=8, by="reviewer")
    assert (context(graph, "ann", "main")["summary"], context(graph, "ann", "main")["upto"]) == (
        "first eight",
        8,
    )
    assert summarize(graph, "ann", "main", "said better", upto=8, by="desk")["status"] == "summed"
    assert context(graph, "ann", "main")["summary"] == "said better"
    # One that reaches less far is refused: it would bring messages back that were summed.
    receipt = summarize(graph, "ann", "main", "first seven", upto=7, by="desk")
    assert receipt == {
        "id": None,
        "status": "stale",
        "reason": "the summary that is there reaches further",
    }
    assert (context(graph, "ann", "main")["summary"], context(graph, "ann", "main")["upto"]) == (
        "said better",
        8,
    )
    assert owners(graph) == [["ann", "Summary", "main", "stale"]]
    assert count(graph, "(s:Session)") == 1 and count(graph, "(n) WHERE n.summary IS NOT NULL") == 1


def test_summary_is_not_a_message(graph):
    talk(graph, "pumps", "valves")
    summarize(graph, "ann", "main", "they spoke of turbines", upto=2, by="desk")
    assert texts(messages(graph, "ann", "main")) == ["pumps", "valves"]
    assert said(graph, "ann", "turbines") == [] and sessions(graph, "ann")[0]["messages"] == 2
    assert talk(graph, "more") == [3]


def test_summary_may_reach_the_last_message_and_no_further(graph):
    talk(graph, "one", "two", "three")
    receipt = summarize(graph, "ann", "main", "all and more", upto=4, by="desk")
    assert receipt == {
        "id": None,
        "status": "invalid",
        "reason": "upto is past the last message of the session",
    }
    assert context(graph, "ann", "main")["summary"] is None
    assert summarize(graph, "ann", "main", "all", upto=3, by="desk")["status"] == "summed"
    assert summarize(graph, "ann", "main", "the first", upto=1, by="desk")["status"] == "stale"


def test_summary_of_a_session_that_the_user_does_not_have_is_refused(graph):
    talk(graph, "of bob", user="bob")
    for session in ("main", "nope"):
        receipt = summarize(graph, "ann", session, "not mine", upto=1, by="desk")
        assert receipt == {
            "id": None,
            "status": "unknown",
            "reason": "the user has no such session",
        }
    assert context(graph, "bob", "main")["summary"] is None
    assert context(graph, "ann", "main") == {
        "summary": None,
        "upto": 0,
        "messages": [],
        "waiting": 0,
    }
    assert owners(graph) == [
        ["ann", "Summary", "main", "unknown"],
        ["ann", "Summary", "nope", "unknown"],
    ]


@pytest.mark.parametrize("text", [7, None, ["a"], "", "   ", "a\x00b", "x" * 100_001, "bad \ud800"])
def test_summary_text_that_cannot_be_stored_is_refused(graph, text):
    talk(graph, "one")
    receipt = summarize(graph, "ann", "main", text, upto=1, by="desk")
    assert receipt["status"] == "invalid" and "text must be text" in receipt["reason"]
    assert context(graph, "ann", "main")["summary"] is None
    assert owners(graph) == [["ann", "Summary", "main", "invalid"]]


@pytest.mark.parametrize("upto", [0, -1, 1.5, "1", None, True])
def test_summary_up_to_something_that_is_no_number_is_refused(graph, upto):
    talk(graph, "one")
    receipt = summarize(graph, "ann", "main", "sum", upto=upto, by="desk")
    assert receipt["status"] == "invalid" and "upto must be a whole number" in receipt["reason"]
    assert context(graph, "ann", "main")["summary"] is None


def test_summary_that_the_database_refuses_is_stored_and_reported(graph, monkeypatch):
    talk(graph, "one")
    with monkeypatch.context() as patch:
        patch.setattr("lighthouse.conversation.SUM", "RETURN no_such_function()")
        receipt = summarize(graph, "ann", "main", "lost", upto=1, by="desk")
    assert receipt["status"] == "failed" and "no_such_function" in receipt["reason"]
    assert owners(graph) == [["ann", "Summary", "main", "failed"]]
    assert summarize(graph, "ann", "main", "kept", upto=1, by="desk")["status"] == "summed"


# --- what is forgotten -----------------------------------------------------------------


def everything(graph) -> str:
    """Every property of every node and edge of the graph, as one text."""
    nodes = graph.ro_query("MATCH (n) RETURN properties(n)").result_set
    edges = graph.ro_query("MATCH ()-[e]->() RETURN properties(e)").result_set
    return str(nodes) + str(edges)


@pytest.fixture
def lived(graph):
    """Ann has two sessions and Bob one. What must go when `main` of Ann is forgotten holds
    the word SECRET; what must stay holds KEPT."""
    talk(graph, "SECRET one", "SECRET two", mentions=[(DEVICE, "d1"), (ROOM, "SECRET-room")])
    talk(graph, "SECRET three", values={"note": "SECRET note"}, mentions=[(DEVICE, "d2")])
    summarize(graph, "ann", "main", "SECRET summary", upto=2, by="desk")
    say(graph, "ann", "main", "user", "SECRET refused \x00", by="ann")
    summarize(graph, "ann", "main", "SECRET refused summary", upto=99, by="desk")
    talk(graph, "KEPT of ann", session="other", mentions=[(DEVICE, "d1")])
    say(graph, "ann", "other", "user", "KEPT refused \x00", by="ann")
    talk(graph, "KEPT of bob", user="bob", mentions=[(DEVICE, "d2")])
    say(graph, "bob", "main", "user", "KEPT refused of bob \x00", by="bob")
    record_failure(graph, "invalid", "Device", "main", "KEPT failure of a device")
    # The reference holds its key twice; each message keeps its words for search.
    assert everything(graph).count("SECRET") == 12
    return graph


def test_forgotten_session_leaves_nothing_of_itself(lived):
    assert forget_session(lived, "ann", "main") == {
        "id": "main",
        "status": "forgotten",
        "messages": 3,
    }
    assert "SECRET" not in everything(lived)
    assert messages(lived, "ann", "main") == [] and said(lived, "ann", "SECRET") == []
    assert context(lived, "ann", "main") == {
        "summary": None,
        "upto": 0,
        "messages": [],
        "waiting": 0,
    }
    assert [s["id"] for s in sessions(lived, "ann")] == ["other"]
    assert said_about(lived, "ann", (DEVICE, "d2")) == []
    # What was not of that session is as it was.
    assert texts(messages(lived, "ann", "other")) == ["KEPT of ann"]
    assert texts(said_about(lived, "ann", (DEVICE, "d1"))) == ["KEPT of ann"]
    assert texts(messages(lived, "bob", "main")) == ["KEPT of bob"]
    assert texts(said_about(lived, "bob", (DEVICE, "d2"))) == ["KEPT of bob"]
    assert everything(lived).count("KEPT") == 7  # two messages, each with its words
    # A reference stays while a message mentions it, and goes with the last one that does.
    left = lived.ro_query("MATCH (r:Reference) RETURN r.label, r.id ORDER BY r.id").result_set
    assert left == [["Device", "d1"], ["Device", "d2"]]
    assert owners(lived) == [
        ["ann", "Message", "other", "invalid"],
        ["bob", "Message", "main", "invalid"],
        [None, "Device", "main", "invalid"],
    ]
    check_sessions(lived)


def test_session_that_the_user_does_not_have_cannot_be_forgotten(lived):
    before, stamp = shape(lived), lived.ro_query("MATCH (s:Stamp) RETURN s.id").result_set
    for user, session in (("ann", "nope"), ("eve", "main"), ("bob", "other")):
        assert forget_session(lived, user, session) == {
            "id": session,
            "status": "unknown",
            "messages": 0,
        }
    assert shape(lived) == before
    assert lived.ro_query("MATCH (s:Stamp) RETURN s.id").result_set == stamp  # nothing deleted


def test_session_starts_again_after_it_was_forgotten(lived):
    forget_session(lived, "ann", "main")
    assert forget_session(lived, "ann", "main")["status"] == "unknown"
    assert talk(lived, "new start") == [1]
    found = context(lived, "ann", "main")
    assert (found["summary"], texts(found["messages"])) == (None, ["new start"])
    check_sessions(lived)


def test_refused_message_of_a_session_that_never_opened_is_forgotten(graph):
    say(graph, "ann", "main", "user", "SECRET \x00", by="ann")
    assert owners(graph) == [["ann", "Message", "main", "invalid"]]
    assert forget_session(graph, "ann", "main") == {
        "id": "main",
        "status": "unknown",
        "messages": 0,
    }
    assert owners(graph) == [] and "SECRET" not in everything(graph)


def test_long_session_is_forgotten_in_steps_that_each_leave_it_whole(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.conversation.BATCH", 7)
    talk(graph, *(f"m{n}" for n in range(1, 31)), mentions=[(DEVICE, "d1"), (ROOM, "r1")])
    for n in range(40):  # more references and more failures than one step takes
        talk(graph, f"x{n}", session="many", mentions=[(ROOM, f"room-{n}"), (ROOM, f"hall-{n}")])
        say(graph, "ann", "many", "user", "bad \x00", by="ann")
    talk(graph, "stays", session="other", mentions=[(DEVICE, "d1")])
    steps, send = [], graph.query

    def watched(query, params=None, **more):
        result = send(query, params, **more)
        if "DETACH DELETE s" in query:
            check_sessions(graph)  # a shorter session that reads right
            steps.append(count(graph, "(m:Message {session: 'main'})"))
        return result

    monkeypatch.setattr(graph, "query", watched)
    assert forget_session(graph, "ann", "main")["messages"] == 30
    assert steps == [23, 16, 9, 2, 0]
    assert forget_session(graph, "ann", "many")["messages"] == 40
    assert count(graph, "(m:Message)") == 1 and count(graph, "(s:Session)") == 1
    assert graph.ro_query("MATCH (r:Reference) RETURN r.id").result_set == [["d1"]]
    assert owners(graph) == []


def test_everything_a_user_said_is_forgotten(lived):
    say(lived, "ann", "never opened", "user", "SECRET \x00", by="ann")
    assert forget_user(lived, "ann") == {"user": "ann", "sessions": 2, "messages": 4}
    found = everything(lived)
    assert "SECRET" not in found and "ann" not in found
    assert sessions(lived, "ann") == [] and said(lived, "ann", "KEPT") == []
    assert texts(messages(lived, "bob", "main")) == ["KEPT of bob"]
    assert owners(lived) == [
        ["bob", "Message", "main", "invalid"],
        [None, "Device", "main", "invalid"],
    ]
    assert forget_user(lived, "ann") == {"user": "ann", "sessions": 0, "messages": 0}
    assert forget_user(lived, "eve") == {"user": "eve", "sessions": 0, "messages": 0}
    check_sessions(lived)


def test_user_with_more_sessions_than_one_read_gives_is_forgotten(graph):
    for n in range(103):
        talk(graph, "x", session=f"s{n}")
    talk(graph, "stays", user="bob")
    assert forget_user(graph, "ann") == {"user": "ann", "sessions": 103, "messages": 103}
    assert count(graph, "(s:Session)") == 1 and count(graph, "(m:Message)") == 1


def test_every_query_that_deletes_gives_the_graph_a_new_stamp(lived, monkeypatch):
    monkeypatch.setattr("lighthouse.conversation.BATCH", 2)
    send, deleting = lived.query, []

    def stamp():
        return lived.ro_query("MATCH (s:Stamp) RETURN s.id").result_set[0][0]

    def watched(query, params=None, **more):
        before = stamp()
        result = send(query, params, **more)
        if result.nodes_deleted:
            deleting.append(query.split()[0:4])
            assert stamp() != before, query
        return result

    monkeypatch.setattr(lived, "query", watched)
    forget_user(lived, "ann")
    # Messages with their session, references that nothing mentions, and failures.
    assert {tuple(words) for words in deleting} == {
        ("MATCH", "(s:Session", "{key:", "$session})"),
        ("UNWIND", "$keys", "AS", "k"),
        ("MATCH", "(f:WriteFailure", "{owner:", "$user})"),
    }


def test_forgetting_gives_the_graph_a_new_stamp(lived):
    stamps = [lived.ro_query("MATCH (s:Stamp) RETURN s.id").result_set[0][0]]
    forget_session(lived, "ann", "main")
    stamps.append(lived.ro_query("MATCH (s:Stamp) RETURN s.id").result_set[0][0])
    forget_user(lived, "bob")
    stamps.append(lived.ro_query("MATCH (s:Stamp) RETURN s.id").result_set[0][0])
    assert len(set(stamps)) == 3 and count(lived, "(s:Stamp)") == 1


def test_answer_that_was_kept_is_not_given_again_after_something_was_forgotten(graph):
    ensure_schema(graph, [PERSON])

    def know(minute, **lists):
        rows = [{"key": k, "t": when(minute), "relations": {"KNOWS": v}} for k, v in lists.items()]
        remember(graph, PERSON, rows, by="test")

    know(0, a=["b"], b=["c"])
    talk(graph, "stays", session="other", mentions=[(DEVICE, "d1")])
    talk(graph, "goes", session="main", mentions=[(DEVICE, "d1")])
    first = groups(graph, [PERSON])  # kept
    assert [group["size"] for group in first] == [3]
    whole = (count(graph, "(n)"), count(graph, "()-[e]->()", "e"))
    know(5, c=["d"])  # two more nodes and two more edges
    forget_session(graph, "ann", "main")  # two nodes and two edges fewer
    # As many nodes and edges as when the answer was kept, and not the same graph.
    assert (count(graph, "(n)"), count(graph, "()-[e]->()", "e")) == whole
    assert [group["size"] for group in groups(graph, [PERSON])] == [4]


def test_writers_and_forgetting_at_once_leave_whole_sessions(graph):
    receipts = []

    def writer(name):
        own = connect().select_graph(graph.name)
        for n in range(15):
            receipts.append(say(own, "ann", "main", name, f"{name} {n}", by=name))

    def forgetter(_):
        own = connect().select_graph(graph.name)
        for _ in range(10):
            receipts.append(forget_session(own, "ann", "main"))

    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs = [pool.submit(writer, f"writer-{n}") for n in range(4)] + [pool.submit(forgetter, 0)]
        for job in jobs:
            job.result()
    assert {receipt["status"] for receipt in receipts} <= {"said", "forgotten", "unknown"}
    check_sessions(graph)
    read = messages(graph, "ann", "main", last=1_000)
    assert [message["seq"] for message in read] == list(range(1, len(read) + 1))
    forgotten = sum(r["messages"] for r in receipts if r["status"] == "forgotten")
    assert forgotten + len(read) == 60  # every message was either deleted or is still there
    assert owners(graph) == []


def test_message_value_cannot_take_the_name_of_its_words(graph):
    receipt = say(graph, "ann", "main", "user", "hello", by="ann", values={"words": "other"})
    assert receipt["status"] == "invalid"


def test_words_next_to_a_line_break_are_found_in_what_was_said(graph):
    talk(graph, "first line\nsecond_line\u00a0third")
    for word in ("line", "second", "third"):
        assert texts(said(graph, "ann", word)) == ["first line\nsecond_line\u00a0third"], word
    assert "words" not in messages(graph, "ann", "main")[0]
