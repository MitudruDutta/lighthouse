"""The measures behind the README's claims, each from the running system.

    uv run python -m app.measure writes     # LLM calls per stored event, write latency
    uv run python -m app.measure history    # a known sequence of changes, read back exactly
    uv run python -m app.measure claims     # many agents race for the same tasks
    uv run python -m app.measure tenants    # a query in one tenant sees nothing of another
    uv run python -m app.measure restart    # mark, restart the database, then --check
    uv run python -m app.measure memory     # the same predictions with memory on and off

Each one prints its result and writes it to measurements/<name>.json with the commit and
the parameters it ran with. Every graph it writes is a throwaway graph of its own, deleted
afterwards, except the PortWatch days of `memory`, which are kept to be read again.
"""

import argparse
import json
import math
import os
import random
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import lighthouse
from lighthouse import Kind, add_task, claim, ensure_schema, history, lesson, remember, tenant
from lighthouse.kinds import STAMP

from app import model, portcalls, portwatch, portwatcher, reviewer
from app.db import get_db

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "measurements"
DATA = "measure_portwatch"  # the PortWatch days of `memory`, kept between runs
SENSOR = Kind("Sensor", key="key", text=("status",))
LONG = 120_000  # milliseconds for the measure's own reads of a year of data


def _throwaway(prefix: str):
    return get_db().select_graph(f"measure_{prefix}_{uuid.uuid4().hex[:8]}")


def _percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(share * len(ordered)) - 1)]


def writes(events: int) -> dict:
    """Stores the live Finnish port call feed one port call at a time, as the poller would
    if each came alone, and counts the model calls made while doing it."""
    feed = portcalls.fetch()
    records = feed["portCalls"][:events]
    calls = []
    real_chat = model.chat
    model.chat = lambda *a, **k: calls.append(1) or real_chat(*a, **k)
    graph = _throwaway("writes")
    try:
        ensure_schema(graph, portcalls.KINDS)
        timings = []
        for record in records:
            started = time.perf_counter()
            portcalls.ingest(graph, [record], feed.get("dataUpdatedTime"))
            timings.append((time.perf_counter() - started) * 1000)
        batch = _throwaway("writes_batch")
        try:
            ensure_schema(batch, portcalls.KINDS)
            started = time.perf_counter()
            portcalls.ingest(batch, records, feed.get("dataUpdatedTime"))
            seconds = time.perf_counter() - started
        finally:
            batch.delete()
    finally:
        model.chat = real_chat
        graph.delete()
    return {
        "events": len(records),
        "llm_calls": len(calls),
        "llm_calls_per_event": len(calls) / len(records),
        "latency_ms_p50": round(_percentile(timings, 0.50), 1),
        "latency_ms_p95": round(_percentile(timings, 0.95), 1),
        "batch_events_per_second": round(len(records) / seconds),
    }


def _replay(rows: list[dict], truth: dict[str, list]) -> dict:
    """Writes `rows` into a throwaway graph and compares every fact read back with `truth`,
    {key: [(time, status), ...]} in time order. A fact is right when the status held, and
    only it, over the whole of its validity window."""
    graph = _throwaway("history")
    try:
        ensure_schema(graph, [SENSOR])
        receipts = []
        for at in range(0, len(rows), 200):
            receipts += remember(graph, SENSOR, rows[at : at + 200], by="measure")
        stale = {(r["key"], row["t"]) for r, row in zip(receipts, rows) if r["status"] == "stale"}
        # The same refusal again is counted on one node: `times` says how many it stands for.
        nodes, refusals = graph.ro_query(
            "MATCH (w:WriteFailure) RETURN count(w), coalesce(sum(w.times), 0)"
        ).result_set[0]
        facts = wrong = unexplained = 0
        for key, changes in truth.items():
            for fact in history(graph, SENSOR, key):
                begins = fact["valid_from"].replace(tzinfo=None)
                ends = fact["valid_to"].replace(tzinfo=None) if fact.get("valid_to") else None
                held = [status for at, status in changes if at <= begins][-1:]
                inside = [at for at, _ in changes if begins < at and (ends is None or at < ends)]
                facts += 1
                if held != [fact["status"]] or inside:
                    wrong += 1
                    unexplained += not any(
                        k == key
                        and begins <= datetime.fromisoformat(t)
                        and (ends is None or datetime.fromisoformat(t) < ends)
                        for k, t in stale
                    )
    finally:
        graph.delete()
    counts = {}
    for receipt in receipts:
        counts[receipt["status"]] = counts.get(receipt["status"], 0) + 1
    return {
        "rows": len(rows),
        "receipts": counts,
        "write_failure_nodes": nodes,
        "refusals_recorded": int(refusals),
        "facts_read_back": facts,
        "facts_wrong": wrong,
        "facts_wrong_without_a_refused_row": unexplained,
    }


