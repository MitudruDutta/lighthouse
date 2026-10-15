"""The port desk mapping. The versioning rules themselves are tested in lighthouse-memory."""

import gzip
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from feed import failures, poll, record, shape, statuses, when
from lighthouse import (
    as_of,
    between,
    connection,
    groups,
    history,
    important,
    pointing_at,
    related,
    search,
    similar,
)

from app.portcalls import BERTH, PORT_CALL, VESSEL, fetch, ingest, to_rows

# --- feed record to rows ----------------------------------------------------------------


def test_rows_keep_no_personal_or_free_text_field():
    assert "PERSONAL" not in json.dumps(to_rows(record(), "2026-10-12T10:00:00"))


def test_blank_and_zero_values_become_absent():
    rec = record(berth=" ", area=" ", prev=" ", next_port="", eta=None)
    rec["mmsi"] = 0
    rows = to_rows(rec, "2026-10-12T10:00:00")
    assert rows["berth"] is None and rows["vessel"]["values"]["mmsi"] is None
    assert rows["port_call"]["values"] == {
        "eta": None,
        "etd": None,
        "ata": None,
        "atd": None,
        "area": None,
        "areas": 1,
        "vessel_name": None,  # the ship has an IMO number: its name is on the Vessel
    }
    relations = rows["port_call"]["relations"]
    assert (relations["AT"], relations["CAME_FROM"], relations["BOUND_FOR"]) == (None, None, None)


def test_change_time_is_the_latest_timestamp_of_the_record():
    rec = record(minute=5)
    rec["portCallTimestamp"] = "2026-10-12T10:05:00.000Z"
    rec["portAreaDetails"][0]["etaTimestamp"] = "2026-10-12T10:05:07.943Z"
    assert to_rows(rec, "2026-10-12T11:00:00")["port_call"]["t"] == "2026-10-12T10:05:07"


def test_vessel_and_berth_rows_are_true_from_the_time_of_the_poll():
    rows = to_rows(record(minute=5), "2026-10-12T11:00:00")
    assert rows["vessel"]["t"] == rows["berth"]["t"] == "2026-10-12T11:00:00"


def test_berth_key_is_unique_across_ports_and_areas():
    keys = {
        to_rows(record(port=port, area=area, berth="1"), "2026-10-12T10:00:00")["berth"]["key"]
        for port in ("FIHEL", "FIKTK")
        for area in ("A", "B")
    }
    assert len(keys) == 4


def test_value_of_a_wrong_type_is_dropped():
    rec = record()
    rec["vesselTypeCode"], rec["mmsi"], rec["vesselName"] = {"a": "map"}, "230", ["list"]
    assert to_rows(rec, "2026-10-12T10:00:00")["vessel"]["values"] == {
        "name": None,
        "mmsi": None,
        "nationality": "FI",
        "type_code": None,
    }


def test_number_of_port_areas_is_kept():
    rec = record()
    rec["portAreaDetails"].append({"berthCode": "ZZ"})
    rows = to_rows(rec, "2026-10-12T10:00:00")
    assert rows["port_call"]["values"]["areas"] == 2 and rows["berth"]["values"]["code"] == "VC2"


# --- one poll -------------------------------------------------------------------------


def test_first_record_becomes_the_port_desk_graph(graph):
    receipts = poll(graph, 1, record())
    assert receipts == {
        "PortCall": [{"key": 1, "status": "created"}],
        "Vessel": [{"key": 9000001, "status": "created"}],
        "Berth": [{"key": "FIHEL/VUOS/VC2", "status": "created"}],
    }
    nodes, edges = shape(graph)
    assert nodes == {"PortCall": 1, "Vessel": 1, "Berth": 1, "Port": 3, "State": 3}
    assert edges == {
        "HAS_STATE": 3,
        "MADE_BY": 1,
        "CALLS_AT": 1,
        "AT": 1,
        "CAME_FROM": 1,
        "BOUND_FOR": 1,
        "IN": 1,
    }
    # From the ship to its port call, to the berth, to the port: one traversal.
    path = graph.ro_query(
        "MATCH (v:Vessel {imo: 9000001})<-[:MADE_BY]-(pc:PortCall)-[:AT]->(b:Berth)-[:IN]->(p:Port) "
        "RETURN v.name, pc.id, pc.eta, b.name, p.locode"
    ).result_set
    assert path == [["Test Ship", 1, when(600), "Berth VC2", "FIHEL"]]
    (state,) = history(graph, PORT_CALL, 1)
    assert state["valid_from"] == when(0) and state["by"] == "digitraffic"
    assert state["eta"] == when(600) and "ata" not in state
    assert history(graph, VESSEL, 9000001)[0]["valid_from"] == when(1)  # the time of the poll
    assert related(graph, PORT_CALL, 1, "CAME_FROM") == ["DETRV"]
    assert related(graph, PORT_CALL, 1, "BOUND_FOR") == ["FIKTK"]


