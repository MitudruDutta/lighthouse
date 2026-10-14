"""Port desk: the Digitraffic port call feed, remembered with Lighthouse.

This module only maps feed records to rows. Lighthouse does the storing: versions, validity
windows, receipts, and failure records.

Run once against the live feed, then let the Watcher look at the berths and the Reviewer
learn from the overloads that ended: `python -m app.portcalls [graph_name]`
"""

import json
import sys
import urllib.request
import zlib
from collections import Counter

from falkordb import Graph
from lighthouse import Kind, ensure_schema, now, record_failure, remember, stamp

from app.db import get_db

FEED_URL = "https://meri.digitraffic.fi/api/port-call/v1/port-calls"
MAX_FEED_BYTES = 50_000_000  # the feed is about 1 MB; more than this is not the feed

PORT = Kind("Port", key="locode")
VESSEL = Kind("Vessel", key="imo", text=("name",))
BERTH = Kind("Berth", relations={"IN": PORT}, text=("name", "area_name"))
PORT_CALL = Kind(
    "PortCall",
    key="id",
    times=("eta", "etd", "ata", "atd"),
    relations={
        "MADE_BY": VESSEL,
        "CALLS_AT": PORT,
        "AT": BERTH,
        "CAME_FROM": PORT,
        "BOUND_FOR": PORT,
    },
)
KINDS = (PORT_CALL, VESSEL, BERTH)


def _text(value) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None


def _number(value) -> int | None:
    return value if type(value) is int and value > 0 else None


def to_rows(rec: dict, observed: str) -> dict:
    """One feed record as rows for Lighthouse: the port call, its vessel, and its berth.

    Only the fields named here are kept, so the ship master, agent, forwarder, and free-text
    fields of the feed never reach the graph. The feed gives no time for vessel and berth
    details, so those rows are true from `observed`, the time of the poll.
    """
    areas = rec.get("portAreaDetails") or [{}]
    # Limit: only the first port area is stored. Every record in the sample of the feed
    # had exactly one; `areas` keeps the count so a longer list is visible.
    area = areas[0]
    imo = _number(rec.get("imoLloyds"))
    port = _text(rec.get("portToVisit"))
    area_code = _text(area.get("portAreaCode"))
    berth = _text(area.get("berthCode"))
    berth_key = f"{port}/{area_code or ''}/{berth}" if berth else None
    changed = [rec.get("portCallTimestamp")] + [
        area.get(f"{name}Timestamp") for name in ("eta", "etd", "ata", "atd")
    ]
    return {
        "port_call": {
            "key": _number(rec.get("portCallId")),
            # The record's own timestamp can lag a field timestamp by a fraction of a second.
            "t": max(filter(None, map(stamp, changed)), default=None),
            "values": {
                "eta": area.get("eta"),
                "etd": area.get("etd"),
                "ata": area.get("ata"),
                "atd": area.get("atd"),
                "area": area_code,
                "areas": len(areas),
            },
            "relations": {
                "MADE_BY": imo,
                "CALLS_AT": port,
                "AT": berth_key,
                "CAME_FROM": _text(rec.get("prevPort")),
                "BOUND_FOR": _text(rec.get("nextPort")),
            },
        },
        "vessel": {
            "key": imo,
            "t": observed,
            "values": {
                "name": _text(rec.get("vesselName")),
                "mmsi": _number(rec.get("mmsi")),
                "nationality": _text(rec.get("nationality")),
                "type_code": _number(rec.get("vesselTypeCode")),
            },
        },
        "berth": berth_key
        and {
            "key": berth_key,
            "t": observed,
            "values": {
                "code": berth,
                "name": _text(area.get("berthName")),
                "area": area_code,
                "area_name": _text(area.get("portAreaName")),
            },
            "relations": {"IN": port},
        },
    }


