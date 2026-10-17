"""Live ship positions from aisstream.io, counted at the busiest ports of the world.

PortWatch publishes once a week, so its newest day is a week behind. AIS is live: ships
report where they are every few seconds to minutes. This reads the stream inside a box
around each of the busiest ports, counts the cargo ships and tankers that are stopped there
(moored, at anchor, or under half a knot), and every quarter of an hour writes one row per
port: the ships in port now, and the ships seen in port today, UTC. A ship counts as in
port now if it reported itself stopped there in the last half hour. A ship's type comes in
its static data, every few minutes; until it has come, the ship is not counted, so that
barges, ferries, and tugs in a harbour never are.

Without AISSTREAM_API_KEY it reads nothing and says so once. The key is free from
https://aisstream.io (sign in, then API Keys).

Run for the world graph:
    python -m app.ais world
"""

import argparse
import asyncio
import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from falkordb import Graph
from lighthouse import Kind, ensure_schema, now, remember

from app.db import get_db
from app.portwatch import busiest

log = logging.getLogger("lighthouse.ais")

URL = "wss://stream.aisstream.io/v0/stream"
LIVE = Kind("LivePort", key="port", text=("name",))
BY = "aisstream"
PORTS = 50  # busiest ports watched: one box each
RADIUS_KM = 9  # half the side of a port's box
FLUSH = 900  # seconds between writes
RECENT = timedelta(minutes=30)  # a stopped ship counts as in port now for this long
STOPPED = {1, 5}  # AIS navigational status: at anchor, moored
CARGO = range(70, 90)  # AIS ship types: cargo (70-79) and tankers (80-89)
SLOW = 0.5  # knots: slower than this is stopped, whatever the status says
WAIT = (5, 30, 120)  # seconds before connecting again after a failure


@dataclass
class Port:
    key: str
    name: str
    lat: float
    lon: float

    def box(self) -> list[list[float]]:
        """[[south, west], [north, east]], as aisstream asks for a bounding box."""
        dlat = RADIUS_KM / 111.0
        dlon = RADIUS_KM / (111.0 * max(math.cos(math.radians(self.lat)), 0.05))
        return [[self.lat - dlat, self.lon - dlon], [self.lat + dlat, self.lon + dlon]]

    def holds(self, lat: float, lon: float) -> bool:
        (south, west), (north, east) = self.box()
        return south <= lat <= north and west <= lon <= east


@dataclass
class Tally:
    """Which ships were stopped at which port, and when they last said so."""

    ports: list[Port]
    seen: dict[str, dict[int, datetime]] = field(default_factory=dict)
    today: dict[str, set[int]] = field(default_factory=dict)
    types: dict[int, int] = field(default_factory=dict)
    day: str = ""
    reports: int = 0

    def port_at(self, lat: float, lon: float) -> Port | None:
        return next((port for port in self.ports if port.holds(lat, lon)), None)

    def observe(self, report: dict) -> None:
        """One message of the stream; anything that is not a usable position or ship
        type is skipped."""
        typed = type_of(report)
        if typed is not None:
            self.types[typed[0]] = typed[1]
            return
        position = position_of(report)
        if position is None:
            return
        ship, lat, lon, stopped, when = position
        self.reports += 1
        port = self.port_at(lat, lon)
        if port is None or not stopped:
            return
        if when.date().isoformat() != self.day:
            self.day, self.today = when.date().isoformat(), {}
        self.seen.setdefault(port.key, {})[ship] = when
        self.today.setdefault(port.key, set()).add(ship)

    def rows(self, at: datetime) -> list[dict]:
        """One row per port with what is known of it now."""
        stamp = at.strftime("%Y-%m-%dT%H:%M:%SZ")
        found = []
        for port in self.ports:
            recent = sum(
                1
                for ship, when in self.seen.get(port.key, {}).items()
                if at - when <= RECENT and self.types.get(ship) in CARGO
            )
            found.append(
                {
                    "key": port.key,
                    "t": stamp,
                    "values": {
                        "name": port.name,
                        "ships_now": recent,
                        "ships_today": sum(
                            1
                            for ship in self.today.get(port.key, ())
                            if self.types.get(ship) in CARGO
                        )
                        if self.day == at.date().isoformat()
                        else 0,
                        "day": at.date().isoformat(),
                    },
                }
            )
        return found


