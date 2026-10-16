"""The schema of a graph, and the separation of tenants."""

import time
import types
import uuid

import pytest
from devices import (
    DEVICE,
    MANUAL,
    PERSON,
    ROOM,
    count,
    row,
    write,
)
from redis.exceptions import ResponseError

from lighthouse import (
    WORLD,
    Kind,
    add_task,
    ensure_schema,
    related,
    tenant,
    world,
)


def test_schema_covers_every_kind_and_the_kinds_they_point_at(graph):
    for _ in range(3):  # safe to apply again
        ensure_schema(graph, [DEVICE, PERSON])
    constraints = {(c["label"], c["properties"][0]): c["status"] for c in graph.list_constraints()}
    assert constraints == {
        key: "OPERATIONAL"
        for key in [
            ("Device", "serial"),
            ("Room", "code"),
            ("Team", "name"),
            ("Person", "email"),
            ("Manual", "code"),
            ("Task", "id"),
            ("Agent", "id"),
            ("Episode", "id"),
            ("Entry", "id"),
            ("Handoff", "id"),
            ("Lesson", "id"),
            ("Playbook", "id"),
            ("Session", "key"),
            ("Message", "key"),
            ("Reference", "key"),
        ]
    }


def test_schema_gives_a_graph_one_stamp_that_stays(graph, db):
    stamp = "MATCH (s:Stamp) RETURN s.id"
    [[first]] = graph.ro_query(stamp).result_set
    assert uuid.UUID(first).version == 4
    for kinds in ([DEVICE], [PERSON], []):
        ensure_schema(graph, kinds)
    assert graph.ro_query(stamp).result_set == [[first]]
    # A graph that is deleted and made again under its name is another graph.
    name = graph.name
    graph.delete()
    ensure_schema(db.select_graph(name), [DEVICE])
    [[second]] = graph.ro_query(stamp).result_set
    assert second != first


def test_schema_has_a_text_index_for_the_text_of_a_kind(graph):
    for _ in range(3):  # safe to apply again
        ensure_schema(graph, [MANUAL])
    indexed = graph.ro_query(
        "CALL db.indexes() YIELD label, types, status RETURN label, types, status"
    ).result_set
    manual = next(row for row in indexed if row[0] == "Manual")
    assert manual[1] == {"code": ["RANGE"], "words": ["FULLTEXT"]}  # the words of its text
    assert manual[2] == "OPERATIONAL"
    # The library's own: the words of a message, of an entry, and of every State of a kind
    # with text, and the user of a session.
    by_label = {row[0]: (row[1], row[2]) for row in indexed}
    assert by_label["Message"] == ({"key": ["RANGE"], "words": ["FULLTEXT"]}, "OPERATIONAL")
    entry = {"id": ["RANGE"], "serial": ["RANGE"], "words": ["FULLTEXT"]}
    assert (dict(by_label["Entry"][0]), by_label["Entry"][1]) == (entry, "OPERATIONAL")
    state = {"words": ["FULLTEXT"], "valid_from": ["RANGE"], "by": ["RANGE"]}
    assert (dict(by_label["State"][0]), by_label["State"][1]) == (state, "OPERATIONAL")
    episode = {"id": ["RANGE"], "opened_at": ["RANGE"], "closed_at": ["RANGE"]}
    assert (dict(by_label["Episode"][0]), by_label["Episode"][1]) == (episode, "OPERATIONAL")
    assert by_label["Session"] == ({"key": ["RANGE"], "user": ["RANGE"]}, "OPERATIONAL")
    assert by_label["Reference"] == ({"key": ["RANGE"]}, "OPERATIONAL")
    assert by_label["WriteFailure"] == ({"owner": ["RANGE"], "same": ["RANGE"]}, "OPERATIONAL")
    others = [row for row in indexed if row[0] not in ("Manual", "Message", "Entry", "State")]
    assert all("FULLTEXT" not in str(row[1]) for row in others)


def test_schema_has_a_vector_index_of_the_declared_size(graph):
    for _ in range(3):  # safe to apply again
        ensure_schema(graph, [MANUAL])
    index = graph.ro_query(
        "CALL db.indexes() YIELD label, types, options, status WHERE label = 'ManualVector' "
        "RETURN types, options.vector.dimension, options.vector.efRuntime, "
        "options.vector.similarityFunction, status"
    ).result_set
    assert index == [[{"vector": ["VECTOR"]}, 8, 100, "cosine", "OPERATIONAL"]]


def test_schema_stops_when_the_vector_index_has_another_size(graph):
    # A vector of another size is stored without an error and never found.
    resized = Kind("Manual", key="code", text=("title", "body"), dimensions=16)
    with pytest.raises(RuntimeError, match="indexed for 8 dimensions, not 16"):
        ensure_schema(graph, [resized])