def test_no_personal_data_reaches_the_graph(graph):
    bad = record(id=2, imo=0)
    poll(graph, 1, record(), bad)
    poll(graph, 9, record(minute=5, eta=700), record(minute=1, eta=1))
    everything = graph.ro_query("MATCH (n) RETURN properties(n)").result_set
    assert len(everything) > 8 and "PERSONAL" not in json.dumps(everything, default=str)


def test_same_poll_again_writes_nothing(graph):
    records = [record(id=1), record(id=2, berth="VA8"), record(id=3, imo=9000002)]
    poll(graph, 1, *records)
    before = shape(graph)
    again = poll(graph, 2, *records)
    assert statuses(again) == ["unchanged"] * 3
    assert set(statuses(again, VESSEL) + statuses(again, BERTH)) == {"unchanged"}
    assert shape(graph) == before and failures(graph) == []
    vessels = graph.ro_query("MATCH (v:Vessel) RETURN v.imo, v.name ORDER BY v.imo").result_set
    assert vessels == [[9000001, "Test Ship"], [9000002, "Test Ship"]]


def test_vessel_and_berth_shared_by_several_port_calls_are_stored_once(graph):
    receipts = poll(graph, 1, *(record(id=i) for i in range(1, 6)))
    assert statuses(receipts) == ["created"] * 5
    assert statuses(receipts, VESSEL) == ["created"] and statuses(receipts, BERTH) == ["created"]
    nodes, edges = shape(graph)
    assert nodes == {"PortCall": 5, "Vessel": 1, "Berth": 1, "Port": 3, "State": 7}
    assert edges["MADE_BY"] == 5 and edges["AT"] == 5 and edges["IN"] == 1
    assert failures(graph) == []


# --- a port call over time ------------------------------------------------------------


def test_feed_changes_become_history(graph):
    polls = [
        (1, record(minute=0, eta=600, berth="VC2")),
        (11, record(minute=10, eta=600, berth="VC2")),  # nothing changed
        (21, record(minute=20, eta=660, berth="VC2")),  # expected time moved
        (46, record(minute=45, eta=660, berth="VA8")),  # berth changed
        (671, record(minute=670, eta=660, berth="VA8", ata=665)),  # ship arrived
        (901, record(minute=900, eta=660, berth="VA8", ata=665, atd=890)),  # ship left
    ]
    seen = [statuses(poll(graph, minute, rec))[0] for minute, rec in polls]
    assert seen == ["created", "unchanged", "changed", "changed", "changed", "changed"]
    states = history(graph, PORT_CALL, 1)
    got = [
        (s["valid_from"], s.get("valid_to"), s["eta"], s.get("ata"), s.get("atd")) for s in states
    ]
    assert got == [
        (when(0), when(20), when(600), None, None),
        (when(20), when(45), when(660), None, None),
        (when(45), when(670), when(660), None, None),
        (when(670), when(900), when(660), when(665), None),
        (when(900), None, when(660), when(665), when(890)),
    ]
    berths = graph.ro_query(
        "MATCH (:PortCall {id: 1})-[o:AT]->(b:Berth) "
        "RETURN b.code, o.valid_from, o.valid_to ORDER BY o.valid_from"
    ).result_set
    assert berths == [["VC2", when(0), when(45)], ["VA8", when(45), None]]
    assert related(graph, PORT_CALL, 1, "AT", when(30)) == ["FIHEL/VUOS/VC2"]
    assert related(graph, PORT_CALL, 1, "AT") == ["FIHEL/VUOS/VA8"]
    # The vessel and the port did not change: one edge each, still open.
    fixed = graph.ro_query(
        "MATCH (:PortCall {id: 1})-[o:MADE_BY|CALLS_AT]->() RETURN type(o), o.valid_from, o.valid_to"
    ).result_set
    assert sorted(fixed) == [["CALLS_AT", when(0), None], ["MADE_BY", when(0), None]]
    assert failures(graph) == []