def history_exact(entities: int, versions: int, seed: int) -> dict:
    """A known sequence of changes, written once in time order and once shuffled, so that
    many rows arrive late. In order, every fact must be right. Shuffled, a late row that
    falls inside a State that held again after it is refused as `stale` and kept as a
    WriteFailure (see the library README); no fact may be wrong unless such a row lies in it."""
    rng = random.Random(seed)
    start = datetime(2026, 1, 1)
    truth, rows = {}, []
    for n in range(entities):
        key, minute, last = f"s{n}", 0, None
        truth[key] = []
        for _ in range(versions):
            minute += rng.randint(1, 120)
            status = rng.choice(("ok", "hot", "cold", "off"))
            if status == last:
                continue  # a source that sends changes: an unchanged value is no row
            at = start + timedelta(minutes=minute)
            truth[key].append((at, status))
            rows.append({"key": key, "t": at.isoformat(), "values": {"status": status}})
            last = status
    in_order = _replay(sorted(rows, key=lambda row: row["t"]), truth)
    shuffled = rows[:]
    rng.shuffle(shuffled)
    return {"entities": entities, "in_order": in_order, "shuffled": _replay(shuffled, truth)}


def claims(agents: int, tasks: int) -> dict:
    """Agents, each on its own connection, claim the same tasks at the same moment."""
    graph = _throwaway("claims")
    try:
        ensure_schema(graph)
        for n in range(tasks):
            add_task(graph, f"t{n}", "work")
        won, start = [], threading.Barrier(agents)

        def agent(name):
            own = get_db().select_graph(graph.name)
            start.wait(timeout=30)
            while task := claim(own, name, "work"):
                won.append(task["id"])

        with ThreadPoolExecutor(agents) as pool:
            for future in [pool.submit(agent, f"agent-{n}") for n in range(agents)]:
                future.result()
        owners = graph.ro_query(
            "MATCH (t:Task) OPTIONAL MATCH (t)-[c:CLAIMED_BY]->() RETURN t.id, count(c)"
        ).result_set
    finally:
        graph.delete()
    return {
        "agents": agents,
        "tasks": tasks,
        "claims_won": len(won),
        "tasks_won_twice": len(won) - len(set(won)),
        "tasks_with_two_claims": sum(1 for _, count in owners if count > 1),
        "tasks_unclaimed": tasks - len(set(won)),
    }


def tenants(rows: int) -> dict:
    """Writes into one tenant's graph and asks the same questions in another's."""
    db, ids = get_db(), [f"measure-{uuid.uuid4().hex[:8]}" for _ in range(2)]
    mine, theirs = (tenant(db, name) for name in ids)
    try:
        for graph in (mine, theirs):
            ensure_schema(graph, [SENSOR])
        remember(
            mine,
            SENSOR,
            [
                {"key": f"s{n}", "t": "2026-01-01T00:00:00", "values": {"status": "secret"}}
                for n in range(rows)
            ],
            by="measure",
        )
        seen = {
            "nodes": theirs.ro_query("MATCH (n:Sensor) RETURN count(n)").result_set[0][0],
            "search": len(lighthouse.search(theirs, SENSOR, "secret", limit=100)),
            "history": sum(len(history(theirs, SENSOR, f"s{n}")) for n in range(rows)),
        }
    finally:
        mine.delete()
        theirs.delete()
    return {"rows_in_one_tenant": rows, "seen_from_the_other": seen}


def restart(check: bool) -> dict:
    """Mark the database, restart FalkorDB (docker compose restart falkordb), then check."""
    graph = get_db().select_graph("measure_restart")
    if not check:
        at = lighthouse.now()
        graph.query("MERGE (m:Mark {id: 1}) SET m.at = $at", {"at": at})
        return {"marked_at": at, "next": "docker compose restart falkordb, then --check"}
    rows = graph.ro_query("MATCH (m:Mark {id: 1}) RETURN m.at").result_set
    graph.delete()
    uptime = get_db().connection.info("server").get("uptime_in_seconds")
    return {
        "mark_found": bool(rows),
        "marked_at": rows[0][0] if rows else None,
        "database_uptime_s": uptime,
    }


def _wilson(right: int, n: int) -> list[float]:
    if not n:
        return [0.0, 0.0]
    p, z = right / n, 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 3), round(centre + half, 3)]