def test_keys_are_found_right_after_the_schema_is_applied(db):
    # A node written while its index is being built is lost from the index. ensure_schema()
    # must not return before the indexes are ready. Without the wait, about one fresh graph
    # in four lost the first task: MATCH by id found nothing and MERGE broke the constraint.
    for kinds in [()] * 30 + [(DEVICE,)] * 10:
        graph = db.select_graph(f"test_{uuid.uuid4().hex}")
        try:
            ensure_schema(graph, kinds)
            indexes = graph.ro_query("CALL db.indexes() YIELD status RETURN DISTINCT status")
            assert indexes.result_set == [["OPERATIONAL"]]
            assert {c["status"] for c in graph.list_constraints()} == {"OPERATIONAL"}
            assert add_task(graph, "t1", "check") is True
            assert add_task(graph, "t1", "check") is False  # found by its key, not made again
            assert count(graph, "(t:Task {id: 't1'})") == 1
            assert write(graph, row(key="d1"), row(key="d2", room="r2")) == ["created"] * 2
            assert count(graph, "(d:Device {serial: 'd1'})") == 1
            assert write(graph, row(key="d1", minute=1, room="r2")) == ["changed"]
            assert count(graph, "(r:Room)") == 2
        finally:
            graph.delete()


class SlowIndexes:
    """A graph whose indexes report 'under construction' for the first `polls` checks."""

    def __init__(self, graph, polls: int):
        self.graph, self.left, self.asked = graph, polls, 0

    def __getattr__(self, name):
        return getattr(self.graph, name)

    def ro_query(self, query, *args, **kwargs):
        result = self.graph.ro_query(query, *args, **kwargs)
        if "db.indexes" in query:
            self.asked += 1
            if self.left > 0:
                self.left -= 1
                building = "[Indexing] 0/0: UNDER CONSTRUCTION"
                rows = [[row[0], building] for row in result.result_set]
                return types.SimpleNamespace(result_set=rows)
        return result


def test_schema_waits_until_every_index_is_ready(graph):
    slow = SlowIndexes(graph, polls=3)
    ensure_schema(slow, [DEVICE])
    assert slow.asked == 4  # three times not ready, then ready


def test_schema_gives_up_when_an_index_is_never_ready(graph):
    with pytest.raises(RuntimeError, match="schema not ready.*UNDER CONSTRUCTION"):
        ensure_schema(SlowIndexes(graph, polls=10**9), [DEVICE], wait_seconds=0.2)


def test_schema_fails_loudly_when_existing_data_breaks_a_key(db):
    graph = db.select_graph(f"test_{uuid.uuid4().hex}")
    try:
        graph.query("CREATE (:Device {serial: 'same'}), (:Device {serial: 'same'})")
        with pytest.raises(RuntimeError, match="schema not ready.*Device.*FAILED"):
            ensure_schema(graph, [DEVICE], wait_seconds=3)
    finally:
        graph.delete()


def test_one_label_with_two_keys_is_rejected(graph):
    with pytest.raises(ValueError, match="two different keys"):
        ensure_schema(graph, [ROOM, Kind("Room", key="number")])


def test_duplicate_key_fails_the_whole_query(graph):
    # The engine relies on this: a write query that fails stores nothing.
    ensure_schema(graph, [DEVICE])
    with pytest.raises(ResponseError, match="unique constraint"):
        graph.query("UNWIND ['a', 'b', 'b'] AS serial CREATE (:Device {serial: serial})")
    assert count(graph, "(d:Device)") == 0


@pytest.mark.parametrize(
    "tenant_id",
    ["", "World", "a b", "a:b", "a/b", "../world", "tenant:acme", "-acme", "a" * 64, None, 7, "é"],
)
def test_tenant_id_that_could_reach_another_graph_is_rejected(db, tenant_id):
    with pytest.raises(ValueError):
        tenant(db, tenant_id)


def test_tenant_graphs_are_separate_from_each_other_and_from_the_world(db):
    assert world(db).name == WORLD
    assert tenant(db, "world").name == "tenant:world"  # a tenant named "world" is not the world
    one, two = (tenant(db, f"test-{uuid.uuid4().hex}") for _ in range(2))
    try:
        for graph, team in ((one, "red"), (two, "blue")):
            ensure_schema(graph, [DEVICE])
            assert write(graph, row(teams=[team])) == ["created"]
        assert related(one, DEVICE, "d1", "USED_BY") == ["red"]
        assert related(two, DEVICE, "d1", "USED_BY") == ["blue"]
        assert count(one, "(t:Team)") == 1 and count(two, "(t:Team)") == 1
    finally:
        one.delete()
        two.delete()


@pytest.mark.parametrize("size", [-1, 4097, 8.0, "8", True])
def test_entry_vector_index_of_a_wrong_size_is_refused(graph, size):
    with pytest.raises(ValueError, match="entry_dimensions"):
        ensure_schema(graph, [MANUAL], entry_dimensions=size)


def test_entry_vector_index_of_another_size_stops_the_start(graph):
    ensure_schema(graph, [MANUAL], entry_dimensions=8)
    ensure_schema(graph, [MANUAL], entry_dimensions=8)  # safe to apply again
    with pytest.raises(RuntimeError, match="8 dimensions"):
        ensure_schema(graph, [MANUAL], entry_dimensions=16)


