import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from conftest import connect
from devices import count

from lighthouse import add_task, claim, complete, release
from lighthouse.tasks import MAX_LEASE


def test_task_goes_from_open_to_claimed_to_done(graph):
    assert add_task(graph, "forecast:1", "forecast", ref="portcall:1") is True
    assert claim(graph, "forecaster-1", "forecast") == {
        "id": "forecast:1",
        "kind": "forecast",
        "ref": "portcall:1",
        "until": None,
    }
    owner = "(:Task {id: 'forecast:1', status: 'claimed'})-[c:CLAIMED_BY]->(:Agent)"
    assert count(graph, f"{owner} WHERE endNode(c).id = 'forecaster-1'", "c") == 1
    assert complete(graph, "forecaster-1", "forecast:1") is True
    assert count(graph, "(t:Task {status: 'done'}) WHERE t.done_at IS NOT NULL") == 1


def test_claim_returns_none_and_writes_nothing_when_no_task_is_open(graph):
    assert claim(graph, "idle", "forecast") is None
    add_task(graph, "review:1", "review")
    assert claim(graph, "idle", "forecast") is None  # another kind is not offered
    assert count(graph, "(a:Agent)") == 0 and count(graph, "(:Task {status: 'open'})") == 1


def test_claimed_task_is_not_offered_again(graph):
    add_task(graph, "t1", "forecast")
    assert claim(graph, "a", "forecast")["id"] == "t1"
    assert claim(graph, "b", "forecast") is None
    assert claim(graph, "a", "forecast") is None
    assert count(graph, "(:Task)-[c:CLAIMED_BY]->(:Agent)", "c") == 1


def test_adding_a_task_twice_keeps_the_first(graph):
    assert add_task(graph, "t1", "forecast", ref="portcall:1") is True
    claim(graph, "a", "forecast")
    assert add_task(graph, "t1", "review", ref="portcall:2") is False
    task = graph.ro_query("MATCH (t:Task) RETURN t.kind, t.status, t.ref").result_set
    assert task == [["forecast", "claimed", "portcall:1"]]


def test_task_without_ref(graph):
    add_task(graph, "t1", "forecast")
    assert claim(graph, "a", "forecast") == {
        "id": "t1",
        "kind": "forecast",
        "ref": None,
        "until": None,
    }


def test_tasks_are_claimed_oldest_first(graph):
    # Created in the same second: the identifier breaks the tie.
    for task_id in ("t3", "t1", "t2"):
        add_task(graph, task_id, "forecast")
    graph.query("MATCH (t:Task {id: 't3'}) SET t.created_at = localdatetime('2020-01-01T00:00:00')")
    assert [claim(graph, "a", "forecast")["id"] for _ in range(3)] == ["t3", "t1", "t2"]


def test_only_the_owner_completes_a_task_and_only_once(graph):
    add_task(graph, "t1", "forecast")
    assert complete(graph, "a", "t1") is False  # not claimed yet
    claim(graph, "a", "forecast")
    assert complete(graph, "b", "t1") is False  # not the owner
    assert complete(graph, "a", "missing") is False
    assert complete(graph, "a", "t1") is True
    assert complete(graph, "a", "t1") is False  # already done
    assert count(graph, "(:Task {status: 'done'})") == 1


@pytest.mark.parametrize("bad", [None, "", 7])
def test_task_and_agent_names_must_be_text(graph, bad):
    add_task(graph, "t1", "forecast")
    for call in (
        lambda: add_task(graph, bad, "forecast"),
        lambda: add_task(graph, "t2", bad),
        lambda: claim(graph, bad, "forecast"),
        lambda: claim(graph, "a", bad),
        lambda: complete(graph, bad, "t1"),
        lambda: complete(graph, "a", bad),
        lambda: release(graph, bad, "t1"),
        lambda: release(graph, "a", bad),
    ):
        with pytest.raises(ValueError, match="must be text"):
            call()
    assert count(graph, "(t:Task {status: 'open'})") == 1 and count(graph, "(a:Agent)") == 0


# --- order, leases, and release ----------------------------------------------------------


def age(graph, task_id: str) -> None:
    """Make a task the oldest, so that it would be claimed first if it were free."""
    graph.query(
        "MATCH (t:Task {id: $id}) SET t.created_at = localdatetime('2020-01-01T00:00:00')",
        {"id": task_id},
    )


def run_out(graph, task_id: str) -> None:
    """Let the lease of a claim run out, as if its time had passed."""
    graph.query(
        "MATCH (t:Task {id: $id}) SET t.until = localdatetime('2020-01-01T00:00:00')",
        {"id": task_id},
    )


def test_task_waits_for_the_tasks_it_comes_after(graph):
    add_task(graph, "fetch", "work")
    add_task(graph, "check", "work")
    assert add_task(graph, "report", "work", after=["fetch", "check", "fetch"]) is True
    age(graph, "report")
    first, second = claim(graph, "a", "work")["id"], claim(graph, "a", "work")["id"]
    assert {first, second} == {"fetch", "check"}  # report waits, though it is oldest
    assert claim(graph, "b", "work") is None  # both are claimed, neither is done
    complete(graph, "a", "fetch")
    assert claim(graph, "b", "work") is None  # check is not done yet
    complete(graph, "a", "check")
    assert claim(graph, "b", "work")["id"] == "report"
    assert count(graph, "(:Task {id: 'report'})-[e:AFTER]->(:Task)", "e") == 2


