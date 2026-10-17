"""Live ship positions: what counts as a ship in port, what is written, and the stream."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from lighthouse import remember

from app import ais
from app.api import get_graph
from app.main import app
from app.portcalls import PORT

NOON = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
ROTTERDAM = ais.Port("NLRTM", "Rotterdam", 51.92, 4.21)
SINGAPORE = ais.Port("portwatch:port1201", "Singapore", 1.27, 103.71)


def typed(ship, kind=70):
    return {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": ship},
        "Message": {"ShipStaticData": {"Type": kind}},
    }


def report(ship, lat, lon, speed=0.0, status=5, at=NOON, kind="PositionReport"):
    return {
        "MessageType": kind,
        "MetaData": {
            "MMSI": ship,
            "latitude": lat,
            "longitude": lon,
            "time_utc": at.strftime("%Y-%m-%d %H:%M:%S.000 +0000 UTC"),
        },
        "Message": {kind: {"Sog": speed, "NavigationalStatus": status}},
    }


def test_a_ship_counts_when_it_is_stopped_inside_a_port_box():
    tally = ais.Tally([ROTTERDAM, SINGAPORE])
    for ship in (1, 2, 3, 4, 5):
        tally.observe(typed(ship, 70 if ship != 4 else 84))  # cargo ships, and a tanker
    tally.observe(typed(7, 52))  # a tug
    tally.observe(report(7, 51.93, 4.22))  # moored, but a tug: not counted
    tally.observe(report(8, 51.93, 4.22))  # moored, of a type not known yet: not counted
    tally.observe(report(1, 51.93, 4.22))  # moored in Rotterdam
    tally.observe(report(2, 51.95, 4.25, speed=0.2, status=0))  # under way, but not moving
    tally.observe(report(3, 51.90, 4.20, speed=12.0, status=0))  # passing through
    tally.observe(report(4, 1.28, 103.72, status=1))  # at anchor off Singapore
    tally.observe(report(5, 40.0, -70.0))  # at sea, in no box
    tally.observe(report(1, 51.93, 4.22))  # the same ship again
    for broken in ({}, {"MessageType": "PositionReport"}, report("x", 1, 2), report(6, 95, 0)):
        tally.observe(broken)
    assert tally.reports == 8
    rows = {row["key"]: row["values"] for row in tally.rows(NOON + timedelta(minutes=5))}
    assert rows["NLRTM"]["ships_now"] == 2 and rows["NLRTM"]["ships_today"] == 2
    assert rows["portwatch:port1201"]["ships_now"] == 1


def test_now_is_the_last_half_hour_and_today_starts_at_midnight():
    tally = ais.Tally([ROTTERDAM])
    for ship in (1, 2, 3):
        tally.observe(typed(ship))
    tally.observe(report(1, 51.93, 4.22, at=NOON))
    tally.observe(report(2, 51.93, 4.22, at=NOON + timedelta(minutes=50)))
    (row,) = tally.rows(NOON + timedelta(hours=1))
    assert (row["values"]["ships_now"], row["values"]["ships_today"]) == (1, 2)
    tomorrow = NOON + timedelta(hours=13)
    tally.observe(report(3, 51.93, 4.22, at=tomorrow))
    (row,) = tally.rows(tomorrow)
    assert (row["values"]["ships_now"], row["values"]["ships_today"]) == (1, 1)
    (row,) = tally.rows(tomorrow + timedelta(days=1))
    assert row["values"]["ships_today"] == 0  # nothing reported yet on that day


def test_a_box_is_about_nine_kilometres_each_way_at_any_latitude():
    (south, west), (north, east) = ROTTERDAM.box()
    assert north - south == pytest.approx(2 * 9 / 111, rel=0.01)
    assert (east - west) > (north - south)  # a degree of longitude is shorter up north
    assert ROTTERDAM.holds(51.92, 4.21) and not ROTTERDAM.holds(52.2, 4.21)


@pytest.fixture
def world(graph):
    remember(
        graph,
        PORT,
        by="portwatch",
        rows=[
            {
                "key": "NLRTM",
                "t": "2026-01-05T00:00:00Z",
                "values": {"name": "Rotterdam", "calls": 77, "lat": 51.92, "lon": 4.21},
            },
            {
                "key": "XXNOP",
                "t": "2026-01-05T00:00:00Z",
                "values": {"name": "Nowhere", "calls": 5},
            },
        ],
    )
    ais.ensure_schema(graph, [ais.LIVE])
    return graph


def test_counts_are_written_per_port_and_served(world):
    ports = ais.watched(world)
    assert [port.key for port in ports] == ["NLRTM"]  # a port without a place has no box
    tally = ais.Tally(ports)
    tally.observe(typed(1))
    tally.observe(report(1, 51.93, 4.22))
    summary = ais.flush(world, tally, NOON)
    assert summary["ports"] == 1 and summary["ships_now"] == 1 and summary["reports"] == 1
    app.dependency_overrides[get_graph] = lambda: world
    try:
        client = TestClient(app)
        live = client.get("/api/live").json()
        assert live["ports"]["NLRTM"]["now"] == 1 and live["ports"]["NLRTM"]["name"] == "Rotterdam"
        status = client.get("/api/status").json()
        assert status["last_ais"]["ships_now"] == 1 and status["availability"]["ais"] is True
    finally:
        app.dependency_overrides.clear()


def test_the_stream_is_asked_for_the_boxes_and_read(world):
    from websockets.asyncio.server import serve

    asked = []

    async def aisstream(connection):
        asked.append(json.loads(await connection.recv()))
        live = datetime.now(UTC)  # the stream sends what happens now
        for message in (
            typed(1),
            typed(2, 81),
            report(1, 51.93, 4.22, at=live),
            "not json",
            report(2, 51.94, 4.23, status=1, at=live),
        ):
            await connection.send(message if isinstance(message, str) else json.dumps(message))

    async def main():
        async with serve(aisstream, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            tally = ais.Tally(ais.watched(world))
            await ais.listen(world, "secret", tally, url=f"ws://127.0.0.1:{port}")
            return tally

    tally = asyncio.run(main())
    (subscription,) = asked
    assert subscription["APIKey"] == "secret"
    assert subscription["BoundingBoxes"] == [ROTTERDAM.box()]
    assert subscription["FilterMessageTypes"] == ["PositionReport", "ShipStaticData"]
    assert sorted(tally.today["NLRTM"]) == [1, 2]
    assert world.ro_query("MATCH (l:LivePort {port: 'NLRTM'}) RETURN l.ships_today").result_set == [
        [2]
    ]
