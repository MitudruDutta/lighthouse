"""What a hostile caller can try. Each test is an attack that worked, or could have, before
the library refused it. The rule for all of them: hostile input costs the attacker one
refused write, and costs nobody else anything."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from devices import DEVICE, count, failures, row, shape, when, write

from lighthouse import (
    add_task,
    as_of,
    claim,
    close_episode,
    complete,
    episode,
    episodes_about,
    history,
    open_episode,
    record,
    record_failure,
    related,
    remember,
)
from lighthouse.values import MAX_DETAIL, MAX_ITEMS, MAX_NAME, MAX_REFERENCES, MAX_TEXT, MAX_VALUES

INJECTIONS = [
    'x"}) MATCH (n) DETACH DELETE n //',
    "x'}) MATCH (n) DETACH DELETE n //",
    "x\\",
    'x\\"',
    '\\" }] MATCH (n) DETACH DELETE n RETURN 1 //',
    '" CYPHER a=1 MATCH (n) DETACH DELETE n //',
    "`x` $now ${now} {{x}} %s",
    "x) DETACH DELETE n",
    "'; DROP TABLE devices; --",
]
BAD_BYTES = {"NUL": "a\x00b", "lone surrogate": "a\ud800b"}


def deep(levels=100_000) -> dict:
    top = inner = {}
    for _ in range(levels):
        inner["a"] = {}
        inner = inner["a"]
    return top


def cyclic() -> dict:
    loop = {}
    loop["self"] = loop
    return loop


@pytest.fixture
def graph(graph):
    """A victim that honest writers keep up to date, and an open episode about it."""
    write(graph, row(key="victim", minute=0, status="true"))
    open_episode(graph, "ep", by="honest", about=[(DEVICE, "victim")], at=when(1))
    return graph


def victim_is_untouched(graph) -> bool:
    return [s["status"] for s in history(graph, DEVICE, "victim")] == ["true"]


# --- injection ------------------------------------------------------------------------


@pytest.mark.parametrize("text", INJECTIONS)
def test_query_text_in_a_value_is_stored_as_text(graph, text):
    before = shape(graph)[0]["Device"]
    assert write(graph, row(key="mallory", note=text, labels=[text, text])) == ["created"]
    assert record(graph, "ep", "observation", by="mallory", values={"note": text})["seq"] == 1
    stored = history(graph, DEVICE, "mallory")[0]
    assert stored["note"] == text and stored["labels"] == [text, text]
    assert episode(graph, "ep")["entries"][0]["note"] == text
    assert shape(graph)[0]["Device"] == before + 1 and victim_is_untouched(graph)


@pytest.mark.parametrize("text", INJECTIONS)
def test_query_text_in_a_key_an_id_or_a_name_is_stored_as_text(graph, text):
    assert write(graph, row(key=text, room=text, teams=[text])) == ["created"]
    assert related(graph, DEVICE, text, "LOCATED_IN") == [text]
    assert open_episode(graph, text, by=text, about=[(DEVICE, text)])["status"] == "opened"
    assert record(graph, text, text, by=text, cites=[(DEVICE, text)])["id"] == f"{text}/1"
    assert close_episode(graph, text, by=text, cites=[f"{text}/1"])["seq"] == 2
    assert [e["type"] for e in episode(graph, text)["entries"]] == [text, "outcome"]
    assert [e["id"] for e in episodes_about(graph, DEVICE, text)] == [text]
    assert add_task(graph, text, text, ref=text) is True
    assert claim(graph, text, text) == {"id": text, "kind": text, "ref": text, "until": None}
    assert complete(graph, text, text) is True
    assert victim_is_untouched(graph) and failures(graph) == []


@pytest.mark.parametrize("name", ["a b", "a`b", "a-b", "a.b", "a:b", "a}b", "a)b", "é", "", "1a"])
def test_property_name_that_is_not_a_plain_name_never_reaches_a_query(graph, name):
    assert write(graph, {"key": "mallory", "t": when(0), "values": {name: 1}}) == ["invalid"]
    assert record(graph, "ep", "observation", by="mallory", values={name: 1})["status"] == "invalid"
    assert count(graph, "(d:Device {serial: 'mallory'})") == 0 and victim_is_untouched(graph)


# --- bytes the database or the client cannot take -------------------------------------


@pytest.mark.parametrize("what", BAD_BYTES)
def test_bad_bytes_in_one_row_do_not_stop_the_other_rows(graph, what):
    # One NUL in one value made the database refuse the whole query: 499 honest rows lost.
    bad = BAD_BYTES[what]
    rows = [
        row(key="honest-1"),
        row(key="bad-value", note=bad),
        row(key="bad-list", notes=["fine", bad]),
        row(key=bad),
        row(key="bad-room", room=bad),
        row(key="bad-team", teams=["fine", bad]),
        row(key="honest-2"),
    ]
    assert write(graph, *rows) == ["created"] + ["invalid"] * 5 + ["created"]
    assert count(graph, "(d:Device) WHERE d.serial STARTS WITH 'honest'") == 2
    assert [f[0] for f in failures(graph)] == ["invalid"] * 5
    assert victim_is_untouched(graph)


@pytest.mark.parametrize("what", BAD_BYTES)
def test_bad_bytes_in_a_name_are_refused_before_any_query(graph, what):
    bad = BAD_BYTES[what]
    before = shape(graph)
    calls = [
        lambda: remember(graph, DEVICE, [row(key="x")], by=bad),
        lambda: open_episode(graph, bad, by="mallory"),
        lambda: open_episode(graph, "ep2", by=bad),
        lambda: record(graph, bad, "observation", by="mallory"),
        lambda: record(graph, "ep", bad, by="mallory"),
        lambda: record(graph, "ep", "observation", by=bad),
        lambda: close_episode(graph, "ep", by=bad),
        lambda: episode(graph, bad),
        lambda: add_task(graph, bad, "kind"),
        lambda: add_task(graph, "task", bad),
        lambda: add_task(graph, "task", "kind", ref=bad),
        lambda: claim(graph, bad, "kind"),
        lambda: claim(graph, "agent", bad),
        lambda: complete(graph, bad, "task"),
        lambda: complete(graph, "agent", bad),
        lambda: history(graph, DEVICE, bad),
        lambda: as_of(graph, DEVICE, bad, when(0)),
        lambda: related(graph, DEVICE, bad, "LOCATED_IN"),
        lambda: episodes_about(graph, DEVICE, bad),
        lambda: record_failure(graph, bad),
    ]
    for call in calls:
        with pytest.raises(ValueError):
            call()
    assert shape(graph) == before


@pytest.mark.parametrize("what", BAD_BYTES)
def test_bad_bytes_in_an_entry_are_refused_and_stored(graph, what):
    bad = BAD_BYTES[what]
    for hostile in ({"values": {"note": bad}}, {"cites": [bad]}, {"cites": [(DEVICE, bad)]}):
        assert record(graph, "ep", "observation", by="mallory", **hostile)["status"] == "invalid"
    assert open_episode(graph, "ep2", by="mallory", about=[(DEVICE, bad)])["status"] == "invalid"
    assert record(graph, "ep", "observation", by="honest")["id"] == "ep/1"
    stored = failures(graph)
    assert [f[0] for f in stored] == ["invalid"] * 4
    for failure in stored:  # what was kept of the hostile input can be read back
        assert "\x00" not in failure[3]
        failure[3].encode("utf-8")


# --- values that break the code that reports them -------------------------------------


@pytest.mark.parametrize("hostile", [deep, cyclic], ids=["100,000 levels deep", "contains itself"])
def test_value_that_cannot_be_printed_is_refused_without_a_crash(graph, hostile):
    # The error message printed the value. A deep or cyclic value raised RecursionError
    # from inside the error path, and the caller got a crash where a receipt was due.
    value = hostile()
    rows = [row(key="honest-1"), row(key="bad", note=value), row(key="honest-2")]
    assert write(graph, *rows) == ["created", "invalid", "created"]
    for arguments in (
        {"values": {"note": value}},
        {"values": value},
        {"cites": [value]},
        {"cites": value},
        {"at": value},
    ):
        assert record(graph, "ep", "observation", by="mallory", **arguments)["status"] == "invalid"
    assert open_episode(graph, "ep2", by="mallory", about=[value])["status"] == "invalid"
    assert open_episode(graph, "ep2", by="mallory", about=value)["status"] == "invalid"
    assert (
        write(graph, value, {"key": value, "t": when(0)}, {"key": "k", "t": value})
        == ["invalid"] * 3
    )
    assert all(len(f[3]) <= MAX_DETAIL for f in failures(graph))
    assert victim_is_untouched(graph)


# --- size -----------------------------------------------------------------------------

TOO_BIG = {
    "text value": lambda: row(key="big", note="x" * (MAX_TEXT + 1)),
    "list value": lambda: row(key="big", note=list(range(MAX_ITEMS + 1))),
    "number of values": lambda: row(key="big", **{f"p{i}": i for i in range(MAX_VALUES + 1)}),
    "relation targets": lambda: row(key="big", teams=[f"t{i}" for i in range(MAX_REFERENCES + 1)]),
    "key": lambda: row(key="k" * (MAX_NAME + 1)),
    "relation key": lambda: row(key="big", room="r" * (MAX_NAME + 1)),
    "row as a whole": lambda: row(key="big", **{f"p{i}": "x" * 50_000 for i in range(5)}),
}


@pytest.mark.parametrize("what", TOO_BIG)
def test_row_over_a_size_limit_is_refused(graph, what):
    assert write(graph, row(key="honest"), TOO_BIG[what]()) == ["created", "invalid"]
    assert count(graph, "(d:Device)") == 2 and count(graph, "(t:Team)") == 1
    ((reason, kind, _, detail),) = failures(graph)
    assert (reason, kind) == ("invalid", "Device") and len(detail) <= MAX_DETAIL


def test_row_at_every_size_limit_is_stored_and_does_not_hold_the_graph_for_long(graph):
    # One row with 20,000 relation targets held the write lock of the graph for 227 seconds.
    full = row(
        key="k" * MAX_NAME,
        room="r" * MAX_NAME,
        teams=[f"t{i}" for i in range(MAX_REFERENCES)],
        note="x" * MAX_TEXT,
        many=list(range(MAX_ITEMS)),
    )
    start = time.monotonic()
    assert write(graph, full) == ["created"]
    assert time.monotonic() - start < 5
    assert len(related(graph, DEVICE, "k" * MAX_NAME, "USED_BY")) == MAX_REFERENCES


def test_heavy_rows_are_sent_in_several_small_queries(graph):
    sent = []
    real = graph.query

    def counting(query, params=None, **options):
        if params and "rows" in params:
            sent.append(len(params["rows"]))
        return real(query, params, **options)

    graph.query = counting
    try:
        heavy = [
            row(key=f"h{i}", teams=[f"t{n}" for n in range(MAX_REFERENCES)]) for i in range(40)
        ]
        assert write(graph, *heavy) == ["created"] * 40
        light = [row(key=f"l{i}") for i in range(40)]
        assert write(graph, *light) == ["created"] * 40
    finally:
        del graph.query
    assert sum(sent) == 80 and sent[-1] == 40  # the light rows travel together
    assert len(sent) >= 5 and max(sent[:-1]) <= 10  # the heavy rows do not


def test_fingerprint_has_one_size_whatever_the_row_holds(graph):
    write(graph, row(key="small"), row(key="large", note="x" * MAX_TEXT))
    assert {len(s["fp"]) for key in ("small", "large") for s in history(graph, DEVICE, key)} == {64}


def test_failure_record_is_bounded_whatever_it_is_given(graph):
    huge = "x" * 10_000_000
    write(
        graph, row(key="bad", note={"x": huge}), row(key=huge), row(key="stale", note="y" * 50_000)
    )
    write(graph, row(key="stale", note="z" * 50_000))  # refused: same time, other content
    record(graph, "ep", "observation", by="mallory", values={"x": {"y": huge}}, cites=[huge])
    record_failure(graph, "manual", kind=huge, key=huge, detail=huge)
    record_failure(graph, "manual", kind={"a": 1}, key=cyclic(), detail=deep(1_000))
    record_failure(graph, "manual", detail="a\x00b\ud800c")
    stored = graph.ro_query(
        "MATCH (f:WriteFailure) RETURN f.reason, size(f.detail), f.kind, f.key, f.detail"
    ).result_set
    assert len(stored) == 7 and {f[0] for f in stored} == {"invalid", "conflict", "manual"}
    assert all(f[1] is None or f[1] <= MAX_DETAIL for f in stored)
    assert all(f[2] in (None, "Device", "Entry") for f in stored)  # a hostile kind is dropped
    assert all(f[3] in (None, "bad", "stale", "ep") for f in stored)  # and a hostile key
    assert any(f[4] == "a\\x00b\\ud800c" for f in stored)


# --- time -----------------------------------------------------------------------------


def soon(**ahead) -> datetime:
    return datetime.now(UTC) + timedelta(**ahead)


@pytest.mark.parametrize("ahead", [{"minutes": 6}, {"days": 1}, {"days": 365 * 7000}])
def test_row_dated_in_the_future_cannot_lock_an_entity(graph, ahead):
    # A row dated in the year 9999 became the current State. Every true row after it was
    # older, so it was refused as stale: one write froze the entity for good.
    poison = {"key": "victim", "t": soon(**ahead), "values": {"status": "false"}}
    assert write(graph, poison) == ["invalid"]
    assert write(
        graph, {"key": "victim", "t": soon(seconds=-1), "values": {"status": "newer"}}
    ) == ["changed"]
    assert [s["status"] for s in history(graph, DEVICE, "victim")] == ["true", "newer"]
    assert "future" in failures(graph)[0][3]


def test_row_within_the_clock_tolerance_is_stored(graph):
    assert write(
        graph, {"key": "victim", "t": soon(minutes=4), "values": {"status": "skewed"}}
    ) == ["changed"]


@pytest.mark.parametrize("ahead", [{"minutes": 6}, {"days": 365 * 7000}])
def test_entry_and_episode_dated_in_the_future_are_refused(graph, ahead):
    assert open_episode(graph, "ep2", by="mallory", at=soon(**ahead))["status"] == "invalid"
    assert record(graph, "ep", "observation", by="mallory", at=soon(**ahead))["status"] == "invalid"
    assert close_episode(graph, "ep", by="mallory", at=soon(**ahead))["status"] == "invalid"
    assert episode(graph, "ep2") is None and "closed_at" not in episode(graph, "ep")


# --- episodes -------------------------------------------------------------------------


def test_entry_with_too_many_references_or_too_much_content_is_refused(graph):
    many = [f"ep/{n}" for n in range(MAX_REFERENCES + 1)]
    assert record(graph, "ep", "observation", by="mallory", cites=many)["status"] == "invalid"
    about = [(DEVICE, f"d{n}") for n in range(MAX_REFERENCES + 1)]
    assert open_episode(graph, "ep2", by="mallory", about=about)["status"] == "invalid"
    large = {f"p{i}": "x" * 50_000 for i in range(5)}
    assert record(graph, "ep", "observation", by="mallory", values=large)["status"] == "invalid"
    assert episode(graph, "ep")["entries"] == [] and all(
        len(f[3]) <= MAX_DETAIL for f in failures(graph)
    )


def test_episode_cannot_grow_without_end(graph, monkeypatch):
    monkeypatch.setattr("lighthouse.episodes.MAX_ENTRIES", 3)
    for _ in range(3):
        assert record(graph, "ep", "observation", by="mallory")["status"] == "recorded"
    refused = record(graph, "ep", "observation", by="mallory", values={"n": 4})
    assert refused["status"] == "full" and refused["id"] is None
    assert close_episode(graph, "ep", by="honest")["status"] == "full"
    assert episode(graph, "ep")["entry_count"] == 3
    assert [f[0] for f in failures(graph)] == ["full", "full"]


# --- reads ----------------------------------------------------------------------------


@pytest.mark.parametrize("key", [None, {"a": 1}, ["victim"], 1.5, True, "", " victim", "x" * 201])
def test_read_with_a_key_of_a_wrong_form_is_refused(graph, key):
    for call in (
        lambda: history(graph, DEVICE, key),
        lambda: as_of(graph, DEVICE, key, when(0)),
        lambda: related(graph, DEVICE, key, "LOCATED_IN"),
        lambda: episodes_about(graph, DEVICE, key),
    ):
        with pytest.raises(ValueError, match="key"):
            call()


def test_long_reads_are_complete(graph, monkeypatch):
    # The database cuts a result at 10,000 rows and gives no sign.
    monkeypatch.setattr("lighthouse.read.PAGE", 3)
    write(
        graph,
        *(row(key="long", minute=m, level=m, teams=[f"t{n}" for n in range(8)]) for m in range(8)),
    )
    assert [s["level"] for s in history(graph, DEVICE, "long")] == list(range(8))
    assert related(graph, DEVICE, "long", "USED_BY") == [f"t{n}" for n in range(8)]
    for n in range(7):
        open_episode(graph, f"e{n}", by="honest", about=[(DEVICE, "long")], at=when(n))
    assert [e["id"] for e in episodes_about(graph, DEVICE, "long")] == [
        f"e{n}" for n in range(6, -1, -1)
    ]


# --- tasks ----------------------------------------------------------------------------


@pytest.mark.parametrize("ref", [{"a": 1}, ["x"], 1.5, "", "a\x00b", "x" * 201])
def test_task_reference_of_a_wrong_form_is_refused(graph, ref):
    with pytest.raises(ValueError, match="ref"):
        add_task(graph, "t1", "forecast", ref=ref)
    assert count(graph, "(t:Task)") == 0
