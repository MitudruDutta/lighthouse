"""Ports of the world: PortWatch's days become the history of each port, joined to the port
call feed by the UN/LOCODE. The service here is a stand-in with the shape of the real one."""

import math
import re

import pytest
from fastapi.testclient import TestClient
from feed import poll, record
from lighthouse import as_of, close_episode, history, learn, open_episode

from app import portwatch
from app.api import get_graph
from app.main import app
from app.portcalls import PORT


def port(id, name, iso3, locode=None, lat=10.0, lon=20.0, continent="Asia & Pacific") -> dict:
    return {
        "portid": id,
        "portname": name,
        "country": {"IND": "India", "FIN": "Finland", "CHN": "China"}.get(iso3, iso3),
        "ISO3": iso3,
        "continent": continent,
        "lat": lat,
        "lon": lon,
        "LOCODE": locode,
    }


def day(id, date, calls, name="", iso3="IND", **more) -> dict:
    return {
        "date": date,
        "portid": id,
        "portname": name,
        "country": "",
        "ISO3": iso3,
        "portcalls": calls,
        "portcalls_container": more.get("container", 0),
        "portcalls_dry_bulk": 0,
        "portcalls_general_cargo": 0,
        "portcalls_roro": 0,
        "portcalls_tanker": more.get("tanker", 0),
        "import": more.get("imported", 0),
        "export": more.get("exported", 0),
    }


class Service:
    """Answers as PortWatch's ArcGIS service does: pages, a newest day, and errors."""

    def __init__(self, ports, days):
        self.ports, self.days, self.asked = ports, days, []

    def __call__(self, url, what, headers=None, params=None):
        self.asked.append((url, dict(params)))
        if "outStatistics" in params:
            newest = max(d["date"] for d in self.days if d.get("date"))
            return {"features": [{"attributes": {"d": newest}}]}
        if url == portwatch.PORTS_URL:
            rows = self.ports
        else:
            (wanted,) = re.fullmatch(r"date = DATE '(.*)'", params["where"]).groups()
            rows = [d for d in self.days if d.get("date") in (wanted, None)]
        start, count = params["resultOffset"], params["resultRecordCount"]
        page = rows[start : start + count]
        return {
            "features": [{"attributes": row} for row in page],
            "exceededTransferLimit": start + count < len(rows),
        }


PORTS = [
    port("port1", "Mumbai (Nhava Sheva)", "IND", "IN NSA", lat=18.9, lon=72.9),
    port("port2", "Chennai", "IND"),  # no UN/LOCODE
    port("port3", "Helsinki", "FIN", "FI HEL", lat=60.1, lon=24.9, continent="Europe"),
    port("port4", "Qingdao", "CHN", "CN QDG"),
    port("port5", "Qingdao Old Harbour", "CHN", "CN QDG"),  # the same UN/LOCODE again
    port("port6", "Valparaiso", "CHL", "CL VAP", lat=-33.0, lon=-71.6),
]


def days(*dates) -> list[dict]:
    rows = []
    for n, date in enumerate(dates):
        rows += [
            day("port1", date, 30 + n, "Mumbai (Nhava Sheva)", container=9, imported=346755.5),
            day("port2", date, 12, "Chennai"),
            day("port3", date, 5, "Helsinki", "FIN"),
            day("port4", date, 600, "Qingdao", "CHN"),
            day("port5", date, 3, "Qingdao Old Harbour", "CHN"),
            day("port6", date, 4, "Valparaiso", "CHL"),
        ]
    return rows


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(portwatch, "PAGE", 4)  # several pages for six ports
    return Service(PORTS, days("2026-10-07", "2026-10-08", "2026-10-09"))


def test_first_read_takes_the_last_days_that_portwatch_has(graph, service):
    summary = portwatch.update(graph, service, backfill=2)
    assert summary["days"] == ["2026-10-08", "2026-10-09"]  # not the days before
    assert summary["ports"] == 6 and summary["rows"] == {"created": 6, "changed": 1, "unchanged": 5}
    mumbai = history(graph, PORT, "INNSA")
    assert [(s["valid_from"].date().isoformat(), s["calls"]) for s in mumbai] == [
        ("2026-10-08", 31),
        ("2026-10-09", 32),
    ]
    last = mumbai[-1]
    assert (last["name"], last["country"], last["iso3"]) == ("Mumbai (Nhava Sheva)", "India", "IND")
    assert (last["calls_container"], last["import_tonnes"], last["continent"]) == (
        9,
        346755.5,
        "Asia & Pacific",
    )
    assert (last["lat"], last["lon"], last["portwatch"]) == (18.9, 72.9, "port1")


def test_ports_are_keyed_by_their_locode_or_their_portwatch_id(graph, service):
    portwatch.update(graph, service, backfill=1)
    found = dict(graph.ro_query("MATCH (p:Port) RETURN p.portwatch, p.locode").result_set)
    assert found == {
        "port1": "INNSA",
        "port2": "portwatch:port2",  # Chennai has no UN/LOCODE in PortWatch
        "port3": "FIHEL",
        "port4": "CNQDG",
        "port5": "portwatch:port5",  # the second port with the same UN/LOCODE
        "port6": "CLVAP",
    }
    valparaiso = as_of(graph, PORT, "CLVAP", "2026-10-09T12:00:00Z")
    assert (valparaiso["lat"], valparaiso["lon"]) == (-33.0, -71.6)  # south and west stay