def _problem(rows: dict) -> str | None:
    if rows["port_call"]["key"] is None:
        return "portCallId must be a positive integer"
    if rows["vessel"]["key"] is None:
        return "imoLloyds must be a positive integer"
    if not rows["port_call"]["relations"]["CALLS_AT"]:
        return "portToVisit is missing"
    return None


def ingest(graph: Graph, records: list[dict], observed=None, by: str = "digitraffic") -> dict:
    """Store one poll of the feed. `observed` is the time of the poll (default: now).

    Returns Lighthouse receipts by kind. "PortCall" has one receipt per record, in order.
    A record that cannot be mapped is not stored: it gets status "invalid" and a WriteFailure.
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list of feed records")
    # A feed clock that runs ahead must not date our rows in the future.
    observed = min(stamp(observed) or now(), now())
    receipts: list[dict | None] = [None] * len(records)
    kept, port_calls, vessels, berths = [], [], {}, {}
    for i, rec in enumerate(records):
        try:
            rows = to_rows(rec, observed)
            why = _problem(rows)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
            why = f"unreadable record: {exc!r}"
        if why:
            key = _number(rec.get("portCallId")) if isinstance(rec, dict) else None
            record_failure(graph, "invalid", PORT_CALL.label, key, why)
            receipts[i] = {"key": key, "status": "invalid", "reason": why}
            continue
        kept.append(i)
        port_calls.append(rows["port_call"])
        # A vessel or berth named by several records is sent once per distinct content.
        for found, row in ((vessels, rows["vessel"]), (berths, rows["berth"])):
            if row:
                found[json.dumps(row, sort_keys=True)] = row
    result = {
        VESSEL.label: remember(graph, VESSEL, list(vessels.values()), by),
        BERTH.label: remember(graph, BERTH, list(berths.values()), by),
    }
    for i, receipt in zip(kept, remember(graph, PORT_CALL, port_calls, by)):
        receipts[i] = receipt
    return result | {PORT_CALL.label: receipts}


def fetch(url: str = FEED_URL) -> dict:
    """The feed: {"dataUpdatedTime", "portCalls"}, port calls updated in the last 24 hours.
    Digitraffic asks for gzip and a user header.

    The answer is not trusted: only https is read (urllib would also open a local file),
    the body is cut off at MAX_FEED_BYTES before and after it is unpacked, and anything
    that is not the feed's shape raises ValueError."""
    if not url.startswith("https://"):
        raise ValueError("the feed is read over https only")
    request = urllib.request.Request(
        url, headers={"Accept-Encoding": "gzip", "Digitraffic-User": "lighthouse"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(MAX_FEED_BYTES + 1)
        if response.headers.get("Content-Encoding") == "gzip":
            # Unpack with a limit: a small gzip body can hold gigabytes.
            body = zlib.decompressobj(wbits=31).decompress(body, MAX_FEED_BYTES + 1)
    if len(body) > MAX_FEED_BYTES:
        raise ValueError(f"the feed answer is larger than {MAX_FEED_BYTES} bytes")
    try:
        feed = json.loads(body)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"the feed answer is not JSON: {type(exc).__name__}") from None
    if not isinstance(feed, dict) or not isinstance(feed.get("portCalls"), list):
        raise ValueError("the feed answer has no list of port calls")  # noqa: TRY004
    return feed


if __name__ == "__main__":
    graph = get_db().select_graph(sys.argv[1] if len(sys.argv) > 1 else "world")
    ensure_schema(graph, KINDS)
    feed = fetch()
    for kind, receipts in ingest(graph, feed["portCalls"], feed.get("dataUpdatedTime")).items():
        print(kind, dict(Counter(r["status"] for r in receipts)))
    # The agents read what this module declares, so they are imported here.
    from app.reviewer import review
    from app.watcher import watch

    done = watch(graph, feed.get("dataUpdatedTime"))
    print("Watcher", dict(Counter(item["did"] for item in done)))
    found = review(graph)
    for kind in ("lessons", "playbooks", "runs"):
        print("Reviewer", kind, dict(Counter(receipt["status"] for receipt in found[kind])))