def test_berth_that_is_removed_closes_the_edge(graph):
    poll(graph, 1, record(minute=0, berth="VC2"))
    poll(graph, 6, record(minute=5, berth=None, area=None))
    assert related(graph, PORT_CALL, 1, "AT") == []
    assert related(graph, PORT_CALL, 1, "AT", when(3)) == ["FIHEL/VUOS/VC2"]
    assert "area" not in history(graph, PORT_CALL, 1)[1]


def test_vessel_that_is_renamed_keeps_its_old_name_in_history(graph):
    poll(graph, 1, record(minute=0, name="Old Name"))
    poll(graph, 50, record(minute=0, name="New Name"))
    names = [
        (s["name"], s["valid_from"], s.get("valid_to")) for s in history(graph, VESSEL, 9000001)
    ]
    assert names == [("Old Name", when(1), when(50)), ("New Name", when(50), None)]
    current = graph.ro_query("MATCH (v:Vessel) RETURN v.name").result_set
    assert current == [["New Name"]]
    assert history(graph, PORT_CALL, 1)[0].get("valid_to") is None  # the port call did not change


def test_older_record_goes_into_history_at_its_time(graph):
    poll(graph, 21, record(minute=20, eta=660))
    assert statuses(poll(graph, 22, record(minute=10, eta=999))) == ["inserted"]
    assert [state["eta"] for state in history(graph, PORT_CALL, 1)] == [when(999), when(660)]
    assert failures(graph) == []


def test_record_of_the_same_time_with_other_values_is_refused_and_stored(graph):
    poll(graph, 21, record(minute=20, eta=660))
    assert statuses(poll(graph, 22, record(minute=20, eta=999))) == ["conflict"]
    assert len(history(graph, PORT_CALL, 1)) == 1
    ((reason, kind, key, _),) = failures(graph)
    assert (reason, kind, key) == ("conflict", "PortCall", 1)


# --- recall ---------------------------------------------------------------------------


def test_ship_and_berth_are_found_by_name_and_port_calls_by_what_they_share(graph):
    poll(
        graph,
        1,
        record(id=1, imo=9000001, name="Nordic Star", berth="VC2", prev="DETRV"),
        record(id=2, imo=9000001, name="Nordic Star", berth="VA8", prev="DETRV"),
        record(id=3, imo=9000002, name="Star of Bothnia", berth="VC2", prev="SESTO"),
        record(id=4, imo=9000003, name="Aurora", berth="VA8", prev="EETLL"),
    )
    assert [v["key"] for v in search(graph, VESSEL, "nordic")] == [9000001]
    assert sorted(v["key"] for v in search(graph, VESSEL, "STAR")) == [9000001, 9000002]
    assert [b["key"] for b in search(graph, BERTH, "berth vc2")] == ["FIHEL/VUOS/VC2"]
    by_area = sorted(
        b["key"] for b in search(graph, BERTH, "area vuos")
    )  # the name of the port area
    assert by_area == ["FIHEL/VUOS/VA8", "FIHEL/VUOS/VC2"]
    # From the berth to the port calls at it, and from one port call to the ones like it.
    assert pointing_at(graph, PORT_CALL, "AT", "FIHEL/VUOS/VC2") == [1, 3]
    assert pointing_at(graph, PORT_CALL, "MADE_BY", 9000001) == [1, 2]
    alike = similar(graph, PORT_CALL, 1, relations=["MADE_BY", "AT", "CAME_FROM"])
    assert [(a["key"], a["shared"]) for a in alike] == [(2, 2), (3, 1)]
    assert alike[0]["through"] == [("CAME_FROM", "DETRV"), ("MADE_BY", 9000001)]


