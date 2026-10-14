"""What a berth held at one time, and where more is expected than that."""

from datetime import UTC, datetime

from feed import poll, record, when
from lighthouse import now

from app.berths import loads, overloads

VC2 = "FIHEL/VUOS/VC2"


def call(id, minute=0, berth="VC2", **times) -> dict:
    """A port call of its own vessel at a berth of FIHEL. Times are minutes after T0."""
    return record(id=id, minute=minute, imo=9000000 + id, berth=berth, **times)


def load(graph, at=0, berth=VC2) -> dict:
    (found,) = [load for load in loads(graph, when(at)) if load["berth"] == berth]
    return found


def test_one_port_call_is_no_overload(graph):
    poll(graph, 0, call(1, eta=600, etd=900))
    assert loads(graph, when(0)) == [
        {"berth": VC2, "capacity": 1, "together": [], "overload": None}
    ]
    assert overloads(graph, when(0)) == []


def test_two_port_calls_expected_at_one_time_are_an_overload(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    assert overloads(graph, when(0)) == [
        {
            "berth": VC2,
            "capacity": 1,
            "together": [],
            # From the arrival of the second to the departure of the first.
            "overload": {"from": when(700), "until": when(900), "most": 2, "calls": [1, 2]},
        }
    ]


def test_one_that_leaves_when_the_next_arrives_is_no_overload(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=900, etd=1000))
    assert overloads(graph, when(0)) == []
    poll(graph, 1, call(2, minute=1, eta=899, etd=1000))  # one minute earlier
    assert load(graph, 1)["overload"] == {
        "from": when(899),
        "until": when(900),
        "most": 2,
        "calls": [1, 2],
    }


def test_what_was_alongside_together_shows_what_a_berth_takes(graph):
    poll(graph, 0, call(1, ata=10, atd=200), call(2, ata=50, atd=300), call(3, ata=250, atd=400))
    # Two were there at one time: 1 and 2, and later 2 and 3.
    assert load(graph, 500) | {"together": None} == {
        "berth": VC2,
        "capacity": 2,
        "together": None,
        "overload": None,
    }
    assert load(graph, 500)["together"] in ([1, 2], [2, 3])
    poll(graph, 500, call(4, minute=500, eta=600, etd=900), call(5, minute=500, eta=700, etd=1000))
    assert overloads(graph, when(500)) == []  # two are expected, and it held two
    poll(graph, 501, call(6, minute=501, eta=750, etd=800))
    assert load(graph, 501)["overload"] == {
        "from": when(750),
        "until": when(800),
        "most": 3,
        "calls": [4, 5, 6],
    }


def test_three_that_were_alongside_at_one_time_are_counted_at_the_arrival_of_the_last(graph):
    poll(graph, 0, call(1, ata=10, atd=300), call(2, ata=20, atd=300), call(3, ata=30, atd=40))
    assert (load(graph, 500)["capacity"], load(graph, 500)["together"]) == (3, [1, 2, 3])


def test_one_that_arrives_as_the_other_leaves_was_not_alongside_with_it(graph):
    poll(graph, 0, call(1, ata=10, atd=200), call(2, ata=200, atd=300))
    assert (load(graph, 500)["capacity"], load(graph, 500)["together"]) == (1, [1])
    poll(graph, 501, call(3, minute=501, ata=299, atd=400))  # one minute with the second
    assert (load(graph, 501)["capacity"], load(graph, 501)["together"]) == (2, [2, 3])


def test_port_call_that_is_alongside_holds_the_berth_now(graph):
    # 1 arrived and has not left, though its expected departure is long past.
    poll(graph, 0, call(1, eta=5, ata=10, etd=100), call(2, eta=700, etd=900))
    assert overloads(graph, when(500)) == []  # 2 is expected later: nobody knows when 1 leaves
    assert load(graph, 800)["overload"] == {
        "from": when(800),
        "until": datetime.fromtimestamp(when(800).timestamp() + 1, UTC),
        "most": 2,
        "calls": [1, 2],
    }
    # Both are there now: the berth has held two, and that is no overload any more.
    poll(graph, 801, call(2, minute=801, eta=700, ata=750, etd=900))
    assert (load(graph, 801)["capacity"], load(graph, 801)["overload"]) == (2, None)


def test_port_call_that_left_is_not_expected(graph):
    poll(graph, 0, call(1, ata=10, atd=100, etd=900), call(2, eta=50, etd=900))
    assert overloads(graph, when(0)) == [] and load(graph)["capacity"] == 1