def test_task_that_comes_after_one_that_does_not_exist_is_not_added(graph):
    add_task(graph, "fetch", "work")
    with pytest.raises(ValueError, match="does not exist"):
        add_task(graph, "report", "work", after=["fetch", "nowhere"])
    with pytest.raises(ValueError, match="does not exist"):
        add_task(graph, "loop", "work", after=["loop"])  # a task cannot wait for itself
    assert count(graph, "(t:Task)") == 1 and count(graph, "()-[e:AFTER]->()", "e") == 0
    assert add_task(graph, "fetch", "work", after=["nowhere"]) is False  # it exists already


AFTER = {
    "not a list": ("fetch", "a list"),
    "none": (None, "a list"),
    "too many": ([f"t{n}" for n in range(201)], "at most 200"),
    "empty id": ([""], "task ids"),
    "number": ([7], "task ids"),
    "space at the end": (["a b "], "task ids"),
    "NUL": (["a\x00"], "task ids"),
}


@pytest.mark.parametrize("name", AFTER)
def test_after_of_a_wrong_form_is_refused(graph, name):
    after, reason = AFTER[name]
    with pytest.raises(ValueError, match=reason):
        add_task(graph, "report", "work", after=after)
    assert count(graph, "(t:Task)") == 0


def test_claim_with_a_lease_runs_out_and_goes_to_another_agent(graph):
    add_task(graph, "t1", "work")
    before = datetime.now(UTC).replace(microsecond=0)
    task = claim(graph, "a", "work", lease=60)
    assert task["id"] == "t1"
    assert before + timedelta(seconds=60) <= task["until"] <= before + timedelta(seconds=62)
    assert claim(graph, "b", "work", lease=60) is None  # the lease holds
    run_out(graph, "t1")
    assert claim(graph, "b", "work", lease=60)["id"] == "t1"
    assert complete(graph, "a", "t1") is False  # a lost the task when its lease ran out
    assert complete(graph, "b", "t1") is True
    assert count(graph, "(:Task)-[c:CLAIMED_BY]->(:Agent)", "c") == 2  # both claims are kept
    done = graph.ro_query("MATCH (t:Task) RETURN t.owner, t.until").result_set
    assert done == [["b", None]]


def test_owner_whose_lease_ran_out_completes_while_nobody_took_the_task(graph):
    add_task(graph, "t1", "work")
    claim(graph, "a", "work", lease=1)
    run_out(graph, "t1")
    assert complete(graph, "a", "t1") is True
    assert claim(graph, "b", "work") is None


def test_claim_without_a_lease_does_not_run_out(graph):
    add_task(graph, "t1", "work")
    claim(graph, "a", "work")
    graph.query("MATCH (t:Task) SET t.created_at = localdatetime('2000-01-01T00:00:00')")
    assert claim(graph, "b", "work") is None


@pytest.mark.parametrize("lease", [0, -1, 1.5, "60", True, MAX_LEASE + 1])
def test_lease_of_a_wrong_form_is_refused(graph, lease):
    add_task(graph, "t1", "work")
    with pytest.raises(ValueError, match="lease"):
        claim(graph, "a", "work", lease=lease)
    assert count(graph, "(:Task {status: 'open'})") == 1


def test_owner_releases_a_task_for_another_agent(graph):
    add_task(graph, "t1", "work")
    assert release(graph, "a", "t1") is False  # not claimed
    claim(graph, "a", "work", lease=60)
    assert release(graph, "b", "t1") is False  # not the owner
    assert release(graph, "a", "t1") is True
    assert graph.ro_query("MATCH (t:Task) RETURN t.status, t.owner, t.until").result_set == [
        ["open", None, None]
    ]
    assert claim(graph, "b", "work")["id"] == "t1"
    assert complete(graph, "a", "t1") is False and complete(graph, "b", "t1") is True
    assert release(graph, "b", "t1") is False  # a done task stays done


def race(graph, agents: int, claims_each: int) -> list[tuple[str, str]]:
    """Agents claim at the same moment, each on its own connection. Returns (agent, task)."""
    won = []
    start = threading.Barrier(agents)

    def agent(name):
        own = connect().select_graph(graph.name)
        start.wait(timeout=30)
        for _ in range(claims_each):
            task = claim(own, name, "forecast")
            if task:
                won.append((name, task["id"]))

    with ThreadPoolExecutor(max_workers=agents) as pool:
        for future in [pool.submit(agent, f"agent-{n}") for n in range(agents)]:
            future.result()  # raises what the agent raised
    return won


def test_many_agents_racing_for_many_tasks_never_double_claim(graph):
    tasks = {f"t{n:03d}" for n in range(60)}
    for task_id in tasks:
        add_task(graph, task_id, "forecast")
    won = race(graph, agents=12, claims_each=10)  # 120 attempts for 60 tasks
    assert sorted(task for _, task in won) == sorted(tasks)  # every task won exactly once
    owners = graph.ro_query(
        "MATCH (t:Task) OPTIONAL MATCH (t)-[c:CLAIMED_BY]->(a:Agent) "
        "RETURN t.id, t.status, count(c), collect(a.id)"
    ).result_set
    assert len(owners) == 60
    assert all(status == "claimed" and n == 1 for _, status, n, _ in owners)
    assert {(agents[0], task) for task, _, _, agents in owners} == set(won)
    assert count(graph, "(a:Agent)") == len({agent for agent, _ in won})  # no duplicate Agent


def test_one_task_has_one_winner_in_every_round(graph):
    for round_number in range(25):
        add_task(graph, f"round-{round_number}", "forecast")
        won = race(graph, agents=8, claims_each=1)
        assert len(won) == 1, f"round {round_number}: {won}"
    assert count(graph, "(:Task)-[c:CLAIMED_BY]->(:Agent)", "c") == 25
