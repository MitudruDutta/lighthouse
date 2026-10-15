"""The poller: each read is stored, watched, and reviewed, and a read that fails is not the end."""

import threading

import pytest
from feed import feed_time, record
from lighthouse import episode

from app import poller


def feed(minute, *records) -> dict:
    return {"dataUpdatedTime": feed_time(minute), "portCalls": list(records)}


def call(id, **times) -> dict:
    return record(id=id, imo=9000000 + id, **times)


def test_one_read_is_stored_watched_and_kept(graph):
    def read():
        return feed(5, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))

    summary = poller.poll_once(graph, read)
    assert summary["port_calls"] == {"created": 2}
    assert summary["watcher"] == {"opened": 1}
    assert summary["reviewer"] == {"lessons": {}, "playbooks": {}, "runs": {}}
    assert summary["feed_time"] == feed_time(5) and summary["ms"] >= 0
    assert poller.last_poll(graph) == summary
    (name,) = graph.ro_query("MATCH (ep:Episode) RETURN ep.id").result_set[0]
    assert episode(graph, name)["about"][0] == ("Berth", "FIHEL/VUOS/VC2")


def test_the_same_read_again_changes_nothing(graph):
    def read():
        return feed(5, call(1, eta=600, etd=900))

    poller.poll_once(graph, read)
    again = poller.poll_once(graph, read)
    assert again["port_calls"] == {"unchanged": 1} and again["watcher"] == {}
    assert graph.ro_query("MATCH (p:Poll) RETURN count(p)").result_set == [[1]]


def test_before_the_first_read_there_is_no_summary(graph):
    assert poller.last_poll(graph) is None


def test_a_read_that_fails_is_logged_and_the_next_one_comes(graph, caplog):
    stop = threading.Event()
    reads = []

    def read():
        reads.append(1)
        if len(reads) == 1:
            raise OSError("the feed is down")
        stop.set()  # the second read is the last one of this test
        return feed(5, call(1))

    poller.run(graph, every=0, stop=stop, read=read)
    assert len(reads) == 2
    assert "reading the feed failed" in caplog.text and "the feed is down" in caplog.text
    assert poller.last_poll(graph)["port_calls"] == {"created": 1}


def test_what_the_reviewer_learned_is_in_the_summary(graph, monkeypatch):
    learned = {"lessons": [{"status": "learned"}], "playbooks": [], "runs": []}
    monkeypatch.setattr(poller, "review", lambda graph: learned)
    summary = poller.poll_once(graph, lambda: feed(5, call(1)))
    assert summary["reviewer"] == {"lessons": {"learned": 1}, "playbooks": {}, "runs": {}}


@pytest.mark.parametrize("every", ["0", "59"])
def test_reads_closer_than_a_minute_are_refused(every, monkeypatch):
    def no_database():
        raise AssertionError("the database was reached")

    monkeypatch.setattr(poller, "get_db", no_database)
    with pytest.raises(SystemExit):
        poller.main(["test_graph_never_made", "--every", every])
