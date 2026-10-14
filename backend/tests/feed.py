"""Feed records in the Digitraffic shape, and reads of the graph, for the tests."""

from datetime import UTC, datetime, timedelta

from app.portcalls import PORT_CALL, ingest

T0 = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


def when(minute: int) -> datetime:
    return T0 + timedelta(minutes=minute)


def feed_time(minute: int | None) -> str | None:
    return None if minute is None else when(minute).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def record(id=1, minute=0, imo=9000001, port="FIHEL", prev="DETRV", next_port="FIKTK", **area):
    """A feed record in the Digitraffic shape. Every time is in minutes after T0.

    Area fields: eta, etd, ata, atd (minutes), berth, area, name (of the vessel). The
    personal and free-text fields are filled so that a leak into the graph is visible.
    """
    area = {"eta": 600, "berth": "VC2", "area": "VUOS", "name": "Test Ship", **area}
    details = {
        "berthCode": area["berth"],
        "berthName": area["berth"] and f"Berth {area['berth']}",
        "portAreaCode": area["area"],
        "portAreaName": area["area"] and f"Area {area['area']}",
    }
    for name in ("eta", "etd", "ata", "atd"):
        details[name] = feed_time(area.get(name))
        details[f"{name}Timestamp"] = feed_time(minute) if area.get(name) is not None else None
    return {
        "portCallId": id,
        "portCallTimestamp": feed_time(minute),
        "portToVisit": port,
        "prevPort": prev,
        "nextPort": next_port,
        "vesselName": area["name"],
        "imoLloyds": imo,
        "mmsi": 230000001,
        "nationality": "FI",
        "vesselTypeCode": 40,
        "shipMasterArrival": "PERSONAL master",
        "shipMasterDeparture": "PERSONAL master",
        "managementNameArrival": "PERSONAL manager",
        "forwarderNameArrival": "PERSONAL forwarder",
        "freeTextArrival": "PERSONAL free text",
        "agentInfo": [{"name": "PERSONAL agent", "ediNumber": "0037", "role": 1}],
        "portAreaDetails": [details],
    }


def poll(graph, minute: int, *records) -> dict:
    return ingest(graph, list(records), observed=when(minute))


def statuses(receipts: dict, kind=PORT_CALL) -> list[str]:
    return [receipt["status"] for receipt in receipts[kind.label]]


def shape(graph) -> tuple[dict, dict]:
    kind = "[l IN labels(n) WHERE l <> 'Entity'][0]"  # every entity also has the label Entity
    nodes = graph.ro_query(f"MATCH (n) WHERE NOT n:Stamp RETURN {kind}, count(n)").result_set
    edges = graph.ro_query("MATCH ()-[e]->() RETURN type(e), count(e)").result_set
    return dict(nodes), dict(edges)


def failures(graph) -> list[list]:
    query = "MATCH (f:WriteFailure) RETURN f.reason, f.kind, f.key, f.detail ORDER BY f.key"
    return graph.ro_query(query).result_set
