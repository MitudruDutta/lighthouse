"""Lessons: no lesson without evidence, every piece of evidence counted once, ranked by weight."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import connect
from devices import DEVICE, ROOM, count, failures, row, shape, when, write

from lighthouse import (
    close_episode,
    episode,
    learn,
    lesson,
    lessons_about,
    open_episode,
    record,
    retire,
    used,
    weigh,
)


@pytest.fixture
def graph(graph):
    """Two devices. Episodes e1 to e6 about d1 have ended; `open` has not."""
    write(graph, row(key="d1", room="r1"), row(key="d2", room="r2"))
    for n in range(1, 7):
        open_episode(graph, f"e{n}", by="watcher", about=[(DEVICE, "d1")], at=when(n))
        close_episode(graph, f"e{n}", by="reviewer", outcome={"failed": n % 2 == 0}, at=when(n + 1))
    open_episode(graph, "open", by="watcher", about=[(DEVICE, "d1")], at=when(9))
    return graph


def learned(
    graph, lesson_id="l1", supported_by=("e1", "e2"), about=((DEVICE, "d1"),), **more
) -> dict:
    statement = more.pop("statement", "A hot device fails within a day.")
    episodes = supported_by if isinstance(supported_by, str) else list(supported_by)
    return learn(graph, lesson_id, "reviewer", statement, episodes, about=list(about), **more)


def check_lessons(graph):
    """What must hold for every lesson, whatever was written."""
    counted = graph.ro_query(
        "MATCH (l:Lesson) "
        "OPTIONAL MATCH (l)-[s:SUPPORTED_BY]->(:Episode) WITH l, count(s) AS support "
        "OPTIONAL MATCH (l)-[c:CONTRADICTED_BY]->(:Episode) WITH l, support, count(c) AS against "
        "OPTIONAL MATCH (l)-[u:USED_IN]->(:Episode) "
        "WITH l, support, against, count(u) AS used, "
        "sum(CASE WHEN u.helped = true THEN 1 ELSE 0 END) AS helped, "
        "sum(CASE WHEN u.helped = false THEN 1 ELSE 0 END) AS failed "
        "RETURN l.id, [l.support, l.against, l.used, l.helped, l.failed], "
        "[support, against, used, helped, failed]"
    ).result_set
    for lesson_id, stored, edges in counted:
        assert stored == [int(n) for n in edges], lesson_id  # every count equals its edges
        assert stored[0] >= 1, f"{lesson_id} has no evidence"
    assert (
        count(
            graph,
            "(:Lesson)-[:SUPPORTED_BY|CONTRADICTED_BY]->(ep:Episode) WHERE ep.closed_at IS NULL",
        )
        == 0
    )
    both = (
        "(l:Lesson)-[:SUPPORTED_BY]->(ep:Episode)<-[:CONTRADICTED_BY]-(m:Lesson) WHERE l.id = m.id"
    )
    assert count(graph, both) == 0  # an episode is for a lesson or against it, not both
    assert count(graph, "(:Agent)-[w:WROTE]->(:Lesson)", "w") == len(counted)


# --- learning -------------------------------------------------------------------------


def test_lesson_is_stored_with_the_episodes_it_was_learned_from(graph):
    receipt = learned(graph, values={"confidence": "low"}, at=when(20))
    assert receipt == {"id": "l1", "status": "learned"}
    found = lesson(graph, "l1")
    assert {k: v for k, v in found.items() if k != "recorded_at"} == {
        "id": "l1",
        "statement": "A hot device fails within a day.",
        "confidence": "low",
        "by": "reviewer",
        "at": when(20),
        "touched_at": when(20),
        "support": 2,
        "against": 0,
        "used": 0,
        "helped": 0,
        "failed": 0,
        "weight": 2,
        "supported_by": ["e1", "e2"],
        "contradicted_by": [],
        "about": [("Device", "d1")],
    }
    assert count(graph, "(:Agent {id: 'reviewer'})-[w:WROTE]->(:Lesson {id: 'l1'})", "w") == 1
    check_lessons(graph)


def test_lesson_learned_again_changes_nothing(graph):
    learned(graph)
    again = learn(graph, "l1", "mallory", "Something else.", ["e3"], about=[(DEVICE, "d2")])
    assert again == {"id": "l1", "status": "exists"}
    found = lesson(graph, "l1")
    assert (found["statement"], found["by"], found["supported_by"]) == (
        "A hot device fails within a day.",
        "reviewer",
        ["e1", "e2"],
    )
    assert count(graph, "(l:Lesson)") == 1


def test_lesson_about_several_entities_or_none(graph):
    learned(graph, "wide", about=[(DEVICE, "d1"), (ROOM, "r1"), (DEVICE, "d2")])
    learned(graph, "general", about=[])
    assert lesson(graph, "wide")["about"] == [("Device", "d1"), ("Device", "d2"), ("Room", "r1")]
    assert lesson(graph, "general")["about"] == []
    assert [x["id"] for x in lessons_about(graph, ROOM, "r1")] == ["wide"]


@pytest.mark.parametrize(
    "arguments",
    [{"supported_by": ["nope"]}, {"supported_by": ["e1", "open"]}, {"about": [(DEVICE, "nope")]}],
    ids=[
        "an episode that does not exist",
        "an episode that has not ended",
        "an entity that does not exist",
    ],
)
def test_lesson_without_real_evidence_is_refused_and_stored(graph, arguments):
    before = shape(graph)
    receipt = learned(graph, **arguments)
    assert receipt["status"] == "missing" and receipt["id"] is None
    nodes, edges = shape(graph)
    assert nodes.pop("WriteFailure") == 1 and (nodes, edges) == before
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("missing", "Lesson", "l1") and "A hot device" in detail


INVALID_LESSONS = {
    "no episode": {"supported_by": []},
    "episodes not a list": {"supported_by": "e1"},
    "episode id of a wrong form": {"supported_by": ["e1", ""]},
    "episode id with bad bytes": {"supported_by": ["e1\x00"]},
    "too many episodes": {"supported_by": [f"e{n}" for n in range(201)]},
    "no statement": {"statement": ""},
    "blank statement": {"statement": "  \n "},
    "statement that is not text": {"statement": ["a", "b"]},
    "statement with bad bytes": {"statement": "a\x00b"},
    "statement too long": {"statement": "x" * 100_001},
    "map as a value": {"values": {"a": {"b": 1}}},
    "values not a map": {"values": ["a"]},
    "value named like the statement": {"values": {"statement": "another"}},
    "value named like a count": {"values": {"support": 999}},
    "value named like the weight": {"values": {"weight": 999}},
    "value named like the uses": {"values": {"helped": 999}},
    "value named like the retirement": {"values": {"retired_at": "2020-01-01"}},
    "about of a wrong form": {"about": [("Device", "d1")]},
    "about an episode": {"about": [("Episode", "e1")]},
    "time that is not a time": {"at": "soon"},
    "time in the future": {"at": "2999-01-01T00:00:00Z"},
    "too much content": {"values": {f"p{i}": "x" * 50_000 for i in range(5)}},
}


@pytest.mark.parametrize("name", INVALID_LESSONS)
def test_invalid_lesson_is_refused_and_stored(graph, name):
    receipt = learned(graph, **INVALID_LESSONS[name])
    assert receipt["status"] == "invalid" and receipt["id"] is None and receipt["reason"]
    assert lesson(graph, "l1") is None and count(graph, "(l:Lesson)") == 0
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("invalid", "Lesson", "l1") and len(detail) <= 2_000


def test_database_error_is_stored_and_reported(graph, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr("lighthouse.lessons._learn_query", lambda groups: "RETURN no_such_function()")
        patch.setattr("lighthouse.lessons.WEIGH", "RETURN no_such_function()")
        receipts = [learned(graph), weigh(graph, "l1", "reviewer", "e3", agrees=True)]
    assert [r["status"] for r in receipts] == ["failed", "failed"]
    assert [f[:3] for f in failures(graph)] == [["failed", "Lesson", "l1"]] * 2
    assert learned(graph)["status"] == "learned"


# --- evidence for and against ---------------------------------------------------------


def test_episode_counts_once_for_or_against_a_lesson(graph):
    learned(graph, at=when(20))
    assert weigh(graph, "l1", "reviewer", "e3", agrees=True, at=when(21)) == {
        "id": "l1",
        "status": "weighed",
    }
    assert weigh(graph, "l1", "reviewer", "e4", agrees=False, at=when(22))["status"] == "weighed"
    for episode_id in ("e1", "e3", "e4"):  # counted already, for or against
        assert weigh(graph, "l1", "other", episode_id, agrees=True)["status"] == "exists"
        assert weigh(graph, "l1", "other", episode_id, agrees=False)["status"] == "exists"
    found = lesson(graph, "l1")
    assert (found["supported_by"], found["contradicted_by"]) == (["e1", "e2", "e3"], ["e4"])
    assert (found["support"], found["against"], found["weight"]) == (3, 1, 2)
    assert found["touched_at"] == when(22)
    check_lessons(graph)


def test_evidence_must_be_an_episode_that_ended(graph):
    learned(graph)
    for episode_id in ("open", "nope"):
        receipt = weigh(graph, "l1", "reviewer", episode_id, agrees=True)
        assert receipt["status"] == "missing"
    assert weigh(graph, "nope", "reviewer", "e3", agrees=True)["status"] == "unknown"
    assert lesson(graph, "l1")["support"] == 2
    assert sorted(f[0] for f in failures(graph)) == ["missing", "missing", "unknown"]
    check_lessons(graph)


def test_many_agents_weighing_one_lesson_lose_no_count(graph):
    learned(graph, supported_by=["e1"])
    statuses, start = [], threading.Barrier(8)

    def agent(name):
        own = connect().select_graph(graph.name)
        start.wait(timeout=30)
        for episode_id in ("e2", "e3", "e4", "e5", "e6"):
            statuses.append(weigh(own, "l1", name, episode_id, agrees=episode_id != "e4")["status"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in [pool.submit(agent, f"agent-{n}") for n in range(8)]:
            future.result()
    assert sorted(statuses) == ["exists"] * 35 + ["weighed"] * 5  # each episode counted once
    found = lesson(graph, "l1")
    assert (found["support"], found["against"]) == (5, 1)
    check_lessons(graph)


# --- use and outcome ------------------------------------------------------------------


def test_use_is_recorded_and_judged_once(graph):
    learned(graph, at=when(20))
    assert used(graph, "l1", "forecaster", "open", at=when(30)) == {"id": "l1", "status": "used"}
    assert used(graph, "l1", "forecaster", "open")["status"] == "exists"
    assert lesson(graph, "l1")["weight"] == 2  # used, not judged yet
    assert used(graph, "l1", "reviewer", "open", helped=True, at=when(40))["status"] == "judged"
    assert used(graph, "l1", "mallory", "open", helped=False)["status"] == "exists"  # said once
    found = lesson(graph, "l1")
    assert (found["used"], found["helped"], found["failed"], found["weight"]) == (1, 1, 0, 3)
    assert found["touched_at"] == when(40)
    judged = graph.ro_query(
        "MATCH (:Lesson)-[u:USED_IN]->(:Episode) RETURN u.by, u.helped, u.judged_by"
    )
    assert judged.result_set == [["forecaster", True, "reviewer"]]
    check_lessons(graph)


def test_use_that_did_not_help_lowers_the_weight(graph):
    learned(graph)
    assert used(graph, "l1", "forecaster", "e3", helped=False)["status"] == "used"
    assert used(graph, "l1", "forecaster", "e4", helped=False)["status"] == "used"
    assert used(graph, "l1", "forecaster", "e5", helped=True)["status"] == "used"
    found = lesson(graph, "l1")
    assert (found["used"], found["helped"], found["failed"], found["weight"]) == (3, 1, 2, 1)
    check_lessons(graph)


def test_use_in_an_episode_that_does_not_exist_is_refused(graph):
    learned(graph)
    assert used(graph, "l1", "forecaster", "nope")["status"] == "missing"
    assert used(graph, "nope", "forecaster", "e1")["status"] == "unknown"
    assert lesson(graph, "l1")["used"] == 0


# --- ranking and fading ---------------------------------------------------------------


def test_lessons_about_an_entity_come_heaviest_first(graph):
    learned(graph, "light", supported_by=["e1"], at=when(20))
    learned(graph, "heavy", supported_by=["e1", "e2", "e3"], at=when(21))
    learned(graph, "doubted", supported_by=["e1", "e2"], at=when(22))
    learned(graph, "elsewhere", supported_by=["e1"], about=[(DEVICE, "d2")])
    weigh(graph, "doubted", "reviewer", "e3", agrees=False, at=when(23))
    weigh(graph, "doubted", "reviewer", "e4", agrees=False, at=when(24))
    found = lessons_about(graph, DEVICE, "d1")
    assert [(x["id"], x["weight"]) for x in found] == [
        ("heavy", 3),
        ("light", 1),
    ]  # doubted weighs 0
    assert [x["id"] for x in lessons_about(graph, DEVICE, "d1", at_least=0)] == [
        "heavy",
        "light",
        "doubted",
    ]
    assert [x["id"] for x in lessons_about(graph, DEVICE, "d1", at_least=2)] == ["heavy"]
    assert [x["id"] for x in lessons_about(graph, DEVICE, "d2")] == ["elsewhere"]
    assert lessons_about(graph, DEVICE, "nope") == []


def test_equal_weight_goes_to_the_lesson_touched_last(graph):
    learned(graph, "a", supported_by=["e1"], at=when(20))
    learned(graph, "b", supported_by=["e1"], at=when(21))
    assert [x["id"] for x in lessons_about(graph, DEVICE, "d1")] == ["b", "a"]
    used(
        graph, "a", "forecaster", "e2", at=when(30)
    )  # used, not judged: same weight, touched later
    assert [x["id"] for x in lessons_about(graph, DEVICE, "d1")] == ["a", "b"]


def test_lesson_that_nothing_touches_fades(graph):
    learned(graph, "old", supported_by=["e1"], at=when(20))
    learned(graph, "kept", supported_by=["e1"], at=when(21))
    weigh(graph, "kept", "reviewer", "e2", agrees=True, at=when(100))
    assert [x["id"] for x in lessons_about(graph, DEVICE, "d1", since=when(50))] == ["kept"]
    assert [x["id"] for x in lessons_about(graph, DEVICE, "d1", since=when(21))] == ["kept"]
    assert [x["id"] for x in lessons_about(graph, DEVICE, "d1", since=when(20))] == ["kept", "old"]


def test_long_list_of_lessons_is_complete(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.read.PAGE", 3)
    for n in range(8):
        learned(graph, f"l{n}", supported_by=["e1"], at=when(20 + n))
    assert [x["id"] for x in lessons_about(graph, DEVICE, "d1")] == [
        f"l{n}" for n in range(7, -1, -1)
    ]


# --- retiring -------------------------------------------------------------------------


def test_retired_lesson_stays_with_its_evidence_and_is_no_longer_given_out(graph):
    learned(graph)
    assert retire(graph, "l1", "reviewer", "the fan was replaced", at=when(50)) == {
        "id": "l1",
        "status": "retired",
    }
    assert retire(graph, "l1", "mallory", "again")["status"] == "exists"
    assert (
        lessons_about(graph, DEVICE, "d1") == []
        and lessons_about(graph, DEVICE, "d1", at_least=-99) == []
    )
    found = lesson(graph, "l1")
    assert (found["retired_at"], found["retired_by"], found["retired_why"]) == (
        when(50),
        "reviewer",
        "the fan was replaced",
    )
    assert found["supported_by"] == ["e1", "e2"]
    assert weigh(graph, "l1", "reviewer", "e3", agrees=True)["status"] == "retired"
    assert used(graph, "l1", "forecaster", "e3")["status"] == "retired"
    assert retire(graph, "nope", "reviewer", "why")["status"] == "unknown"
    assert sorted(f[0] for f in failures(graph)) == ["retired", "retired", "unknown"]
    check_lessons(graph)


# --- with the rest of the memory ------------------------------------------------------


def test_entry_can_cite_the_lesson_it_used(graph):
    learned(graph)
    assert (
        record(graph, "open", "forecast", by="forecaster", cites=[("Lesson", "l1")])["status"]
        == "recorded"
    )
    assert episode(graph, "open")["entries"][0]["cites"] == [("Lesson", "l1")]
    assert (
        record(graph, "open", "forecast", by="forecaster", cites=[("Lesson", "nope")])["status"]
        == "missing"
    )


# --- what is refused ------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, "", 7, "a\x00b", " padded "])
def test_names_must_be_text(graph, bad):
    learned(graph)
    for call in (
        lambda: learn(graph, bad, "r", "s", ["e1"]),
        lambda: learn(graph, "l2", bad, "s", ["e1"]),
        lambda: weigh(graph, bad, "r", "e3", agrees=True),
        lambda: weigh(graph, "l1", bad, "e3", agrees=True),
        lambda: weigh(graph, "l1", "r", bad, agrees=True),
        lambda: used(graph, bad, "r", "e3"),
        lambda: used(graph, "l1", bad, "e3"),
        lambda: used(graph, "l1", "r", bad),
        lambda: retire(graph, bad, "r", "why"),
        lambda: retire(graph, "l1", bad, "why"),
        lambda: retire(graph, "l1", "r", bad),
        lambda: lesson(graph, bad),
    ):
        with pytest.raises(ValueError, match="must be text"):
            call()
    assert lesson(graph, "l1")["support"] == 2 and failures(graph) == []


@pytest.mark.parametrize("flag", [None, 1, 0, "yes", "True"])
def test_agreement_and_help_must_be_true_or_false(graph, flag):
    learned(graph)
    with pytest.raises(TypeError, match="agrees"):
        weigh(graph, "l1", "reviewer", "e3", agrees=flag)
    if flag is not None:
        with pytest.raises(TypeError, match="helped"):
            used(graph, "l1", "reviewer", "e3", helped=flag)
    assert lesson(graph, "l1")["weight"] == 2


@pytest.mark.parametrize("key", [None, {"a": 1}, "", "a\x00b"])
def test_read_with_a_key_of_a_wrong_form_is_refused(graph, key):
    with pytest.raises(ValueError, match="key"):
        lessons_about(graph, DEVICE, key)


def test_read_with_a_weight_or_time_of_a_wrong_form_is_refused(graph):
    for at_least in (1.5, "1", None, True):
        with pytest.raises(ValueError, match="at_least"):
            lessons_about(graph, DEVICE, "d1", at_least=at_least)
    with pytest.raises(ValueError):
        lessons_about(graph, DEVICE, "d1", since="soon")
    with pytest.raises(ValueError, match="since"):
        lessons_about(graph, DEVICE, "d1", since="")
