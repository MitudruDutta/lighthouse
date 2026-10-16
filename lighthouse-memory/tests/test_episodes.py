"""Episodes: one order of entries, evidence that exists, and refusals that are stored."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import connect
from devices import DEVICE, ROOM, count, failures, row, when, write

from lighthouse import (
    Kind,
    add_task,
    as_of,
    claim,
    close_episode,
    episode,
    episodes_about,
    open_episode,
    record,
)


@pytest.fixture
def graph(graph):
    """Two devices in two rooms, known since minute 0."""
    write(graph, row(key="d1", room="r1"), row(key="d2", room="r2"))
    return graph


def started(graph, episode_id="ep1", about=((DEVICE, "d1"),)) -> str:
    assert open_episode(graph, episode_id, by="watcher", about=list(about), at=when(1)) == {
        "id": episode_id,
        "status": "opened",
    }
    return episode_id


def check_episodes(graph):
    """What must hold for every episode, whatever was written."""
    # The entries of an episode are numbered 1..n without a gap, and the counter agrees.
    numbering = graph.ro_query(
        "MATCH (ep:Episode) OPTIONAL MATCH (ep)-[:HAS]->(n:Entry) "
        "WITH ep, n ORDER BY n.seq RETURN ep.id, ep.entry_count, collect(n.seq), collect(n.id)"
    ).result_set
    for episode_id, counted, numbers, ids in numbering:
        assert numbers == list(range(1, counted + 1)), episode_id
        assert ids == [f"{episode_id}/{n}" for n in numbers]
    # One chain per episode, in the order of the numbers, and no entry outside an episode.
    entries = count(graph, "(n:Entry)")
    assert count(graph, "(:Episode)-[h:HAS]->(:Entry)", "h") == entries
    episodes_with_entries = sum(1 for row in numbering if row[1])
    assert count(graph, "(:Entry)-[x:NEXT]->(:Entry)", "x") == entries - episodes_with_entries
    assert count(graph, "(a:Entry)-[:NEXT]->(b:Entry) WHERE b.seq <> a.seq + 1") == 0
    crossing = "(p:Episode)-[:HAS]->(:Entry)-[:NEXT]->(:Entry)<-[:HAS]-(q:Episode)"
    assert count(graph, f"{crossing} WHERE p.id <> q.id") == 0
    # Every entry has one writer, and the edge agrees with the property.
    assert count(graph, "(:Agent)-[w:WROTE]->(:Entry)", "w") == entries
    assert count(graph, "(a:Agent)-[:WROTE]->(n:Entry) WHERE a.id <> n.by") == 0
    # A closed episode ends in its outcome, and only a closed episode has one.
    closed = count(graph, "(ep:Episode) WHERE ep.closed_at IS NOT NULL")
    assert count(graph, "(n:Entry {type: 'outcome'})") == closed
    last_is_outcome = (
        "(ep:Episode)-[:HAS]->(n:Entry {type: 'outcome'}) WHERE n.seq = ep.entry_count"
    )
    assert count(graph, last_is_outcome) == closed
    # Evidence is pinned to the time of the entry that cites it.
    assert count(graph, "(n:Entry)-[c:CITES]->() WHERE c.as_of <> n.at OR c.as_of IS NULL") == 0


# --- opening --------------------------------------------------------------------------


def test_open_makes_an_episode_about_its_entities(graph):
    started(graph, about=[(DEVICE, "d1"), (ROOM, "r2"), (DEVICE, "d2"), (DEVICE, "d1")])
    found = episode(graph, "ep1")
    assert found["about"] == [("Device", "d1"), ("Device", "d2"), ("Room", "r2")]
    assert (found["id"], found["by"], found["opened_at"]) == ("ep1", "watcher", when(1))
    assert found["entries"] == [] and found["entry_count"] == 0 and "closed_at" not in found
    assert count(graph, "(:Episode)-[a:ABOUT]->()", "a") == 3
    assert count(graph, "(:Episode)-[a:ABOUT]->(:Device {serial: 'd2'})", "a") == 1


def test_open_again_changes_nothing(graph):
    started(graph)
    again = open_episode(graph, "ep1", by="other", about=[(DEVICE, "d2")], at=when(9))
    assert again == {"id": "ep1", "status": "exists"}
    found = episode(graph, "ep1")
    assert (found["by"], found["opened_at"], found["about"]) == (
        "watcher",
        when(1),
        [("Device", "d1")],
    )
    assert count(graph, "(ep:Episode)") == 1 and failures(graph) == []


def test_open_without_entities(graph):
    started(graph, about=[])
    assert episode(graph, "ep1")["about"] == []


def test_open_about_something_unknown_is_refused_and_stored(graph):
    receipt = open_episode(graph, "ep1", by="watcher", about=[(DEVICE, "d1"), (ROOM, "nowhere")])
    assert receipt["status"] == "missing" and receipt["id"] is None
    assert episode(graph, "ep1") is None and count(graph, "(r:Room {code: 'nowhere'})") == 0
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("missing", "Episode", "ep1")
    assert "['Room', 'nowhere']" in detail  # what was refused


@pytest.mark.parametrize(
    "about",
    ["d1", [("Device", "d1")], [(DEVICE,)], [(DEVICE, None)], ["ep1/1"], [DEVICE], {"d1": 1}],
)
def test_open_with_references_of_a_wrong_form_is_refused(graph, about):
    receipt = open_episode(graph, "ep1", by="watcher", about=about)
    assert receipt["status"] == "invalid" and receipt["reason"]
    assert episode(graph, "ep1") is None and [f[0] for f in failures(graph)] == ["invalid"]


def test_open_at_a_time_that_is_not_a_time_is_refused(graph):
    assert open_episode(graph, "ep1", by="watcher", at="soon")["status"] == "invalid"
    assert episode(graph, "ep1") is None


# --- appending ------------------------------------------------------------------------


def test_entries_keep_the_order_they_were_written_in(graph):
    started(graph)
    first = record(graph, "ep1", "observation", by="watcher", values={"what": "moved"}, at=when(2))
    second = record(graph, "ep1", "forecast", by="forecaster", values={"late": 30}, at=when(1))
    third = record(graph, "ep1", "action", by="desk")
    assert [first, second] == [
        {"id": "ep1/1", "seq": 1, "status": "recorded"},
        {"id": "ep1/2", "seq": 2, "status": "recorded"},
    ]
    assert third["seq"] == 3
    entries = episode(graph, "ep1")["entries"]
    assert [(e["id"], e["type"], e["by"]) for e in entries] == [
        ("ep1/1", "observation", "watcher"),
        ("ep1/2", "forecast", "forecaster"),
        ("ep1/3", "action", "desk"),
    ]
    # The order is the order of writing, not the order of the times given.
    assert [e["at"] for e in entries[:2]] == [when(2), when(1)]
    assert (entries[0]["what"], entries[1]["late"]) == ("moved", 30)
    chain = graph.ro_query(
        "MATCH p = (first:Entry)-[:NEXT*0..]->(n:Entry) WHERE NOT ()-[:NEXT]->(first) "
        "RETURN n.id ORDER BY length(p)"
    ).result_set
    assert [r[0] for r in chain] == ["ep1/1", "ep1/2", "ep1/3"]
    check_episodes(graph)


def test_entry_values_of_every_storable_type_come_back(graph):
    started(graph)
    values = {"text": 'a "quote" \\ ☃', "whole": -7, "real": 2.5, "flag": False, "many": [1, 2]}
    record(graph, "ep1", "observation", by="watcher", values={**values, "nothing": None})
    entry = episode(graph, "ep1")["entries"][0]
    assert {k: entry[k] for k in values} == values and "nothing" not in entry


def test_each_writer_is_one_agent_shared_with_tasks(graph):
    started(graph)
    add_task(graph, "t1", "forecast")
    claim(graph, "forecaster", "forecast")
    record(graph, "ep1", "forecast", by="forecaster")
    record(graph, "ep1", "forecast", by="forecaster")
    record(graph, "ep1", "action", by="desk")
    agents = graph.ro_query(
        "MATCH (a:Agent) OPTIONAL MATCH (a)-[w:WROTE]->(:Entry) RETURN a.id, count(w) ORDER BY a.id"
    ).result_set
    assert agents == [["desk", 1], ["forecaster", 2]]
    check_episodes(graph)


def test_entries_of_two_episodes_do_not_mix(graph):
    started(graph, "ep1")
    started(graph, "ep2", about=[(DEVICE, "d2")])
    for episode_id in ("ep1", "ep2", "ep1", "ep2", "ep2"):
        record(graph, episode_id, "observation", by="watcher")
    assert [e["id"] for e in episode(graph, "ep1")["entries"]] == ["ep1/1", "ep1/2"]
    assert [e["id"] for e in episode(graph, "ep2")["entries"]] == ["ep2/1", "ep2/2", "ep2/3"]
    check_episodes(graph)


# --- evidence -------------------------------------------------------------------------


def test_entry_cites_earlier_entries_and_entities(graph):
    started(graph)
    record(graph, "ep1", "observation", by="watcher", cites=[(DEVICE, "d1")], at=when(5))
    cites = ["ep1/1", (DEVICE, "d2"), (ROOM, "r1"), (DEVICE, "d2"), "ep1/1"]
    record(graph, "ep1", "forecast", by="forecaster", cites=cites, at=when(7))
    first, second = episode(graph, "ep1")["entries"]
    assert first["cites"] == [("Device", "d1")]
    assert second["cites"] == [("Device", "d2"), ("Entry", "ep1/1"), ("Room", "r1")]
    assert count(graph, "(:Entry {id: 'ep1/2'})-[c:CITES]->()", "c") == 3  # no doubles
    assert count(graph, "(:Entry {id: 'ep1/2'})-[c:CITES]->(:Entry {id: 'ep1/1'})", "c") == 1
    check_episodes(graph)


def test_cited_entity_can_be_read_as_the_agent_saw_it(graph):
    started(graph)
    record(graph, "ep1", "observation", by="watcher", cites=[(DEVICE, "d1")], at=when(5))
    write(graph, row(key="d1", minute=10, status="hot", room="r9"))  # the device changes later
    cited = graph.ro_query(
        "MATCH (:Entry {id: 'ep1/1'})-[c:CITES]->(d:Device) RETURN c.key, c.as_of, d.status"
    ).result_set
    assert cited == [["d1", when(5), "hot"]]  # the node shows what is true now
    assert as_of(graph, DEVICE, "d1", cited[0][1])["status"] == "ok"  # what was true then


def test_entry_that_cites_something_unknown_is_refused_and_stored(graph):
    started(graph)
    record(graph, "ep1", "observation", by="watcher")
    for cites in (["ep1/9"], [(DEVICE, "nope")], ["ep1/1", (DEVICE, "d1"), (ROOM, "nowhere")]):
        receipt = record(graph, "ep1", "forecast", by="forecaster", values={"x": 1}, cites=cites)
        assert receipt == {
            "id": None,
            "status": "missing",
            "reason": "something it refers to does not exist",
        }
    assert [e["id"] for e in episode(graph, "ep1")["entries"]] == ["ep1/1"]  # no number was used
    assert record(graph, "ep1", "forecast", by="forecaster")["id"] == "ep1/2"
    found = failures(graph)
    assert [(f[0], f[1], f[2]) for f in found] == [("missing", "Entry", "ep1")] * 3
    assert all("'type': 'forecast'" in f[3] and "'x': 1" in f[3] for f in found)
    assert any("['Room', 'nowhere']" in f[3] for f in found)
    assert count(graph, "(r:Room {code: 'nowhere'})") == 0
    check_episodes(graph)


def test_entry_may_cite_an_entry_of_another_episode(graph):
    started(graph, "past")
    record(graph, "past", "observation", by="watcher")
    started(graph, "now", about=[(DEVICE, "d2")])
    assert (
        record(graph, "now", "forecast", by="forecaster", cites=["past/1"])["status"] == "recorded"
    )
    assert episode(graph, "now")["entries"][0]["cites"] == [("Entry", "past/1")]


def test_one_label_cited_with_two_keys_is_refused(graph):
    started(graph)
    other = Kind("Device", key="number")
    receipt = record(graph, "ep1", "forecast", by="f", cites=[(DEVICE, "d1"), (other, 7)])
    assert receipt["status"] == "invalid" and "two different keys" in receipt["reason"]


# --- refusals -------------------------------------------------------------------------


def test_entry_for_an_episode_that_does_not_exist_is_refused_and_stored(graph):
    receipt = record(graph, "nope", "observation", by="watcher", values={"what": "moved"})
    assert receipt == {"id": None, "status": "unknown", "reason": "the episode does not exist"}
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("unknown", "Entry", "nope") and "'what': 'moved'" in detail
    assert count(graph, "(n:Entry)") == 0 and count(graph, "(a:Agent)") == 0


INVALID_ENTRIES = {
    "map as a value": {"values": {"a": {"b": 1}}},
    "values not a map": {"values": ["a"]},
    "unsafe value name": {"values": {"a b": 1}},
    "value named like the entry id": {"values": {"id": "x"}},
    "value named like the type": {"values": {"type": "x"}},
    "value named like the writer": {"values": {"by": "x"}},
    "value named like the citations": {"values": {"cites": "x"}},
    "not a number": {"values": {"a": float("nan")}},
    "cites not a list": {"cites": "ep1/1"},
    "citation of a wrong form": {"cites": [("Device", "d1")]},
    "citation of a record that cannot be cited": {"cites": [("Handoff", "h1")]},
    "citation with three parts": {"cites": [(DEVICE, "d1", "extra")]},
    "empty citation": {"cites": [""]},
    "time that is not a time": {"at": "soon"},
}


@pytest.mark.parametrize("name", INVALID_ENTRIES)
def test_invalid_entry_is_refused_and_stored(graph, name):
    started(graph)
    receipt = record(graph, "ep1", "observation", by="watcher", **INVALID_ENTRIES[name])
    assert receipt["status"] == "invalid" and receipt["id"] is None and receipt["reason"]
    if name == "citation with three parts":
        assert "not a reference" in receipt["reason"]
    assert episode(graph, "ep1")["entries"] == []
    ((reason, kind, key, detail),) = failures(graph)
    assert (reason, kind, key) == ("invalid", "Entry", "ep1") and receipt["reason"] in detail


@pytest.mark.parametrize("bad", [None, "", 7])
def test_names_must_be_text(graph, bad):
    started(graph)
    for call in (
        lambda: open_episode(graph, bad, by="w"),
        lambda: open_episode(graph, "ep2", by=bad),
        lambda: record(graph, bad, "observation", by="w"),
        lambda: record(graph, "ep1", bad, by="w"),
        lambda: record(graph, "ep1", "observation", by=bad),
        lambda: close_episode(graph, "ep1", by=bad),
    ):
        with pytest.raises(ValueError, match="must be text"):
            call()
    assert count(graph, "(n:Entry)") == 0 and count(graph, "(ep:Episode)") == 1


def test_database_error_is_stored_and_reported(graph, monkeypatch):
    started(graph)
    with monkeypatch.context() as patch:
        patch.setattr(
            "lighthouse.episodes._append_query", lambda kinds: "RETURN no_such_function()"
        )
        patch.setattr("lighthouse.episodes._open_query", lambda kinds: "RETURN no_such_function()")
        receipts = [record(graph, "ep1", "observation", by="w"), open_episode(graph, "ep2", by="w")]
    assert [r["status"] for r in receipts] == ["failed", "failed"]
    assert all("no_such_function" in r["reason"] for r in receipts)
    assert sorted((f[0], f[1], f[2]) for f in failures(graph)) == [
        ("failed", "Entry", "ep1"),
        ("failed", "Episode", "ep2"),
    ]
    assert record(graph, "ep1", "observation", by="w")["id"] == "ep1/1"


# --- closing --------------------------------------------------------------------------


def test_close_records_the_outcome_as_the_last_entry(graph):
    started(graph)
    record(graph, "ep1", "forecast", by="forecaster", values={"late": 30})
    receipt = close_episode(
        graph, "ep1", by="reviewer", outcome={"late": 25}, cites=["ep1/1"], at=when(60)
    )
    assert receipt == {"id": "ep1/2", "seq": 2, "status": "recorded"}
    found = episode(graph, "ep1")
    assert found["closed_at"] == when(60)
    last = found["entries"][-1]
    assert (last["type"], last["by"], last["late"], last["cites"]) == (
        "outcome",
        "reviewer",
        25,
        [("Entry", "ep1/1")],
    )
    check_episodes(graph)


def test_closed_episode_takes_no_more_entries(graph):
    started(graph)
    close_episode(graph, "ep1", by="reviewer", outcome={"late": 25})
    refused = {"id": None, "status": "closed", "reason": "the episode is closed"}
    assert record(graph, "ep1", "action", by="desk", values={"what": "too late"}) == refused
    assert close_episode(graph, "ep1", by="reviewer", outcome={"late": 99}) == refused
    found = episode(graph, "ep1")
    assert [e["type"] for e in found["entries"]] == ["outcome"] and found["entries"][0][
        "late"
    ] == 25
    assert [(f[0], f[1], f[2]) for f in failures(graph)] == [("closed", "Entry", "ep1")] * 2
    assert any("'what': 'too late'" in f[3] for f in failures(graph))
    check_episodes(graph)


def test_close_without_an_outcome_value(graph):
    started(graph)
    assert close_episode(graph, "ep1", by="reviewer")["status"] == "recorded"
    assert episode(graph, "ep1")["entries"][0]["type"] == "outcome"
    check_episodes(graph)


def test_close_that_is_refused_leaves_the_episode_open(graph):
    started(graph)
    assert close_episode(graph, "ep1", by="reviewer", cites=["ep1/9"])["status"] == "missing"
    assert (
        close_episode(graph, "ep1", by="reviewer", outcome={"a": {"b": 1}})["status"] == "invalid"
    )
    assert "closed_at" not in episode(graph, "ep1")
    assert record(graph, "ep1", "action", by="desk")["status"] == "recorded"
    check_episodes(graph)


def test_outcome_cannot_be_recorded_without_closing(graph):
    started(graph)
    with pytest.raises(ValueError, match="close_episode"):
        record(graph, "ep1", "outcome", by="reviewer")
    assert episode(graph, "ep1")["entries"] == []


# --- reading --------------------------------------------------------------------------


def test_episode_that_does_not_exist_reads_as_none(graph):
    assert episode(graph, "nope") is None


def test_episodes_about_an_entity_newest_first_with_their_outcome(graph):
    for n, episode_id in enumerate(("old", "mid", "new"), start=1):
        open_episode(
            graph, episode_id, by="watcher", about=[(DEVICE, "d1"), (ROOM, "r1")], at=when(n)
        )
    open_episode(graph, "other", by="watcher", about=[(DEVICE, "d2")], at=when(9))
    record(graph, "old", "forecast", by="forecaster", values={"late": 30})
    close_episode(graph, "old", by="reviewer", outcome={"late": 25})
    record(graph, "mid", "forecast", by="forecaster")
    found = episodes_about(graph, DEVICE, "d1")
    assert [(e["id"], e["entry_count"]) for e in found] == [("new", 0), ("mid", 1), ("old", 2)]
    assert [e["outcome"] and e["outcome"]["late"] for e in found] == [None, None, 25]
    assert found[2]["outcome"]["id"] == "old/2" and "closed_at" in found[2]
    assert [e["id"] for e in episodes_about(graph, ROOM, "r1")] == ["new", "mid", "old"]
    assert [e["id"] for e in episodes_about(graph, DEVICE, "d2")] == ["other"]
    assert episodes_about(graph, DEVICE, "nope") == [] and episodes_about(graph, ROOM, "r2") == []


# --- many writers ---------------------------------------------------------------------


def test_many_agents_writing_into_one_episode_get_one_order(graph):
    started(graph)
    receipts = []

    def agent(name):
        own = connect().select_graph(graph.name)
        for n in range(12):
            cites = [(DEVICE, "d1")] if n % 2 else []
            receipts.append(
                record(own, "ep1", "observation", by=name, values={"n": n}, cites=cites)
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in [pool.submit(agent, f"agent-{n}") for n in range(8)]:
            future.result()
    assert {r["status"] for r in receipts} == {"recorded"}
    assert sorted(r["seq"] for r in receipts) == list(range(1, 97))  # every place taken once
    serials = graph.ro_query("MATCH (n:Entry) RETURN n.serial ORDER BY n.serial").result_set
    assert [s for (s,) in serials] == list(range(1, 97))  # and every serial of the graph
    assert graph.ro_query("MATCH (s:Stamp) RETURN s.entries").result_set == [[96]]
    assert count(graph, "(a:Agent)") == 8
    check_episodes(graph)


def test_close_while_others_write_ends_the_episode_at_the_outcome(graph):
    started(graph)
    receipts = []

    def writer(name):
        own = connect().select_graph(graph.name)
        for _ in range(15):
            receipts.append(record(own, "ep1", "observation", by=name))

    def closer():
        own = connect().select_graph(graph.name)
        receipts.append(close_episode(own, "ep1", by="reviewer", outcome={"done": True}))

    with ThreadPoolExecutor(max_workers=7) as pool:
        futures = [pool.submit(writer, f"agent-{n}") for n in range(6)]
        futures.insert(3, pool.submit(closer))
        for future in futures:
            future.result()
    assert {r["status"] for r in receipts} <= {"recorded", "closed"}
    recorded = [r for r in receipts if r["status"] == "recorded"]
    found = episode(graph, "ep1")
    assert len(found["entries"]) == len(recorded) == found["entry_count"]
    assert found["entries"][-1]["type"] == "outcome"
    refused = len(receipts) - len(recorded)
    assert [f[0] for f in failures(graph)] == ["closed"] * refused
    check_episodes(graph)


def test_entry_cites_another_episode_and_an_entry_by_its_label(graph):
    started(graph, "past")
    record(graph, "past", "observation", by="watcher")
    started(graph, "now", about=[(DEVICE, "d2")])
    cites = [("Episode", "past"), ("Entry", "past/1"), "past/1"]
    assert record(graph, "now", "forecast", by="forecaster", cites=cites)["status"] == "recorded"
    entry = episode(graph, "now")["entries"][0]
    assert entry["cites"] == [("Entry", "past/1"), ("Episode", "past")]
    # What an entry cites can be given back as references as it is.
    assert record(graph, "now", "action", by="desk", cites=entry["cites"])["status"] == "recorded"
    assert (
        record(graph, "now", "action", by="desk", cites=[("Episode", "nope")])["status"]
        == "missing"
    )
    check_episodes(graph)


def test_episode_is_about_entities_only(graph):
    started(graph, "past")
    for about in ([("Episode", "past")], [("Entry", "past/1")], ["past/1"]):
        assert open_episode(graph, "now", by="watcher", about=about)["status"] == "invalid"
    assert episode(graph, "now") is None


def test_an_entry_is_read_without_its_serial_and_its_words(graph):
    started(graph)
    record(graph, "ep1", "observation", by="watcher", values={"saw": "the pump is hot"})
    close_episode(graph, "ep1", by="reviewer", outcome={"note": "it cooled"})
    found = episode(graph, "ep1")
    assert all("serial" not in e and "words" not in e for e in found["entries"])
    stored = graph.ro_query("MATCH (n:Entry) RETURN n.serial ORDER BY n.serial").result_set
    assert stored == [[1], [2]]  # it is there, for the jobs that read entries
    outcome = episodes_about(graph, DEVICE, "d1")[0]["outcome"]
    assert "serial" not in outcome and outcome["note"] == "it cooled"