def test_each_read_takes_only_the_days_after_the_last(graph, service):
    portwatch.update(graph, service, backfill=1)
    assert portwatch.update(graph, service)["days"] == []
    service.days += days("2026-10-10")
    again = portwatch.update(graph, service)
    assert again["days"] == ["2026-10-10"] and portwatch.newest(graph) == "2026-10-10"
    asked = [p["where"] for url, p in service.asked if url == portwatch.DAYS_URL and "where" in p]
    assert asked[-1] == "date = DATE '2026-10-10'"
    ports_read = sum(url == portwatch.PORTS_URL for url, _ in service.asked)
    portwatch.update(graph, service)  # no new day: the list of ports is not read
    assert sum(url == portwatch.PORTS_URL for url, _ in service.asked) == ports_read


def test_rejected_writes_hold_the_checkpoint_and_retry_before_newer_days(
    graph, service, monkeypatch
):
    real_remember = portwatch.remember
    rejected = False

    def fail_once(graph, kind, rows, by):
        nonlocal rejected
        if rows[0]["t"].startswith("2026-10-08") and not rejected:
            rejected = True
            # A partial day is already present when the next import retries it.
            first = real_remember(graph, kind, rows[:1], by)
            return first + [{"key": row["key"], "status": "failed"} for row in rows[1:]]
        return real_remember(graph, kind, rows, by)

    monkeypatch.setattr(portwatch, "remember", fail_once)
    summary = portwatch.update(graph, service, backfill=3)
    assert summary["days"] == ["2026-10-07"]
    assert summary["pending_days"] == ["2026-10-08", "2026-10-09"]
    assert portwatch.newest(graph) == "2026-10-07"
    assert history(graph, PORT, "INNSA")[-1]["valid_from"].date().isoformat() == "2026-10-08"

    retried = portwatch.update(graph, service)
    assert retried["days"] == ["2026-10-08", "2026-10-09"]
    assert retried["pending_days"] == []
    assert portwatch.newest(graph) == "2026-10-09"
    assert history(graph, PORT, "INNSA")[-1]["calls"] == 32


def test_empty_day_does_not_skip_forward_to_newer_days(graph, service):
    service.days = [row for row in service.days if row["date"] != "2026-10-08"]
    summary = portwatch.update(graph, service, backfill=3)
    assert summary["days"] == ["2026-10-07"]
    assert summary["pending_days"] == ["2026-10-08", "2026-10-09"]
    assert portwatch.newest(graph) == "2026-10-07"
    service.days += days("2026-10-08")
    assert portwatch.update(graph, service)["days"] == ["2026-10-08", "2026-10-09"]