def _sign_test(wins: int, losses: int) -> float:
    """Two-sided exact p-value that wins and losses are equally likely."""
    n = wins + losses
    if not n:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / 2**n
    return round(min(1.0, 2 * tail), 4)


PAST = f"""
MATCH (ep:Episode)-[:ABOUT]->(:Port {{locode: $key}})
WHERE ep.closed_at IS NOT NULL AND ep.id STARTS WITH '{portwatcher.SITUATION}:'
MATCH (ep)-[:HAS]->(first:Entry {{seq: 1}}), (ep)-[:HAS]->(end:Entry {{type: 'outcome'}})
RETURN first.state, end.days
"""
ALL_PAST = f"""
MATCH (ep:Episode)-[:HAS]->(first:Entry {{seq: 1}}), (ep)-[:HAS]->(end:Entry {{type: 'outcome'}})
WHERE ep.id STARTS WITH '{portwatcher.SITUATION}:'
RETURN first.state, end.days
"""


def _guesses(graph, key: str, state: str) -> dict:
    """What each way of guessing says, when a spell begins: will it pass within SHORT days?"""

    def passed(rows):
        return [days <= portwatcher.SHORT for seen, days in rows if seen == state]

    # The measure's own reads scan what the replay wrote so far: past the server's 1 s default.
    everyone = passed(graph.ro_query(ALL_PAST, timeout=LONG).result_set)
    base = sum(everyone) * 2 >= len(everyone) if everyone else True
    found = lesson(graph, f"{portwatcher.SITUATION}:{key}:{state}:passes")
    by_lesson = None if not found or found["weight"] == 0 else found["weight"] > 0
    here = passed(graph.ro_query(PAST, {"key": key}, timeout=LONG).result_set)
    by_episodes = None if not here or sum(here) * 2 == len(here) else sum(here) * 2 > len(here)
    return {
        "always_passes": True,
        "base_rate": base,
        "lesson": by_lesson,
        "episodes": by_episodes,
    }


# What the PortWatch days are kept as. Everything else in their graph was written by a replay.
KEPT = {"Port", "State", "Poll", STAMP}


def _clear_replay(graph) -> int:
    """Delete what a replay wrote, and keep the PortWatch days. Returns how many nodes went.
    A node has several labels (a Port is an Entity too): it goes only when none is kept."""
    gone = 0
    for (label,) in graph.ro_query("CALL db.labels() YIELD label RETURN label").result_set:
        if label in KEPT:
            continue
        while True:
            (deleted,) = graph.query(
                f"MATCH (n:`{label}`) WHERE none(l IN labels(n) WHERE l IN $kept) "
                "WITH n LIMIT 10000 DETACH DELETE n RETURN count(n)",
                {"kept": sorted(KEPT)},
                timeout=LONG,
            ).result_set[0]
            gone += deleted
            if deleted < 10000:
                break
    return gone


