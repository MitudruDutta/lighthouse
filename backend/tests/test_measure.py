from lighthouse import ensure_schema, open_episode, remember

from app import measure
from app.portcalls import KINDS, PORT


def test_claims_have_one_winner_each(db):
    result = measure.claims(agents=6, tasks=40)
    assert result["claims_won"] == 40
    assert result["tasks_won_twice"] == result["tasks_with_two_claims"] == 0


def test_tenants_see_nothing_of_each_other(db):
    result = measure.tenants(rows=5)
    assert result["seen_from_the_other"] == {"nodes": 0, "search": 0, "history": 0}


def test_history_is_exact_in_order_and_refuses_what_it_cannot_place(db):
    result = measure.history_exact(entities=20, versions=8, seed=3)
    assert result["in_order"]["facts_wrong"] == 0
    assert result["in_order"]["facts_read_back"] == result["in_order"]["rows"]
    shuffled = result["shuffled"]
    assert shuffled["refusals_recorded"] == shuffled["receipts"].get("stale", 0)
    assert shuffled["facts_wrong_without_a_refused_row"] == 0


def test_measures_leave_no_graph_behind(db):
    measure.claims(agents=2, tasks=3)
    measure.history_exact(entities=2, versions=3, seed=1)
    assert not [name for name in db.list_graphs() if name.startswith("measure_claims_")]
    assert not [name for name in db.list_graphs() if name.startswith("measure_history_")]


def test_statistics():
    assert measure._wilson(0, 0) == [0.0, 0.0]
    low, high = measure._wilson(80, 100)
    assert low < 0.8 < high and round(high - low, 2) == 0.16
    assert measure._sign_test(0, 0) == 1.0
    assert measure._sign_test(10, 0) == 0.002
    assert measure._sign_test(5, 5) == 1.0
    assert measure._percentile([1, 2, 3, 4], 0.5) == 2


def test_clearing_a_replay_keeps_the_ports_and_their_days(graph):
    ensure_schema(graph, KINDS)
    rows = [
        {"key": "FIHEL", "t": "2026-10-01T00:00:00", "values": {"name": "Helsinki", "calls": 5}}
    ]
    remember(graph, PORT, rows, by="portwatch")
    open_episode(graph, "port-activity:FIHEL:2026-10-02", "port-watcher", [(PORT, "FIHEL")])
    assert measure._clear_replay(graph) == 1  # the episode
    ports = graph.ro_query("MATCH (p:Port)-[:HAS_STATE]->(s:State) RETURN p.locode, s.calls")
    assert ports.result_set == [["FIHEL", 5]]
    assert graph.ro_query("MATCH (e:Episode) RETURN count(e)").result_set == [[0]]
