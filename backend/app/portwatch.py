"""Ports of the world: how many ships called at each of some 2,000 ports in 180 countries,
each day, by type of ship, and what they unloaded and loaded.

Source: IMF PortWatch (portwatch.imf.org), counted from the positions that ships send (AIS).
The numbers are some days behind. Reuse of IMF data for a commercial purpose needs the
permission of the IMF.

A port is the Port that the port call feed names when PortWatch gives its UN/LOCODE, so a
ship that comes to Finland from Qingdao leads to Qingdao's days. A port without one is
keyed by its PortWatch id. One day of one port is one row, true from the start of that day:
the history of a port is its days, and as_of() gives the numbers of any day.
"""

import json
import math
import re
import time
import urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from falkordb import Graph
from lighthouse import history, now, remember
from lighthouse.values import whole_number, without_words

from app.portcalls import PORT
from app.web import read_json

SERVICE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTS_URL = f"{SERVICE}/PortWatch_ports_database/FeatureServer/0/query"
DAYS_URL = f"{SERVICE}/Daily_Ports_Data/FeatureServer/0/query"
PAGE = 1_000  # the most rows the service gives in one answer
MAX_PAGES = 500  # pages of one read: more is not the service as it is
BACKFILL = 30  # days read when the graph has none yet
BY = "portwatch"
MOST = 200  # ports or days in one answer
WORKERS = 4  # days asked for at once: a public service, used gently
# Seconds to wait before asking again after an error the service gets over, such as a 503
# or a 304 that its cache gives for no reason. One such error would otherwise lose a read.
RETRIES = (2, 8)
PASSING = {304, 429, 500, 502, 503, 504}