def test_graph_tells_what_is_busy_and_how_two_ships_are_connected(graph):
    poll(
        graph,
        1,
        record(id=1, imo=9000001, port="FIHEL", berth="VC2", prev="DETRV", next_port="SEGOT"),
        record(id=2, imo=9000002, port="FIHEL", berth="VA8", prev="EETLL", next_port="FIKTK"),
        record(
            id=3, imo=9000002, port="FIKTK", berth="K1", area="KTK", prev="FIHEL", next_port="X"
        ),
        record(
            id=4, imo=9000003, port="SESTO", berth="S1", area="STO", prev="PLGDN", next_port="Y"
        ),
        record(id=5, imo=9000003, port="FIHEL", berth="VC2", prev="SESTO", next_port="Z"),
    )
    # The port that most port calls are at.
    busiest = important(graph, [PORT_CALL], "CALLS_AT", limit=1)
    assert busiest[0]["entity"] == ("Port", "FIHEL")
    # A berth lies between the port calls at it and its port.
    berths = between(graph, [PORT_CALL], ["AT", "IN"], limit=2)
    assert berths == [
        {"entity": ("Berth", "FIHEL/VUOS/VC2"), "score": 2.0},
        {"entity": ("Berth", "FIHEL/VUOS/VA8"), "score": 1.0},
    ]
    # Two ships that never met at a berth were at the same port.
    steps = connection(
        graph, (VESSEL, 9000001), (VESSEL, 9000002), [PORT_CALL], ["MADE_BY", "CALLS_AT"]
    )
    assert [(step["relation"], step["forward"], step["to"], step["current"]) for step in steps] == [
        ("MADE_BY", False, ("PortCall", 1), True),
        ("CALLS_AT", True, ("Port", "FIHEL"), True),
        ("CALLS_AT", False, ("PortCall", 2), True),
        ("MADE_BY", True, ("Vessel", 9000002), True),
    ]
    at_a_berth = [PORT_CALL], ["MADE_BY", "AT"]
    assert connection(graph, (VESSEL, 9000001), (VESSEL, 9000002), *at_a_berth) is None
    shared = connection(graph, (VESSEL, 9000001), (VESSEL, 9000003), *at_a_berth)
    assert [step["to"] for step in shared][1] == ("Berth", "FIHEL/VUOS/VC2") and len(shared) == 4
    # Each ship with its port calls.
    fleets = groups(graph, [PORT_CALL], ["MADE_BY"])
    assert [fleet["size"] for fleet in fleets] == [3, 3, 2]
    assert set(fleets[2]["members"]) == {("Vessel", 9000001), ("PortCall", 1)}
    # A poll that changes only a time adds no relation: the answers are the ones kept.
    poll(graph, 2, record(id=1, minute=1, imo=9000001, berth="VC2", next_port="SEGOT", eta=700))
    assert between(graph, [PORT_CALL], ["AT", "IN"], limit=2) == berths
    assert important(graph, [PORT_CALL], "CALLS_AT", limit=1) == busiest


# --- records that cannot be stored ----------------------------------------------------


def test_record_that_cannot_be_mapped_stores_nothing_but_the_failure(graph):
    for unusable in (record(id=None), record(port=None)):
        assert statuses(poll(graph, 1, unusable)) == ["invalid"]
    assert shape(graph) == ({"WriteFailure": 2}, {})


def test_a_ship_without_an_imo_number_keeps_its_port_call_and_its_name(graph):
    for imo in (0, None):
        assert statuses(poll(graph, 1, record(id=7, imo=imo, name="Tug Seven"))) in (
            ["created"],
            ["unchanged"],
        )
    assert related(graph, PORT_CALL, 7, "MADE_BY") == []
    assert as_of(graph, PORT_CALL, 7, when(2))["vessel_name"] == "Tug Seven"
    assert graph.ro_query("MATCH (n:Vessel) RETURN count(n)").result_set == [[0]]
    assert failures(graph) == []
    # A ship with a number has its name on the Vessel, not on the port call.
    poll(graph, 2, record(id=8, imo=9000001, name="Nordic Star"))
    assert "vessel_name" not in as_of(graph, PORT_CALL, 8, when(3))


def test_invalid_records_are_stored_as_failures_and_do_not_block_valid_ones(graph):
    no_port = record(id=3, port=" ")
    bad_time = record(id=4)
    bad_time["portCallTimestamp"] = "yesterday"
    bad_eta = record(id=5)
    bad_eta["portAreaDetails"][0]["eta"] = "soon"
    no_id = record(id=None)
    records = [record(id=1), no_port, bad_time, bad_eta, "not a record", no_id]
    receipts = poll(graph, 1, *records)["PortCall"]
    assert [r["status"] for r in receipts] == ["created"] + ["invalid"] * 5
    assert [r["key"] for r in receipts] == [1, 3, 4, 5, None, None]
    assert all(r["reason"] for r in receipts[1:])
    stored = graph.ro_query("MATCH (pc:PortCall) RETURN pc.id").result_set
    assert stored == [[1]]
    found = failures(graph)
    assert [(f[0], f[1]) for f in found] == [("invalid", "PortCall")] * 5
    assert "PERSONAL" not in json.dumps(found)


