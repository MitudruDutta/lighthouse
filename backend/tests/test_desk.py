"""The Desk, driven by a model that is a script here: the tools it picks are called over MCP,
what it concludes goes into the episode with what the tools read, and a person's sessions
are kept in the tenant's graph."""

import json
import uuid

import pytest
from feed import poll, record, when
from lighthouse import (
    add_task,
    claim,
    close_episode,
    context,
    ensure_schema,
    episode,
    handoffs_for,
    messages,
    open_episode,
)

from app import desk
from app.watcher import watch

VC2 = "FIHEL/VUOS/VC2"


def call(name, **arguments) -> dict:
    return {
        "id": f"c-{name}",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


class Script:
    """A model that gives the replies it was given, in order, and keeps what it was asked."""

    def __init__(self, *replies):
        self.replies, self.asked = list(replies), []

    def __call__(self, conversation, tools=None):
        self.asked.append({"conversation": [dict(m) for m in conversation], "tools": tools})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            return {"role": "assistant", "content": reply}
        for wanted in reply:
            arguments = wanted["function"]["arguments"]
            if not isinstance(arguments, str):
                wanted["function"]["arguments"] = json.dumps(arguments)
        return {"role": "assistant", "content": "", "tool_calls": reply}


def ports_call(id, **times) -> dict:
    return record(id=id, imo=9000000 + id, **times)


@pytest.fixture
def handed(graph):
    """Two port calls expected at VC2 together: the Watcher opens an episode, raises a task,
    and hands the episode to the desk."""
    poll(graph, 0, ports_call(1, eta=600, etd=900), ports_call(2, eta=700, etd=1000))
    (opened,) = watch(graph, when(5))
    return opened["episode"]


def test_a_handed_episode_is_assessed_with_the_tools_the_model_picked(graph, handed):
    model = Script(
        [call("look", kind="Berth", key=VC2), call("lessons_about", kind="Berth", key=VC2)],
        "VC2 has two port calls expected at once and has held one. Propose another berth.",
    )
    (done,) = desk.work(graph, model)
    assert (done["episode"], done["did"]) == (handed, "assessed")
    assert done["tools"] == [
        f"look(kind=Berth, key={VC2})",
        f"lessons_about(kind=Berth, key={VC2})",
    ]
    entry = episode(graph, handed)["entries"][-1]
    assert (entry["type"], entry["by"]) == ("assessment", "desk")
    assert entry["text"].startswith("VC2 has two port calls") and entry["model"]
    assert entry["cites"] == [("Berth", VC2)]  # what look read; lessons_about is no evidence
    # The model was given the ask of the handoff, the episode, and every tool.
    first = model.asked[0]
    assert handed in first["conversation"][1]["content"]
    assert "port calls are expected at a berth" in first["conversation"][1]["content"]
    assert {t["function"]["name"] for t in first["tools"]} >= {"look", "unusual_ports", "note"}
    # What the tools answered went back to the model.
    answers = [m for m in model.asked[1]["conversation"] if m["role"] == "tool"]
    assert [json.loads(a["content"])["key"] for a in answers[:1]] == [VC2]
    # The handoff is taken and the task is done.
    assert handoffs_for(graph, "desk") == []
    assert claim(graph, "desk", "berth-overload") is None


def test_a_model_that_fails_gives_the_task_back(graph, handed):
    (done,) = desk.work(graph, Script(RuntimeError("the model service answered 503")))
    assert done["did"] == "failed" and "503" in done["reason"]
    assert [e["type"] for e in episode(graph, handed)["entries"]] == ["observation", "action"]
    assert [h["id"] for h in handoffs_for(graph, "desk")] == [handed]
    assert claim(graph, "desk", "berth-overload")["id"] == handed  # free again


def test_an_answer_of_nothing_is_a_failure(graph, handed):
    (done,) = desk.work(graph, Script("   "))
    assert done["did"] == "failed" and "no answer" in done["reason"]


def test_an_episode_that_ended_is_done_without_the_model(graph, handed):
    close_episode(graph, handed, "watcher", {"held": True}, at=when(6))
    (done,) = desk.work(graph, Script())  # a model that is asked would fail: it has no reply
    assert done["did"] == "ended before the desk looked"
    assert handoffs_for(graph, "desk") == [] and claim(graph, "desk", "berth-overload") is None


def test_nothing_handed_is_nothing_done(graph):
    assert desk.work(graph, Script()) == []


def test_the_model_must_answer_after_the_last_round(graph, handed, monkeypatch):
    monkeypatch.setattr(desk, "ROUNDS", 2)
    bad = [{"id": "x", "type": "function", "function": {"name": "look", "arguments": "{nope"}}]
    model = Script(bad, [call("look", kind="Ship", key="1")], "Two port calls overlap at VC2.")
    (done,) = desk.work(graph, model)
    assert done["did"] == "assessed" and len(model.asked) == 3
    assert model.asked[-1]["tools"] is None  # the last turn has no tools to call
    told = [m["content"] for m in model.asked[-1]["conversation"] if m["role"] == "tool"]
    assert told[0] == "The arguments were not a JSON object."
    assert "This lookup is unavailable" in told[1]
    assert "kind must be one of" not in told[1]  # internal tool errors stay in logs
    assert episode(graph, handed)["entries"][-1]["cites"] == []


@pytest.fixture
def memory(db):
    """The tenant's own graph, where sessions are kept."""
    memory = db.select_graph(f"test_{uuid.uuid4().hex}")
    ensure_schema(memory)
    yield memory
    memory.delete()


def test_answers_are_kept_and_earlier_sessions_recalled(graph, handed, memory):
    model = Script(
        [call("look", kind="Berth", key=VC2)],
        "VC2 is overloaded: port calls 1 and 2 are expected together.",
    )
    first = desk.answer(graph, memory, "ana", "monday", "Is berth VC2 overloaded?", model)
    assert first["text"].startswith("VC2 is overloaded") and first["seq"] == 2
    assert first["tools"] == [f"look(kind=Berth, key={VC2})"]
    assert first["mentions"] == [("Berth", VC2)]
    kept = messages(memory, "ana", "monday")
    assert [(m["role"], m["by"]) for m in kept] == [("user", "ana"), ("assistant", "desk")]
    assert kept[1]["mentions"] == [("Berth", VC2)] and kept[1]["tools"] == first["tools"]
    # A new session: what was said about VC2 before is given to the model.
    later = Script("Still two port calls at VC2.")
    desk.answer(graph, memory, "ana", "tuesday", "What about VC2 overloaded now?", later)
    notes = [m["content"] for m in later.asked[0]["conversation"] if m["role"] == "system"]
    assert any("earlier sessions" in n and "Is berth VC2 overloaded?" in n for n in notes)
    # Another user has none of it.
    assert messages(memory, "bob", "monday") == []
    other = Script("I do not know.")
    desk.answer(graph, memory, "bob", "monday", "Is berth VC2 overloaded?", other)
    assert not any("earlier sessions" in m["content"] for m in other.asked[0]["conversation"])


def test_a_long_session_is_summed_up(graph, memory, monkeypatch):
    monkeypatch.setattr(desk, "TURNS", 2)

    def model(conversation, tools=None):
        if conversation[0]["content"].startswith("Sum up"):
            return {"content": "Ana asked about VC2 and FIHEL."}
        return {"content": f"answer to {conversation[-1]['content']}"}

    for n in range(3):
        desk.answer(graph, memory, "ana", "long", f"question {n}", model)
    held = context(memory, "ana", "long", 10)
    assert held["summary"] == "Ana asked about VC2 and FIHEL." and held["upto"] == 3
    assert [m["text"] for m in held["messages"]] == [
        "answer to question 1",
        "question 2",
        "answer to question 2",
    ]


def test_a_message_that_cannot_be_kept_is_refused(graph, memory):
    with pytest.raises(ValueError, match="text"):
        desk.answer(graph, memory, "ana", "s", "x" * 200_000, Script())


TOKEN = "t" * 32
OTHER = "o" * 32


@pytest.fixture
def client(graph, monkeypatch):
    from fastapi.testclient import TestClient

    from app import desk_api
    from app.api import get_graph
    from app.main import app

    tenant = f"test-{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("LIGHTHOUSE_DESK_USERS", f"{TOKEN}={tenant}/ana, {OTHER}={tenant}/bob")
    app.dependency_overrides[get_graph] = lambda: graph
    yield TestClient(app)
    app.dependency_overrides.clear()
    desk_api._memory(tenant).delete()
    desk_api._memory.cache_clear()


def signed(token=TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_the_inbox_shows_what_waits_and_what_was_concluded(client, graph, handed):
    first = client.get("/api/desk").json()
    assert first["waiting_count"] == 1 and first["waiting"][0]["id"] == handed
    assert first["assessed"] == []
    desk.work(graph, Script("Two port calls overlap at VC2."))
    after = client.get("/api/desk").json()
    assert after["waiting_count"] == 0
    (assessed,) = after["assessed"]
    assert (assessed["episode"], assessed["text"]) == (handed, "Two port calls overlap at VC2.")


def test_a_signed_in_user_asks_and_reads_their_sessions(client, graph, monkeypatch):
    monkeypatch.setattr(desk, "chat", Script("Nothing waits at VC2."))
    question = {"session": "s1", "text": "What waits at VC2?"}
    assert client.post("/api/desk/ask", json=question).status_code == 401
    assert client.post("/api/desk/ask", json=question, headers=signed("x" * 32)).status_code == 401
    answer = client.post("/api/desk/ask", json=question, headers=signed()).json()
    assert answer["text"] == "Nothing waits at VC2." and answer["seq"] == 2
    (session,) = client.get("/api/desk/sessions", headers=signed()).json()
    assert session["id"] == "s1"
    kept = client.get("/api/desk/sessions/s1", headers=signed()).json()
    assert [m["role"] for m in kept] == ["user", "assistant"]
    # Bob, in the same tenant, has no such session; nor has anyone without a token.
    assert client.get("/api/desk/sessions/s1", headers=signed(OTHER)).status_code == 404
    assert client.get("/api/desk/sessions", headers=signed(OTHER)).json() == []
    assert client.get("/api/desk/sessions").status_code == 401


def test_a_model_that_cannot_be_reached_is_a_502(client, monkeypatch):
    monkeypatch.setattr(desk, "chat", Script(RuntimeError("the model service cannot be reached")))
    found = client.post("/api/desk/ask", json={"session": "s", "text": "hi"}, headers=signed())
    assert (
        found.status_code == 502
        and found.json()["detail"]
        == "The assistant is temporarily unavailable. Please try again shortly."
    )


@pytest.mark.parametrize(
    "question",
    [{"session": "a/b", "text": "hi"}, {"session": "s", "text": ""}, {"text": "hi"}],
)
def test_a_question_of_a_wrong_form_is_a_422(client, question):
    assert client.post("/api/desk/ask", json=question, headers=signed()).status_code == 422


@pytest.mark.parametrize("users", ["short=t/u", f"{TOKEN}=Tenant/u", f"{TOKEN}"])
def test_a_wrong_list_of_users_lets_no_one_in(client, monkeypatch, users):
    from app.desk_api import _users

    with pytest.raises(RuntimeError, match="LIGHTHOUSE_DESK_USERS"):
        _users(users)


def test_a_look_is_kept_for_the_screen(graph, handed, monkeypatch):
    from app.poller import last_poll

    monkeypatch.setenv("LIGHTHOUSE_MODEL", "some-model")
    summary = desk.look(graph, think=Script("Two port calls overlap at VC2."))
    assert summary["did"] == {"assessed": 1} and summary["waiting"] == 0
    assert summary["model"] == "some-model" and summary["failed"] is None
    assert last_poll(graph, "desk") == summary
    failed = desk.look(graph, think=Script())
    assert failed["did"] == {} and last_poll(graph, "desk")["at"] >= summary["at"]


def test_without_a_model_key_the_desk_waits_and_says_why(graph, handed, monkeypatch):
    monkeypatch.delenv("LIGHTHOUSE_MODEL_URL", raising=False)
    monkeypatch.delenv("LIGHTHOUSE_MODEL_KEY", raising=False)
    monkeypatch.setattr(desk, "chat", Script())  # asked, it would fail: it has no reply
    summary = desk.look(graph)
    assert (summary["did"], summary["failed"]) == ({}, "needs a model key")
    assert summary["waiting"] == 1 and claim(graph, "desk", "berth-overload")["id"] == handed


def test_closed_backlog_does_not_consume_the_live_assessment_budget(graph, handed):
    open_episode(graph, "obsolete", "watcher", at=when(1))
    close_episode(graph, "obsolete", "watcher", at=when(2))
    add_task(graph, "0-closed", "berth-overload", ref="obsolete")
    # Make the stale task older independently of the machine clock's resolution.
    graph.query(
        "MATCH (t:Task {id: '0-closed'}) SET t.created_at = localdatetime('2020-01-01T00:00:00')"
    )
    model = Script("Two port calls overlap at VC2.")
    done = desk.work(graph, model, limit=1)
    assert [item["did"] for item in done] == ["ended before the desk looked", "assessed"]
    assert len(model.asked) == 1


def test_a_key_that_no_tool_showed_is_taken_back(graph, handed):
    model = Script(
        [call("look", kind="Berth", key=VC2)],
        "Move port call 3401234 to FIHEL/VUOS/VA8.",
        "Port calls 1 and 2 overlap at VC2. The graph holds no other berth for them.",
    )
    (done,) = desk.work(graph, model)
    assert done["outcome"] == "grounded" and len(model.asked) == 3
    correction = model.asked[2]["conversation"][-1]["content"]
    assert "3401234" in correction and "FIHEL/VUOS/VA8" in correction
    entry = episode(graph, handed)["entries"][-1]
    assert entry["text"].startswith("Port calls 1 and 2") and "unsupported" not in entry
    assert entry["tool_rows"] == [1] and len(entry["tool_ms"]) == 1


def test_a_key_that_stays_unshown_is_kept_as_unsupported(graph, handed):
    model = Script("Move it to FIHEL/VUOS/VA8.", "Move it to FIHEL/VUOS/VA8 anyway.")
    (done,) = desk.work(graph, model)
    assert done["outcome"] == "unsupported"
    entry = episode(graph, handed)["entries"][-1]
    assert entry["unsupported"] == ["FIHEL/VUOS/VA8"] and entry["tools"] == ["none"]


def test_what_the_graph_does_not_hold_is_said_so(graph, memory):
    model = Script([call("look", kind="Port", key="XXNONE")], "XXNONE is not in the graph.")
    found = desk.answer(graph, memory, "ana", "s", "How busy is XXNONE?", model)
    assert (found["outcome"], found["unsupported"]) == ("not in the graph", [])
    (kept,) = messages(memory, "ana", "s")[1:]
    assert kept["outcome"] == "not in the graph" and kept["tool_rows"] == [0]


def test_only_keys_and_ports_count_as_claims(graph, handed):
    seen = "the episode and what the tools returned: FIHEL/VUOS/VC2, 1, 2"
    assert desk.unsupported(graph, "ALERT: VC2 at FIHEL/VUOS/VC2 is full", seen) == []
    # DETRV is a port of the graph that nothing showed (FIHEL is in a berth key that was
    # shown); 1234567 is a number that nothing showed.
    found = desk.unsupported(graph, "ALERT at FIHEL and DETRV, see 1234567", seen)
    assert found == ["1234567", "DETRV"]


@pytest.mark.parametrize(
    ("reason", "says"),
    [
        (None, None),
        (
            "the model service answered 401: {secret answer}",
            "the model service did not accept the key",
        ),
        (
            "the model service at http://x cannot be reached: refused",
            "the model service cannot be reached",
        ),
        ("the model service answered 500: trace", "the model service refused the request"),
        ("the assessment was refused: too large", "the desk could not finish"),
    ],
)
def test_a_failure_is_told_as_a_category_and_never_as_its_text(reason, says):
    assert desk.problem(reason) == says


def test_a_failed_look_keeps_no_text_of_the_error(graph, handed):
    failed = desk.look(graph, think=Script(RuntimeError("the model service answered 401: {k}")))
    assert failed["failed"] == "the model service did not accept the key"
    assert "{k}" not in json.dumps(failed)


def test_model_choices_require_sign_in_and_never_expose_keys(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "private-openai-key")
    monkeypatch.setenv("LIGHTHOUSE_OPENAI_MODELS", "gpt-6-astra")
    assert client.get("/api/desk/models").status_code == 401
    response = client.get("/api/desk/models", headers=signed())
    assert response.status_code == 200
    assert {
        "id": "openai:gpt-6-astra",
        "provider": "OpenAI",
        "model": "gpt-6-astra",
    } in response.json()
    assert "private-openai-key" not in response.text and "https://" not in response.text


def test_selected_model_is_used_and_recorded_with_the_answer(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "private-openai-key")
    calls = []

    def think(conversation, tools=None, *, selection=None):
        calls.append(selection)
        return {"role": "assistant", "content": "Nothing was found in memory."}

    monkeypatch.setattr(desk, "chat", think)
    response = client.post(
        "/api/desk/ask",
        headers=signed(),
        json={"session": "choice", "text": "Check memory", "model": "openai:gpt-6-astra"},
    )
    assert response.status_code == 200 and calls == ["openai:gpt-6-astra"]
    held = client.get("/api/desk/sessions/choice", headers=signed()).json()
    assert held[-1]["model"] == "gpt-6-astra"
    assert "private-openai-key" not in json.dumps(held)
    assert client.get("/api/desk/sessions/choice", headers=signed(OTHER)).status_code == 404


def test_unknown_model_is_rejected_without_writing_a_message(client):
    response = client.post(
        "/api/desk/ask",
        headers=signed(),
        json={
            "session": "unknown-choice",
            "text": "Check memory",
            "model": "https://untrusted.example/model",
        },
    )
    assert response.status_code == 400
    assert "untrusted.example" not in response.text
    assert client.get("/api/desk/sessions/unknown-choice", headers=signed()).status_code == 404
