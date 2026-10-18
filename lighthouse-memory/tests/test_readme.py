"""The example in the README runs as printed."""

import pathlib
import re
import uuid

import lighthouse

README = pathlib.Path(__file__).parent.parent / "README.md"


def test_readme_example_runs_and_gives_the_printed_results(db):
    code = re.search(r"## Example\n\n```python\n(.*?)```", README.read_text(), re.DOTALL).group(1)
    name = f"test_{uuid.uuid4().hex}"
    assert code.count('select_graph("world")') == 1
    scope: dict = {}
    try:
        exec(code.replace('select_graph("world")', f'select_graph("{name}")'), scope)  # noqa: S102
        device, graph = scope["DEVICE"], scope["graph"]
        assert [s["status"] for s in lighthouse.history(graph, device, "d1")] == ["ok", "hot"]
        assert lighthouse.as_of(graph, device, "d1", "2026-01-01T12:00:00Z")["status"] == "ok"
        assert lighthouse.related(graph, device, "d1", "LOCATED_IN") == ["r2"]
        then = lighthouse.related(graph, device, "d1", "USED_BY", "2026-01-01T12:00:00Z")
        assert then == ["blue", "red"]
        found = lighthouse.search(graph, device, "sensor in the pump room", match="any")
        assert [item["key"] for item in found] == ["d1"]
        assert lighthouse.pointing_at(graph, device, "LOCATED_IN", "r2") == ["d1"]
        entries = lighthouse.episode(graph, "d1-overheat")["entries"]
        assert [(e["id"], e["type"]) for e in entries] == [
            ("d1-overheat/1", "observation"),
            ("d1-overheat/2", "forecast"),
            ("d1-overheat/3", "outcome"),
        ]
        assert entries[0]["cites"] == [("Device", "d1")]
        assert lighthouse.episodes_about(graph, device, "d1")[0]["outcome"]["failed"] is False
        (learned,) = lighthouse.lessons_about(graph, device, "d1")
        assert (learned["id"], learned["weight"]) == ("hot-in-r2", 1)
        (fitting,) = lighthouse.playbooks_for(graph, {"status": "hot", "room": "r2"})
        assert fitting["id"] == "hot-device#1" and fitting["steps"][0] == {"do": "check the fan"}
        (handoff,) = lighthouse.handoffs_for(graph, "planner", waiting_only=False)
        assert handoff["points_to"] == [("Device", "d1"), ("Episode", "d1-overheat")]
        assert handoff["accepted_at"] is not None
        talk = lighthouse.messages(graph, "ann", "main")
        assert [(m["seq"], m["role"], m["by"]) for m in talk] == [
            (1, "user", "ann"),
            (2, "helper", "assistant"),
        ]
        assert [m["text"] for m in talk] == ["why is d1 hot?", "the fan stopped"]
        assert lighthouse.said_about(graph, "ann", (device, "d1"))[0]["text"] == "the fan stopped"
        assert lighthouse.messages(graph, "bob", "main") == []
        assert [g["size"] for g in lighthouse.groups(graph, [device])] == [5]
        (step,) = lighthouse.connection(graph, (device, "d1"), (scope["ROOM"], "r1"))
        assert (step["relation"], step["forward"], step["current"]) == ("LOCATED_IN", True, False)
        assert str(step["since"])[:16] == "2026-01-01 00:00" and str(step["until"])[:16] == (
            "2026-01-02 00:00"
        )
    finally:
        db.select_graph(name).delete()