def test_checkpoint_survives_an_interrupted_import(graph, service, monkeypatch):
    real_remember = portwatch.remember

    def interrupted(graph, kind, rows, by):
        if rows[0]["t"].startswith("2026-10-08"):
            raise OSError("interrupted import")
        return real_remember(graph, kind, rows, by)

    monkeypatch.setattr(portwatch, "remember", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        portwatch.update(graph, service, backfill=3)
    assert portwatch.newest(graph) == "2026-10-07"
    monkeypatch.setattr(portwatch, "remember", real_remember)
    resumed = portwatch.update(graph, service)
    assert resumed["days"] == ["2026-10-08", "2026-10-09"]
    assert resumed["state"] == "complete"


def test_a_port_of_the_feed_gets_the_days_of_portwatch(graph, service):
    poll(graph, 0, record(port="FIHEL", prev="CNQDG"))
    portwatch.update(graph, service, backfill=1)
    assert history(graph, PORT, "FIHEL")[-1]["calls"] == 5
    assert history(graph, PORT, "CNQDG")[-1]["calls"] == 600  # where the ship came from
    assert graph.ro_query("MATCH (p:Port {locode: 'FIHEL'}) RETURN count(p)").result_set == [[1]]


def test_numbers_that_cannot_be_numbers_are_left_out(graph, monkeypatch):
    bad = [
        day("port1", "2026-10-09", -1),
        day("port3", "2026-10-09", math.inf, iso3="FIN"),
        day("port4", "2026-10-09", math.nan, iso3="CHN"),
        {"date": None, "portid": "port6", "portcalls": 1},  # no day: says nothing
        {"date": "2026-10-09", "portid": None, "portcalls": 1},  # no port: says nothing
    ]
    summary = portwatch.update(graph, Service(PORTS, bad), backfill=1)
    assert summary["skipped"] == 2  # the row without a day and the row without a port
    for key in ("INNSA", "FIHEL", "CNQDG"):
        assert "calls" not in history(graph, PORT, key)[-1]
    assert history(graph, PORT, "CLVAP") == []


@pytest.mark.parametrize(
    "answer",
    [
        {"error": {"code": 400, "message": "Invalid query parameters"}},
        {"features": None},
        [],
        "text",
    ],
)
def test_an_answer_without_rows_is_refused(graph, answer):
    def broken(url, what, headers=None, params=None):
        if "outStatistics" in params:
            return {"features": [{"attributes": {"d": "2026-10-09"}}]}
        return answer

    with pytest.raises(ValueError, match="PortWatch answer"):
        portwatch.update(graph, broken)
    assert portwatch.newest(graph) is None


@pytest.mark.parametrize("newest", [None, "yesterday", "2026-10-09' OR 1=1 --", 7])
def test_a_newest_day_that_is_not_a_day_is_refused(graph, newest):
    def answer(url, what, headers=None, params=None):
        return {"features": [{"attributes": {"d": newest}}]}

    with pytest.raises(ValueError, match="newest day"):
        portwatch.update(graph, answer)


def test_a_service_that_never_stops_paging_is_refused(graph, service, monkeypatch):
    monkeypatch.setattr(portwatch, "MAX_PAGES", 1)
    with pytest.raises(ValueError, match="more than 1 pages"):
        portwatch.update(graph, service)


@pytest.fixture
def client(graph):
    app.dependency_overrides[get_graph] = lambda: graph
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ports_of_a_country_and_one_port_over_http(graph, service, client):
    poll(graph, 0, record(port="FIHEL", prev="CNQDG"))
    portwatch.update(graph, service, backfill=2)
    india = client.get("/api/ports", params={"country": "IND"}).json()
    assert [(p["key"], p["calls"]) for p in india] == [("INNSA", 32), ("portwatch:port2", 12)]
    assert "fp" not in india[0] and "words" not in india[0]
    busiest = client.get("/api/ports", params={"limit": 1}).json()
    assert [p["key"] for p in busiest] == ["CNQDG"]
    helsinki = client.get("/api/ports/FIHEL").json()
    assert [(d["day"], d["calls"]) for d in helsinki["days"]] == [
        ("2026-10-08", 5),
        ("2026-10-09", 5),  # one version holds both days; each day is given
    ]
    assert helsinki["place"]["name"] == "Helsinki" and helsinki["place"]["lat"] == 60.1
    mumbai = client.get("/api/ports/INNSA", params={"days": 1}).json()
    assert [d["calls"] for d in mumbai["days"]] == [32]  # the last day only
    assert helsinki["port_calls"]["CALLS_AT"] == [1]
    qingdao = client.get("/api/ports/CNQDG").json()
    assert qingdao["port_calls"]["CAME_FROM"] == [1]
    assert [d["calls"] for d in qingdao["days"]] == [600, 600]
    assert qingdao["lessons"] == [] and qingdao["episodes"] == []
    assert client.get("/api/ports/portwatch:port2").json()["place"]["name"] == "Chennai"
    assert [
        p["key"] for p in client.get("/api/search", params={"q": "chennai", "kind": "Port"}).json()
    ] == ["portwatch:port2"]
    assert client.get("/api/ports/XXNONE").status_code == 404
    assert client.get("/api/ports", params={"country": "india"}).status_code == 422


def test_the_world_gives_every_port_with_a_place(graph, service, client):
    portwatch.update(graph, service, backfill=1)
    found = client.get("/api/world").json()
    assert found["newest_day"] == "2026-10-09" and found["unusual"] == {}
    rows = {row[0]: row for row in found["ports"]}
    assert rows["INNSA"] == ["INNSA", "Mumbai (Nhava Sheva)", "IND", "India", 18.9, 72.9, 32]
    assert rows["CLVAP"][4:6] == [-33.0, -71.6] and len(rows) == 6


def test_the_world_and_a_port_show_their_episodes_and_lessons(graph, service, client):
    portwatch.update(graph, service, backfill=1)
    poll(graph, 0, record(port="FIHEL", prev="SEGOT"))  # Gothenburg: a port with no place
    now, ended = "port-activity:INNSA:2026-10-09", "port-activity:CNQDG:2026-10-08"
    open_episode(graph, now, "port-watcher", [(PORT, "INNSA")], at="2026-10-09T00:00:00")
    open_episode(graph, ended, "port-watcher", [(PORT, "CNQDG")], at="2026-10-08T00:00:00")
    close_episode(graph, ended, "port-watcher", {"back_to_usual": True}, at="2026-10-09T00:00:00")
    open_episode(graph, "other", "desk", [(PORT, "FIHEL")], at="2026-10-09T00:00:00")
    learn(graph, "innsa-passes", "reviewer", "Quiet days there pass", [ended], [(PORT, "INNSA")])
    found = client.get("/api/world").json()
    assert found["unusual"] == {"INNSA": now}  # not one that ended, nor of another kind
    assert client.get("/api/unusual").json() == {"ports": []}  # it has no first entry
    assert "SEGOT" not in {row[0] for row in found["ports"]}
    mumbai = client.get("/api/ports/INNSA").json()
    assert [e["id"] for e in mumbai["episodes"]] == [now]
    assert [lesson["id"] for lesson in mumbai["lessons"]] == ["innsa-passes"]
