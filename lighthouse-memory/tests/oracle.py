"""An independent oracle for the write rule: random histories of devices, the rows a source
would send for them, and the checks that the graph holds exactly what they say."""

import random

from devices import DEVICE, when, windows

from lighthouse import history


def random_timelines(rng: random.Random, devices: int, snapshots: int):
    """Per device: the snapshots a source would send, and the history they must give."""
    feed, expected = [], {}
    for n in range(devices):
        key, minute = f"d{n}", rng.randint(0, 50)
        now_true = {"status": "ok", "level": 1, "room": "r1", "teams": ("red",)}
        expected[key] = []
        for _ in range(snapshots):
            for _ in range(rng.choice((0, 0, 1, 1, 2))):
                what = rng.choice(("status", "level", "room", "teams"))
                now_true[what] = {
                    "status": lambda: rng.choice(("ok", "hot", None)),
                    "level": lambda: rng.randint(1, 4),
                    "room": lambda: rng.choice(("r1", "r2", "r3", None)),
                    "teams": lambda: tuple(rng.sample(("red", "blue", "green"), rng.randint(0, 3))),
                }[what]()
            snapshot = dict(now_true, teams=frozenset(now_true["teams"]))
            if not expected[key] or expected[key][-1][1] != snapshot:
                expected[key].append((minute, snapshot))
            feed.append((minute, key, dict(now_true)))
            minute += rng.randint(1, 40)
    return feed, expected


def as_row(minute, key, v) -> dict:
    values = {"status": v["status"], "level": v["level"]}
    relations = {"LOCATED_IN": v["room"], "USED_BY": list(v["teams"])}
    return {"key": key, "t": when(minute), "values": values, "relations": relations}


def expected_windows(versions, targets_of) -> list[tuple]:
    """The edges a relation must have: one per unbroken stay of a target."""
    edges, open_since = [], {}
    for minute, snapshot in versions:
        targets = targets_of(snapshot)
        for target in sorted(set(open_since) - targets):
            edges.append((target, when(open_since.pop(target)), when(minute)))
        for target in targets - set(open_since):
            open_since[target] = minute
    edges += [(target, when(start), None) for target, start in open_since.items()]
    return sorted(edges, key=lambda e: (e[1], e[0]))


def assert_matches_the_oracle(graph, expected):
    for key, versions in expected.items():
        got = [
            (s["valid_from"], s.get("valid_to"), s.get("status"), s["level"])
            for s in history(graph, DEVICE, key)
        ]
        ends = [when(minute) for minute, _ in versions[1:]] + [None]
        want = [
            (when(minute), end, v["status"], v["level"]) for (minute, v), end in zip(versions, ends)
        ]
        assert got == want, key
        rooms = expected_windows(versions, lambda v: {v["room"]} - {None})
        assert windows(graph, "LOCATED_IN", key) == rooms, key
        teams = expected_windows(versions, lambda v: set(v["teams"]))
        assert windows(graph, "USED_BY", key) == teams, key


def history_of(feed) -> dict:
    """The history that rows give in the order of their times: per entity, every snapshot
    that differs from the one before it."""
    expected: dict[str, list] = {}
    for minute, key, v in sorted(feed, key=lambda item: item[0]):
        snapshot = dict(v, teams=frozenset(v["teams"]))
        versions = expected.setdefault(key, [])
        if not versions or versions[-1][1] != snapshot:
            versions.append((minute, snapshot))
    return expected