def test_a_schema_that_another_process_is_making_is_waited_for():
    from lighthouse.graphs import _create

    asked = []

    def busy_twice(label, prop):
        asked.append((label, prop))
        if len(asked) < 3:
            raise ResponseError("another write is in progress, retry the query")

    _create(busy_twice, "Task", "id", time.monotonic() + 5)
    assert asked == [("Task", "id")] * 3

    def always_busy(label, prop):
        raise ResponseError("another write is in progress, retry the query")

    with pytest.raises(ResponseError, match="in progress"):
        _create(always_busy, "Task", "id", time.monotonic())  # the deadline has passed

    def other(label, prop):
        raise ResponseError("something else")

    with pytest.raises(ResponseError, match="something else"):
        _create(other, "Task", "id", time.monotonic() + 5)


def notes(graph, count: int, episode="watch") -> list[str]:
    from lighthouse import open_episode, record

    open_episode(graph, episode, "eye")
    return [
        record(graph, episode, "observation", "eye", {"saw": f"n{n}"})["id"] for n in range(count)
    ]


def test_a_mark_is_kept_on_the_stamp(graph):
    from lighthouse.graphs import mark, set_mark

    assert mark(graph, "read_Device_x") is None
    set_mark(graph, "read_Device_x", 7)
    assert mark(graph, "read_Device_x") == 7
    for wrong in ("", "1x", "a-b", "a b", "s.id = 1 //", "x" * 101):
        with pytest.raises(ValueError, match="mark"):
            mark(graph, wrong)


def test_an_entry_job_reads_by_serial_in_slices_from_its_mark(graph, monkeypatch):
    from lighthouse import graphs
    from lighthouse.graphs import entries_after, entries_waiting, set_mark

    monkeypatch.setattr(graphs, "SLICE", 2)  # several slices for a few entries
    ids = notes(graph, 7)
    everything = "n.words IS NOT NULL"
    found, done = entries_after(graph, "job", everything, {}, 3)
    assert [n.properties["id"] for n in found] == ids[:3] and done == 3
    set_mark(graph, "job", done)
    assert entries_waiting(graph, done, everything, {}) == 4
    # A condition that keeps few: the slices go on until the end, and the mark with them.
    found, done = entries_after(graph, "job", "n.saw = 'n5'", {}, 3)
    assert [n.properties["id"] for n in found] == [ids[5]] and done == 7
    set_mark(graph, "job", done)
    assert entries_after(graph, "job", everything, {}, 3) == ([], 7)


def test_each_step_of_an_entry_job_reads_twice_the_serials_of_the_last(graph, monkeypatch):
    from lighthouse import graphs
    from lighthouse.graphs import entries_after

    monkeypatch.setattr(graphs, "SLICE", 2)
    notes(graph, 7)
    asked = []
    real = graph.ro_query

    def counted(query, params=None, **kw):
        asked.append(query)
        return real(query, params, **kw)

    monkeypatch.setattr(graph, "ro_query", counted)
    entries_after(graph, "job", "n.saw = 'n5'", {}, 3)
    reads = [q for q in asked if "n.serial > $start" in q]
    assert len(reads) == 3  # serials 1-2, 3-6, and 7: not 1-2, 3-4, 5-6, 7


def test_entries_and_messages_of_an_earlier_version_are_brought_up_to_date(graph):
    from lighthouse import said, say

    ids = notes(graph, 3)
    say(graph, "ann", "s", "user", "the pump leaks", by="ann")
    # As a graph that an earlier version wrote: no serials, no count, no word of the user.
    graph.query("MATCH (n:Entry) REMOVE n.serial")
    graph.query("MATCH (s:Stamp) REMOVE s.entries, s.messages_owned")
    graph.query("MATCH (m:Message) SET m.words = 'the pump leaks'")
    say(graph, "bob", "s", "user", "a valve", by="bob")  # stored with the word of its user
    graph.query(
        "MATCH (m:Message {user: 'bob'}) SET m.words = m.words + ' kept'"
    )  # what is already up to date is left as it is
    assert said(graph, "ann", "pump") == []
    ensure_schema(graph, [DEVICE])
    serials = graph.ro_query("MATCH (n:Entry) RETURN n.id, n.serial ORDER BY n.serial").result_set
    assert serials == [[entry_id, n] for n, entry_id in enumerate(ids, 1)]
    assert [m["text"] for m in said(graph, "ann", "pump")] == ["the pump leaks"]
    assert [m["text"] for m in said(graph, "bob", "kept")] == ["a valve"]
    notes(graph, 1, episode="later")  # the count goes on from there
    assert graph.ro_query("MATCH (s:Stamp) RETURN s.entries").result_set == [[4]]


def test_a_graph_without_a_stamp_keeps_no_mark(db):
    bare = db.select_graph(f"test_{uuid.uuid4().hex}")
    try:
        from lighthouse.graphs import mark, set_mark

        bare.query("CREATE (:Thing)")
        set_mark(bare, "read_x", "2026-01-01T00:00:00")
        assert mark(bare, "read_x") is None
    finally:
        bare.delete()