# --- the feed is not trusted ----------------------------------------------------------


class Answer:
    """What urlopen() gives back, for a body we choose."""

    def __init__(self, body: bytes, encoding: str | None = None):
        self.body, self.headers = body, {"Content-Encoding": encoding} if encoding else {}

    def read(self, amount=-1):
        return self.body if amount < 0 else self.body[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *error):
        return False


def answered(monkeypatch, body: bytes, encoding: str | None = None):
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Answer(body, encoding))


def test_feed_answer_is_read_plain_or_packed(monkeypatch):
    feed = {"dataUpdatedTime": "2026-10-13T08:55:00Z", "portCalls": [record()]}
    body = json.dumps(feed).encode()
    answered(monkeypatch, body)
    assert fetch() == feed
    answered(monkeypatch, gzip.compress(body), "gzip")
    assert fetch() == feed


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://example.com/feed", "ftp://x/y", "/etc/passwd", ""]
)
def test_feed_is_read_over_https_only(monkeypatch, url):
    def opened(request, timeout):
        raise AssertionError("nothing may be opened")

    monkeypatch.setattr("urllib.request.urlopen", opened)
    with pytest.raises(ValueError, match="https"):
        fetch(url)


def test_feed_answer_that_unpacks_to_a_huge_body_is_refused(monkeypatch):
    monkeypatch.setattr("app.portcalls.MAX_FEED_BYTES", 10_000)
    bomb = gzip.compress(b"[" + b"0," * 5_000_000 + b"0]")  # 20 kB that holds 10 MB
    assert len(bomb) < 30_000
    answered(monkeypatch, bomb, "gzip")
    with pytest.raises(ValueError, match="larger than"):
        fetch()
    answered(monkeypatch, b"x" * 10_001)
    with pytest.raises(ValueError, match="larger than"):
        fetch()


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not json",
        b"[1, 2]",
        b'"text"',
        b"{}",
        b'{"portCalls": {"a": 1}}',
        b'{"portCalls": null}',
    ]
    + [b"[" * 100_000 + b"]" * 100_000],
)
def test_feed_answer_of_a_wrong_shape_is_refused(monkeypatch, body):
    answered(monkeypatch, body)
    with pytest.raises(ValueError, match="feed answer"):
        fetch()


def test_records_must_be_a_list(graph):
    for wrong in ({"a": 1}, "records", None, 7):
        with pytest.raises(TypeError, match="list"):
            ingest(graph, wrong)


def test_feed_clock_that_runs_ahead_does_not_date_rows_in_the_future(graph):
    receipts = ingest(graph, [record()], observed="2999-01-01T00:00:00Z")
    assert statuses(receipts) == ["created"] and statuses(receipts, VESSEL) == ["created"]
    seen = history(graph, VESSEL, 9000001)[0]["valid_from"]
    assert abs(datetime.now(UTC) - seen) < timedelta(seconds=10)
    time.sleep(1.1)  # the next poll comes at a later second
    assert statuses(ingest(graph, [record(name="Renamed")]), VESSEL) == ["changed"]  # not locked


HOSTILE = [
    'x"}) MATCH (n) DETACH DELETE n //',
    "a\x00b",
    "a\ud800b",
    "x" * 300_000,
    {"a": {"b": 1}},
    ["x"],
]


@pytest.mark.parametrize(
    "hostile", HOSTILE, ids=["query text", "NUL", "surrogate", "huge", "map", "list"]
)
def test_hostile_field_in_one_record_does_not_stop_the_other_records(graph, hostile):
    bad = record(id=2, imo=9000002, name=hostile, berth=hostile, prev=hostile, next_port=hostile)
    bad["nationality"] = hostile
    bad["portAreaDetails"][0]["portAreaName"] = hostile
    receipts = ingest(graph, [record(id=1), bad, record(id=3, imo=9000003)], observed=when(1))
    assert [r["status"] for r in receipts["PortCall"]][::2] == ["created", "created"]
    assert receipts["PortCall"][1]["status"] in ("created", "invalid")
    stored = graph.ro_query(
        "MATCH (pc:PortCall)-[:MADE_BY]->(v:Vessel) RETURN pc.id, v.name ORDER BY pc.id"
    )
    assert [row for row in stored.result_set if row[0] != 2] == [[1, "Test Ship"], [3, "Test Ship"]]
    assert all(len(f[3]) <= 2_000 for f in failures(graph))