_LOCODE = re.compile(r"[A-Z]{2}[A-Z0-9]{3}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# PortWatch's name of a daily number, and ours.
DAY = {
    "portcalls": "calls",
    "portcalls_container": "calls_container",
    "portcalls_dry_bulk": "calls_dry_bulk",
    "portcalls_general_cargo": "calls_general_cargo",
    "portcalls_roro": "calls_roro",
    "portcalls_tanker": "calls_tanker",
    "import": "import_tonnes",
    "export": "export_tonnes",
}
PLACE = {"portname": "name", "country": "country", "ISO3": "iso3", "continent": "continent"}


def _ask(read, url: str, params: dict):
    """One answer of the service, asked for again after an error that passes."""
    for wait in (*RETRIES, None):
        try:
            return read(url, "PortWatch", params=params)
        except urllib.error.HTTPError as exc:
            if exc.code not in PASSING or wait is None:
                raise
        except (urllib.error.URLError, TimeoutError):
            if wait is None:
                raise
        time.sleep(wait)


def _features(read, url: str, where: str, fields: str) -> list[dict]:
    """Every row that `where` selects, a page at a time."""
    rows = []
    for page in range(MAX_PAGES):
        params = {
            "where": where,
            "outFields": fields,
            "orderByFields": "ObjectId",
            "resultOffset": page * PAGE,
            "resultRecordCount": PAGE,
            "returnGeometry": "false",
            "f": "json",
        }
        answer = _ask(read, url, params)
        features = answer.get("features") if isinstance(answer, dict) else None
        if not isinstance(features, list):
            error = answer.get("error") if isinstance(answer, dict) else None
            raise ValueError(f"the PortWatch answer has no rows: {str(error)[:200]}")  # noqa: TRY004
        rows += [f["attributes"] for f in features if isinstance(f, dict) and "attributes" in f]
        if not answer.get("exceededTransferLimit"):
            return rows
    raise ValueError(f"PortWatch gave more than {MAX_PAGES} pages")


def _latest(read) -> str:
    """The newest day that PortWatch has, as YYYY-MM-DD."""
    stat = [{"statisticType": "max", "onStatisticField": "date", "outStatisticFieldName": "d"}]
    params = {"where": "1=1", "outStatistics": json.dumps(stat), "f": "json"}
    answer = _ask(read, DAYS_URL, params)
    try:
        found = answer["features"][0]["attributes"]["d"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("the PortWatch answer has no newest day") from None
    if not _DATE.fullmatch(str(found)):
        raise ValueError(f"the PortWatch answer has no newest day: {str(found)[:50]}")
    return found


def keys(ports: list[dict]) -> dict[str, str]:
    """The UN/LOCODE of each PortWatch port that has one, by its id. Of ports with the same
    one, the first by id takes it; the others are keyed by their PortWatch id."""
    found, taken = {}, set()
    for port in sorted(ports, key=lambda p: str(p.get("portid"))):
        locode = str(port.get("LOCODE") or "").replace(" ", "").upper()
        if _LOCODE.fullmatch(locode) and locode not in taken:
            taken.add(locode)
            found[port["portid"]] = locode
    return found


def _number(value, low: float = 0, high: float = math.inf):
    """A number of the answer, or None for one that cannot be one."""
    ok = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    return value if ok else None


def to_row(day: dict, port: dict, key: str) -> dict:
    """One day of one port as a row. Where a port was is taken from the list of ports, what
    happened that day from the day."""
    values = {ours: day.get(theirs) or port.get(theirs) for theirs, ours in PLACE.items()}
    values |= {"lat": _number(port.get("lat"), -90, 90), "lon": _number(port.get("lon"), -180, 180)}
    values |= {"portwatch": day.get("portid")}
    values |= {ours: _number(day.get(theirs)) for theirs, ours in DAY.items()}
    return {"key": key, "t": f"{day.get('date')}T00:00:00Z", "values": values}


def newest(graph: Graph) -> str | None:
    """The last day that was read, as YYYY-MM-DD, or None."""
    rows = graph.ro_query("MATCH (p:Poll {id: 'portwatch'}) RETURN p.newest").result_set
    return rows[0][0] if rows else None


def update(graph: Graph, read=read_json, backfill: int = BACKFILL) -> dict:
    """Read the days after the last one that was read, or the last `backfill` days that
    PortWatch has the first time, and write them. Returns {"at", "ports", "days", "rows"}.

    Each day is asked for on its own, a few at a time: the service is slow to page far into
    one long answer. With no new day, the list of ports is not read either."""
    latest = date.fromisoformat(_latest(read))
    checkpoint = newest(graph)
    since = checkpoint or (latest - timedelta(days=backfill)).isoformat()
    if not _DATE.fullmatch(since):
        raise ValueError(f"not a day: {since!r}")
    wanted = [
        (date.fromisoformat(since) + timedelta(days=n)).isoformat()
        for n in range(1, (latest - date.fromisoformat(since)).days + 1)
    ]
    rows_by_day, read_days, by_id = {}, [], {}
    skipped, receipts = 0, []

    def save(state):
        summary = {
            "at": now(),
            "ports": len(by_id),
            "days": list(read_days),
            "rows": dict(Counter(receipt["status"] for receipt in receipts)),
            "skipped": skipped,
            "pending_days": wanted[len(read_days) :],
            "newest": max(read_days, default=checkpoint),
            "state": state,
        }
        graph.query(
            "MERGE (p:Poll {id: 'portwatch'}) SET p.at = localdatetime($at), "
            "p.summary = $summary, p.newest = $newest",
            {"at": summary["at"], "summary": json.dumps(summary), "newest": summary["newest"]},
        )
        return summary

    save("running")
    if wanted:
        ports = _features(
            read, PORTS_URL, "1=1", "portid,portname,country,ISO3,continent,lat,lon,LOCODE"
        )
        by_id = {port["portid"]: port for port in ports if "portid" in port}
        key_of = keys(list(by_id.values()))
        fields = ",".join(["date", "portid", "portname", "country", "ISO3", *DAY])
        with ThreadPoolExecutor(WORKERS) as pool:
            found = pool.map(
                lambda d: _features(read, DAYS_URL, f"date = DATE '{d}'", fields), wanted
            )
            days = [row for rows_of_day in found for row in rows_of_day]
        for day in sorted(days, key=lambda d: (str(d.get("date")), str(d.get("portid")))):
            if not _DATE.fullmatch(str(day.get("date"))) or day.get("portid") is None:
                skipped += 1
                continue  # a row without a day or a port says nothing
            port = by_id.get(day["portid"], {})
            key = key_of.get(day["portid"], f"portwatch:{day['portid']}")
            rows_by_day.setdefault(day["date"], []).append(to_row(day, port, key))
    for day in wanted:
        rows = rows_by_day.get(day, [])
        if not rows:
            break  # An empty day must not move the checkpoint past a gap.
        written = remember(graph, PORT, rows, by=BY)
        receipts.extend(written)
        if any(r["status"] not in {"created", "changed", "inserted", "unchanged"} for r in written):
            break  # Retry this day before writing newer versions of the same ports.
        read_days.append(day)
        save("running")  # Resume after this complete day even if the process stops next.
    return save("partial" if len(read_days) < len(wanted) else "complete")


def busiest(graph: Graph, country: str | None = None, limit: int = 50) -> list[dict]:
    """Ports with what happened on their last day, busiest first. `country` keeps to one
    country, by its ISO 3166 code, such as IND."""
    if country is not None and not re.fullmatch(r"[A-Z]{3}", str(country)):
        raise ValueError("country is an ISO 3166 code of three capital letters, such as IND")
    whole_number(limit, "limit", MOST)
    rows = graph.ro_query(
        "MATCH (p:Port) WHERE p.calls IS NOT NULL AND ($country IS NULL OR p.iso3 = $country) "
        "RETURN p ORDER BY p.calls DESC, p.locode LIMIT $limit",
        {"country": country, "limit": limit},
    ).result_set
    return [
        {"key": node.properties["locode"], **without_words(node.properties)} for (node,) in rows
    ]


def daily(versions: list[dict], last: str | None, days: int) -> list[dict]:
    """The last `days` days of a port, oldest first, one entry a day. A version holds every
    day from its start until the next one; the open one until `last`, the newest day read."""
    found = {}
    end_of_all = date.fromisoformat(last) if last else None
    for state in versions:
        day = state["valid_from"].date()
        end = state["valid_to"].date() - timedelta(days=1) if state.get("valid_to") else end_of_all
        while end is not None and day <= end:
            found[day] = {"day": day.isoformat(), **{n: state.get(n) for n in DAY.values()}}
            day += timedelta(days=1)
    return [found[day] for day in sorted(found)[-days:]]


def days_of(graph: Graph, key: str, days: int = 30) -> list[dict]:
    """The last `days` days of one port, as daily() gives them."""
    whole_number(days, "days", MOST)
    return daily(history(graph, PORT, key), newest(graph), days)
