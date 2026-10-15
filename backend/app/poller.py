"""The poller: reads the port call feed again and again. After each read, the Watcher looks
at the berths and the Reviewer learns from the overloads that ended. Once an hour it also
reads the ports of the world from PortWatch.

    python -m app.poller [graph_name] [--every SECONDS] [--once]

A read that fails is logged and the next one comes on time: a source or the network may be
down for a while, and the graph keeps what it had. The summary of the last read of each
source is kept in the graph, as a Poll node, for the API to show.
"""

import argparse
import json
import logging
import threading
import time
from collections import Counter

from falkordb import Graph
from lighthouse import ensure_schema, now

from app import portwatch
from app.db import get_db
from app.portcalls import KINDS, PORT_CALL, fetch, ingest
from app.reviewer import review
from app.watcher import watch

EVERY = 300  # seconds between reads: the feed holds the port calls of the last 24 hours
WORLD_EVERY = 3600  # seconds between reads of PortWatch, which adds a day at a time
LEAST = 60  # the shortest wait that may be asked for: Digitraffic is a shared service

log = logging.getLogger("lighthouse.poller")


def _counts(receipts, field: str = "status") -> dict:
    return dict(Counter(receipt[field] for receipt in receipts))


def poll_once(graph: Graph, read=fetch) -> dict:
    """One read of the feed, stored, watched, and reviewed. Returns what it did:
    {"at", "feed_time", "port_calls", "watcher", "reviewer", "ms"}."""
    started = time.perf_counter()
    feed = read()
    observed = feed.get("dataUpdatedTime")
    stored = ingest(graph, feed["portCalls"], observed)
    watched = watch(graph, observed)
    learned = review(graph)
    summary = {
        "at": now(),
        "feed_time": observed,
        "port_calls": _counts(stored[PORT_CALL.label]),
        "watcher": _counts(watched, "did"),
        "reviewer": {kind: _counts(learned[kind]) for kind in ("lessons", "playbooks", "runs")},
        "ms": round((time.perf_counter() - started) * 1000),
    }
    graph.query(
        "MERGE (p:Poll {id: 'feed'}) SET p.at = localdatetime($at), p.summary = $summary",
        {"at": summary["at"], "summary": json.dumps(summary)},
    )
    return summary


def last_poll(graph: Graph, source: str = "feed") -> dict | None:
    """The summary of the last read of a source ("feed" or "portwatch"), or None."""
    rows = graph.ro_query("MATCH (p:Poll {id: $id}) RETURN p.summary", {"id": source}).result_set
    return json.loads(rows[0][0]) if rows else None


def run(
    graph: Graph,
    every: int = EVERY,
    stop: threading.Event | None = None,
    read=fetch,
    world=portwatch.update,
    world_every: int = WORLD_EVERY,
):
    """Read the feed every `every` seconds, and the world every `world_every` seconds,
    until `stop` is set."""
    stop = stop or threading.Event()
    world_read = None
    while not stop.is_set():
        try:
            summary = poll_once(graph, read)
            log.info("read the feed: %s", json.dumps(summary))
        except Exception:
            # The next read may work: a failed one costs one interval, not the process.
            log.exception("reading the feed failed")
        if world_read is None or time.monotonic() - world_read >= world_every:
            world_read = time.monotonic()
            try:
                log.info("read PortWatch: %s", json.dumps(world(graph)))
            except Exception:
                log.exception("reading PortWatch failed")
        stop.wait(every)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Read the port call feed into the graph.")
    parser.add_argument("graph", nargs="?", default="world")
    parser.add_argument("--every", type=int, default=EVERY, help="seconds between reads")
    parser.add_argument("--once", action="store_true", help="read once and stop")
    args = parser.parse_args(argv)
    if args.every < LEAST:
        parser.error(f"--every must be at least {LEAST} seconds")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    graph = get_db().select_graph(args.graph)
    ensure_schema(graph, KINDS)
    if args.once:
        print(json.dumps(poll_once(graph), indent=2))
        print(json.dumps(portwatch.update(graph), indent=2))
    else:
        run(graph, args.every)


if __name__ == "__main__":
    main()