def test_overload_is_the_first_stretch_from_the_time_of_the_look(graph):
    poll(graph, 0, call(1, eta=100, etd=300), call(2, eta=200, etd=400))
    poll(graph, 0, call(3, eta=600, etd=900), call(4, eta=700, etd=950), call(5, eta=710, etd=720))
    first = {"from": when(200), "until": when(300), "most": 2, "calls": [1, 2]}
    assert load(graph, 0)["overload"] == first
    assert load(graph, 250)["overload"] == first | {"from": when(250)}
    # 1 and 2 are over. The next stretch holds all three that are there in it, from the
    # arrival of the second to the time one is left.
    later = {"from": when(700), "until": when(900), "most": 3, "calls": [3, 4, 5]}
    assert load(graph, 450)["overload"] == later
    assert load(graph, 715)["overload"] == later | {"from": when(715)}
    assert load(graph, 725)["overload"] == {
        "from": when(725),
        "until": when(900),
        "most": 2,
        "calls": [3, 4],
    }
    assert load(graph, 900)["overload"] is None


def test_stretch_ends_when_as_many_are_left_as_the_berth_held(graph):
    poll(graph, 0, call(1, ata=-900, atd=-500), call(2, ata=-800, atd=-600))  # it held two
    poll(graph, 0, call(3, eta=100, etd=400), call(4, eta=150, etd=300), call(5, eta=200, etd=500))
    assert load(graph, 0)["overload"] == {
        "from": when(200),
        "until": when(300),  # 4 leaves: two are left, and it held two
        "most": 3,
        "calls": [3, 4, 5],
    }


def test_berths_do_not_mix(graph):
    poll(
        graph,
        0,
        call(1, eta=600, etd=900),
        call(2, eta=700, etd=1000, berth="VA8"),
        record(id=3, imo=9000003, port="FIKTK", eta=700, etd=1000),  # the same code, another port
        record(id=4, imo=9000004, area="LOV", eta=700, etd=1000),  # and another port area
    )
    assert overloads(graph, when(0)) == []
    assert [found["berth"] for found in loads(graph, when(0))] == [
        "FIHEL/LOV/VC2",
        "FIHEL/VUOS/VA8",
        "FIHEL/VUOS/VC2",
        "FIKTK/VUOS/VC2",
    ]


def test_port_call_counts_at_the_berth_it_has_now(graph):
    poll(graph, 0, call(1, eta=600, etd=900), call(2, eta=700, etd=1000))
    assert [found["berth"] for found in overloads(graph, when(0))] == [VC2]
    poll(
        graph,
        5,
        call(2, minute=5, eta=700, etd=1000, berth="VA8"),
        call(3, eta=800, etd=950, berth="VA8"),
    )
    assert [(o["berth"], o["overload"]["calls"]) for o in overloads(graph, when(5))] == [
        ("FIHEL/VUOS/VA8", [2, 3])
    ]
    poll(graph, 9, call(2, minute=9, eta=700, etd=1000, berth=None))  # no berth any more
    assert overloads(graph, when(9)) == []


def test_port_call_with_times_that_cannot_be_is_left_out(graph):
    poll(
        graph,
        0,
        call(1, eta=600, etd=900),
        call(2, eta=700, etd=None),  # no end
        call(3, eta=None, etd=800),  # no start
        call(4, eta=800, etd=700),  # ends before it starts
        call(5, eta=650, etd=650),  # no time at all
        # Arrived half a year before it is expected to leave: it would be alongside for good.
        call(6, eta=600, ata=-260_000, etd=900),
    )
    assert load(graph) == {"berth": VC2, "capacity": 1, "together": [], "overload": None}
    poll(graph, 1, call(7, eta=-172_000, ata=-171_000, etd=700))  # 119 days: a long stay
    assert load(graph, 1)["overload"]["calls"] == [1, 7]


def test_what_ended_long_ago_does_not_count(graph):
    old = -91 * 24 * 60  # 91 days before T0
    poll(graph, 0, call(1, ata=old, atd=old + 500), call(2, ata=old + 100, atd=old + 600))
    poll(
        graph,
        0,
        call(3, ata=-5000, atd=-4000, berth="VA8"),
        call(4, ata=-4500, atd=-3000, berth="VA8"),
    )
    assert [(found["berth"], found["capacity"]) for found in loads(graph, when(0))] == [
        ("FIHEL/VUOS/VA8", 2)
    ]


def test_look_cannot_be_ahead_of_the_clock(graph):
    ahead = 200_000  # minutes after T0: months from now
    poll(graph, 0, call(1, eta=ahead, etd=ahead + 300), call(2, eta=ahead + 100, etd=ahead + 400))
    expected = {"from": when(ahead + 100), "until": when(ahead + 300), "most": 2, "calls": [1, 2]}
    assert datetime.fromisoformat(now()).replace(tzinfo=UTC) < when(ahead)
    # A look from the year 2999 would see nothing left. It is a look from now.
    for at in (None, "2999-01-01T00:00:00Z", when(ahead + 350)):
        assert [found["overload"] for found in loads(graph, at)] == [expected]