def memory(days: int, review_every: int, read: bool = True) -> dict:
    """Replays PortWatch day by day through the Port Watcher and the Reviewer, as the poller
    does, on the kept days of real data, in place: a copy would hold them twice in memory. When a port turns quiet or busy, each way of guessing says
    whether the spell will pass within SHORT days; when it ends, each guess is scored.

      always_passes  no memory: the same guess every time
      base_rate      no memory of this port: what most spells so far, at any port, did
      lesson         memory on: the Reviewer's lesson about this port, else the base rate
      episodes       memory on: this port's own past spells, else the base rate
    """
    # This measures what the guesses get right, not how fast the Port Watcher reads: a page
    # of its read may wait behind other work on the server, so the replay gives it time.
    portwatcher.READ_TIMEOUT = LONG
    db = get_db()
    data = db.select_graph(DATA)
    ensure_schema(data, portcalls.KINDS)
    # Without `read`, the days kept from an earlier run are replayed as they are.
    loaded = portwatch.update(data, backfill=days) if read else {"days": [], "state": "not read"}
    graph = data
    _clear_replay(graph)  # what a replay that stopped halfway left
    try:
        span = graph.ro_query(
            "MATCH (:Port)-[:HAS_STATE]->(s:State) WHERE s.calls IS NOT NULL "
            "RETURN min(s.valid_from), max(s.valid_from)",
            timeout=LONG,
        ).result_set[0]
        first, last = span[0].date(), span[1].date()
        guesses, scored, open_at_end = {}, [], 0
        started = time.perf_counter()
        day = first + timedelta(days=portwatcher.LEAST_DAYS)
        n = 0
        while day <= last:
            for did in portwatcher.watch(graph, [str(day)]):
                if did["did"] == "opened":
                    seen = lighthouse.episode(graph, did["episode"])["entries"][0]
                    guesses[did["episode"]] = (
                        _guesses(graph, did["port"], seen["state"]),
                        seen["state"],
                    )
                elif did["did"] == "ended" and did["episode"] in guesses:
                    end = lighthouse.episode(graph, did["episode"])["entries"][-1]
                    said, state = guesses.pop(did["episode"])
                    scored.append(
                        {"state": state, "passed": end["days"] <= portwatcher.SHORT, **said}
                    )
            n += 1
            if n % review_every == 0:
                reviewer.review(graph)
            day += timedelta(days=1)
        open_at_end = len(guesses)
        seconds = round(time.perf_counter() - started)
    finally:
        _clear_replay(graph)

    def score(way: str, rows: list[dict]) -> dict:
        right = sum(
            (row[way] if row[way] is not None else row["base_rate"]) == row["passed"]
            for row in rows
        )
        return {
            "right": right,
            "of": len(rows),
            "accuracy": round(right / len(rows), 3) if rows else None,
            "ci95": _wilson(right, len(rows)),
        }

    result = {
        "days": [str(first), str(last)],
        "portwatch": {"read": len(loaded["days"]), "state": loaded["state"]},
        "spells_scored": len(scored),
        "spells_still_open": open_at_end,
        "passed_within_days": portwatcher.SHORT,
        "share_that_passed": round(sum(r["passed"] for r in scored) / len(scored), 3)
        if scored
        else None,
        "replay_seconds": seconds,
        "review_every_days": review_every,
        "all_spells": {
            way: score(way, scored) for way in ("always_passes", "base_rate", "lesson", "episodes")
        },
    }
    for way in ("lesson", "episodes"):
        covered = [row for row in scored if row[way] is not None]
        wins = sum(row[way] == row["passed"] != row["base_rate"] for row in covered)
        losses = sum(row["base_rate"] == row["passed"] != row[way] for row in covered)
        result[f"where_{way}_spoke"] = {
            "spells": len(covered),
            way: score(way, covered),
            "base_rate": score("base_rate", covered),
            "memory_right_base_wrong": wins,
            "base_right_memory_wrong": losses,
            "sign_test_p": _sign_test(wins, losses),
        }
    return result


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="measure", required=True)
    sub.add_parser("writes").add_argument("--events", type=int, default=300)
    h = sub.add_parser("history")
    h.add_argument("--entities", type=int, default=500)
    h.add_argument("--versions", type=int, default=20)
    h.add_argument("--seed", type=int, default=7)
    c = sub.add_parser("claims")
    c.add_argument("--agents", type=int, default=16)
    c.add_argument("--tasks", type=int, default=500)
    sub.add_parser("tenants").add_argument("--rows", type=int, default=200)
    sub.add_parser("restart").add_argument("--check", action="store_true")
    m = sub.add_parser("memory")
    m.add_argument("--days", type=int, default=400)
    m.add_argument("--review-every", type=int, default=1)
    m.add_argument("--no-read", dest="read", action="store_false", help="replay the kept days only")
    args = parser.parse_args(argv)
    params = {k: v for k, v in vars(args).items() if k != "measure"}
    run = {
        "writes": lambda: writes(args.events),
        "history": lambda: history_exact(args.entities, args.versions, args.seed),
        "claims": lambda: claims(args.agents, args.tasks),
        "tenants": lambda: tenants(args.rows),
        "restart": lambda: restart(args.check),
        "memory": lambda: memory(args.days, args.review_every, args.read),
    }[args.measure]
    result = run()

    def git(*command):
        try:
            found = subprocess.run(
                ["git", *command], check=False, cwd=ROOT, capture_output=True, text=True
            )
            return found.stdout.strip()
        except FileNotFoundError:  # no git where it runs, such as a container
            return None

    # `dirty`: the code that ran differs from the commit, so the commit alone does not say what ran.
    # Where git is missing, as in a container, whoever starts the measure says both.
    status = git("status", "--porcelain", "--", "backend", "lighthouse-memory")
    commit = git("rev-parse", "--short", "HEAD") or os.environ.get("MEASURE_COMMIT")
    dirty = bool(status) if status is not None else os.environ.get("MEASURE_DIRTY") == "1"
    report = {
        "measure": args.measure,
        "at": lighthouse.now(),
        "commit": commit,
        "dirty": dirty if commit else None,
        "params": params,
        "result": result,
    }
    print(json.dumps(report, indent=2, default=str))
    OUT.mkdir(exist_ok=True)
    name = args.measure + ("-check" if args.measure == "restart" and args.check else "")
    (OUT / f"{name}.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