def position_of(report: dict) -> tuple[int, float, float, bool, datetime] | None:
    """(ship, latitude, longitude, stopped, time) of a PositionReport, or None."""
    if not isinstance(report, dict) or report.get("MessageType") != "PositionReport":
        return None
    meta = report.get("MetaData") or {}
    body = (report.get("Message") or {}).get("PositionReport") or {}
    try:
        ship = int(meta["MMSI"])
        lat, lon = float(meta["latitude"]), float(meta["longitude"])
        speed = float(body.get("Sog", 0))
        status = int(body.get("NavigationalStatus", 15))
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not 0 < ship < 1_000_000_000:
        return None
    return ship, lat, lon, status in STOPPED or speed < SLOW, _time(meta.get("time_utc"))


def type_of(report: dict) -> tuple[int, int] | None:
    """(ship, AIS ship type) of a ShipStaticData message, or None."""
    if not isinstance(report, dict) or report.get("MessageType") != "ShipStaticData":
        return None
    meta = report.get("MetaData") or {}
    body = (report.get("Message") or {}).get("ShipStaticData") or {}
    try:
        return int(meta["MMSI"]), int(body["Type"])
    except (KeyError, TypeError, ValueError):
        return None


def _time(text) -> datetime:
    """The report's time, as aisstream writes it ("2026-10-17 19:20:01.123 +0000 UTC"),
    or now when it cannot be read: a report is live by nature."""
    try:
        return datetime.fromisoformat(str(text)[:19]).replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def watched(graph: Graph, most: int = PORTS) -> list[Port]:
    """The busiest ports with a place on the map."""
    return [
        Port(
            str(row["key"]),
            str(row.get("name") or row["key"]),
            float(row["lat"]),
            float(row["lon"]),
        )
        for row in busiest(graph, limit=most)
        if isinstance(row.get("lat"), (int, float)) and isinstance(row.get("lon"), (int, float))
    ]


def flush(graph: Graph, tally: Tally, at: datetime | None = None) -> dict:
    """Writes the counts of every port and the summary of this read."""
    at = at or datetime.now(UTC)
    rows = tally.rows(at)
    receipts = remember(graph, LIVE, by=BY, rows=rows) if rows else []
    summary = {
        "at": now(),
        "ports": len(rows),
        "ships_now": sum(row["values"]["ships_now"] for row in rows),
        "reports": tally.reports,
        "rows": {
            status: sum(1 for r in receipts if r["status"] == status)
            for status in {r["status"] for r in receipts}
        },
    }
    graph.query(
        "MERGE (p:Poll {id: 'ais'}) SET p.at = localdatetime($at), p.summary = $summary",
        {"at": summary["at"], "summary": json.dumps(summary)},
    )
    tally.reports = 0
    return summary


async def listen(
    graph: Graph, key: str, tally: Tally, url: str = URL, flush_every: int = FLUSH, stop=None
) -> None:
    """Reads the stream until it ends or `stop` is set, writing every `flush_every` seconds."""
    from websockets.asyncio.client import connect

    subscribe = {
        "APIKey": key,
        "BoundingBoxes": [port.box() for port in tally.ports],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
    }
    async with connect(url, open_timeout=20, max_size=2**20) as stream:
        await stream.send(json.dumps(subscribe))
        log.info("watching %d ports for ships in port", len(tally.ports))
        last = asyncio.get_running_loop().time()
        async for message in stream:
            try:
                tally.observe(json.loads(message))
            except (ValueError, TypeError):
                continue
            if asyncio.get_running_loop().time() - last >= flush_every:
                summary = await asyncio.to_thread(flush, graph, tally)
                log.info("wrote live counts: %s", json.dumps(summary))
                last = asyncio.get_running_loop().time()
            if stop is not None and stop.is_set():
                break
    await asyncio.to_thread(flush, graph, tally)


def run(graph: Graph, key: str | None = None) -> None:
    key = key if key is not None else os.environ.get("AISSTREAM_API_KEY", "").strip()
    if not key:
        log.info("AISSTREAM_API_KEY is not set: live ship positions are off")
        while True:  # stay up, so that the service does not restart over and over
            asyncio.run(asyncio.sleep(3600))
    ensure_schema(graph, [LIVE])
    failures = 0
    while True:
        ports = watched(graph)
        if not ports:
            log.info("No ports with a place on the map yet: waiting for PortWatch")
            asyncio.run(asyncio.sleep(600))
            continue
        try:
            asyncio.run(listen(graph, key, Tally(ports)))
            failures = 0
        except Exception:  # the stream drops; connect again, a little later each time
            log.exception("Live positions interrupted")
            graph.query(
                "MERGE (p:Poll {id: 'ais-error'}) SET p.summary = $summary",
                {"summary": json.dumps({"at": now()})},
            )
            asyncio.run(asyncio.sleep(WAIT[min(failures, len(WAIT) - 1)]))
            failures += 1


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", help="the graph to write, such as world")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    run(get_db().select_graph(args.graph))


if __name__ == "__main__":
    main()
