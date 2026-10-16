"""Trust in an agent: each kind of evidence counted for and against it, from what the graph
records, and one score that no kind of evidence drowns."""

import pytest
from devices import DEVICE, when, write

from lighthouse import (
    agent_trust,
    close_episode,
    invalidate_entry,
    learn,
    open_episode,
    ran,
    record,
    remember,
    weigh,
    write_playbook,
)


def version(key: str, t: str, status: str) -> dict:
    return {"key": key, "t": t, "values": {"status": status}, "relations": {}}


@pytest.fixture
def worked(graph):
    """The agent "eye": three entries, one invalidated; two closed episodes, one that a
    lesson rests on and one that contradicts it; two playbook runs, one failed; and four
    versions, one replaced within a minute."""
    write(graph, version("d1", "2026-01-01T00:00:00Z", "ok"))  # by another writer
    rows = [
        version("d1", "2026-01-01T00:10:00Z", "hot"),  # held ten minutes
        version("d2", "2026-01-01T00:00:00Z", "ok"),  # replaced after 30 seconds
    ]
    remember(graph, DEVICE, rows, by="eye")
    remember(graph, DEVICE, [version("d2", "2026-01-01T00:00:30Z", "hot")], by="eye")
    remember(graph, DEVICE, [version("d1", "2026-01-01T00:20:00Z", "ok")], by="eye")
    for name, minute in (("e1", 1), ("e2", 3)):
        open_episode(graph, name, by="eye", about=[(DEVICE, "d1")], at=when(minute))
        record(graph, name, "observation", "eye", {"saw": "hot"}, at=when(minute))
        close_episode(graph, name, by="eye", outcome={"ok": True}, at=when(minute + 1))
    open_episode(graph, "e3", by="eye", at=when(10))
    wrong = record(graph, "e3", "observation", "eye", {"saw": "hot"}, at=when(10))["id"]
    invalidate_entry(graph, wrong, by="reviewer", reason="the sensor was faulty")
    learn(graph, "hot-passes", "reviewer", "A hot d1 passes", ["e1"], [(DEVICE, "d1")])
    weigh(graph, "hot-passes", "reviewer", "e2", agrees=False)
    write_playbook(graph, "cool", "reviewer", {"status": "hot"}, [{"do": "x"}], ["e1"], needs=1)
    ran(graph, "cool", "eye", "e1", succeeded=True)
    ran(graph, "cool", "eye", "e2", succeeded=False)
    return graph


def test_each_kind_of_evidence_is_counted_for_and_against(worked):
    found = agent_trust(worked, "eye")
    assert {k: v for k, v in found.items() if k not in ("agent", "score")} == {
        "entries_written": 5,  # an observation and an outcome in e1 and e2, and e3's one
        "entries_invalidated": 1,
        "closed_episodes": 2,
        "corroborated_episodes": 1,
        "contradicted_episodes": 1,
        "playbook_runs": 2,
        "runs_succeeded": 1,
        "runs_failed": 1,
        "states_written": 4,
        "states_short_lived": 1,  # d2 was replaced after 30 seconds
    }


def test_the_score_is_the_mean_of_the_smoothed_rates(worked):
    rates = [(4 + 1) / (5 + 2), (1 + 1) / (2 + 2), (1 + 1) / (2 + 2), (3 + 1) / (4 + 2)]
    assert agent_trust(worked, "eye")["score"] == round(sum(rates) / 4, 4)


def test_an_agent_without_evidence_has_no_score(graph):
    found = agent_trust(graph, "nobody")
    assert found["score"] is None and found["entries_written"] == 0
    assert found["states_written"] == 0 and found["playbook_runs"] == 0


def test_a_name_that_is_not_one_is_refused(graph):
    for wrong in ("", " eye", "a\x00b", 7):
        with pytest.raises(ValueError):
            agent_trust(graph, wrong)
