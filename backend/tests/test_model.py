"""The model service, as a local stand-in that speaks the chat completions API."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import model


@pytest.fixture
def service(monkeypatch):
    asked = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            asked.append({"path": self.path, "body": body, "key": self.headers["Authorization"]})
            status, answer = 200, {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
            if body["model"] == "refused":
                status, answer = 401, {"error": {"message": "Unauthorized"}}
            elif body["model"] == "empty":
                answer = {"choices": []}
            data = json.dumps(answer).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LIGHTHOUSE_MODEL_URL", f"http://127.0.0.1:{server.server_port}/v1/")
    for name in ("LIGHTHOUSE_MODEL", "LIGHTHOUSE_MODEL_KEY", "LIGHTHOUSE_MODEL_REASONING"):
        monkeypatch.delenv(name, raising=False)
    yield asked
    server.shutdown()


def test_a_turn_is_asked_with_the_tools_the_key_and_the_reasoning(service, monkeypatch):
    monkeypatch.setenv("LIGHTHOUSE_MODEL_KEY", "secret")
    monkeypatch.setenv("LIGHTHOUSE_MODEL_REASONING", "low")
    tools = [{"type": "function", "function": {"name": "look", "parameters": {}}}]
    assert model.chat([{"role": "user", "content": "hi"}], tools)["content"] == "ok"
    (asked,) = service
    assert asked["path"] == "/v1/chat/completions" and asked["key"] == "Bearer secret"
    assert asked["body"]["model"] == model.MODEL and asked["body"]["tools"] == tools
    assert asked["body"]["reasoning_effort"] == "low" and asked["body"]["stream"] is False


def test_without_tools_a_key_or_reasoning_none_is_sent(service):
    model.chat([{"role": "user", "content": "hi"}])
    (asked,) = service
    assert asked["key"] is None
    assert "tools" not in asked["body"] and "reasoning_effort" not in asked["body"]


def test_provider_path_and_namespaced_models_are_preserved(service, monkeypatch):
    # Command Code's provider prefix and slash-separated IDs need no separate client.
    base = model.settings()["url"].removesuffix("/v1")
    monkeypatch.setenv("LIGHTHOUSE_MODEL_URL", base + "/provider/v1")
    monkeypatch.setenv("LIGHTHOUSE_MODEL", "deepseek/deepseek-v4-flash")
    model.chat([{"role": "user", "content": "hi"}])
    assert service[0]["path"] == "/provider/v1/chat/completions"
    assert service[0]["body"]["model"] == "deepseek/deepseek-v4-flash"


@pytest.mark.parametrize(
    ("name", "error"), [("refused", "answered 401"), ("empty", "gave no message")]
)
def test_a_refusal_or_an_empty_answer_is_an_error(service, monkeypatch, name, error):
    monkeypatch.setenv("LIGHTHOUSE_MODEL", name)
    with pytest.raises(RuntimeError, match=error):
        model.chat([{"role": "user", "content": "hi"}])


def test_a_service_that_is_not_there_is_an_error(monkeypatch):
    monkeypatch.setenv("LIGHTHOUSE_MODEL_URL", "http://127.0.0.1:9/v1")
    with pytest.raises(RuntimeError, match="cannot be reached"):
        model.chat([{"role": "user", "content": "hi"}])


def test_a_hosted_service_without_a_key_is_not_ready(monkeypatch):
    monkeypatch.delenv("LIGHTHOUSE_MODEL_URL", raising=False)
    monkeypatch.delenv("LIGHTHOUSE_MODEL_KEY", raising=False)
    found = model.readiness()
    assert (found["service"], found["ready"]) == ("ollama.com", False)
    assert "LIGHTHOUSE_MODEL_KEY" in found["problem"]
    monkeypatch.setenv("LIGHTHOUSE_MODEL_KEY", "k")
    assert model.readiness()["ready"] is True
    monkeypatch.setenv("LIGHTHOUSE_MODEL_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.delenv("LIGHTHOUSE_MODEL_KEY")
    assert model.readiness() == {
        "model": model.MODEL,
        "service": "127.0.0.1",
        "ready": True,
        "problem": None,
    }


@pytest.fixture
def transport(monkeypatch):
    """Capture real request serialization without calling any paid provider."""
    from io import BytesIO

    for provider, spec in model.PROVIDERS.items():
        monkeypatch.delenv(spec["key_env"], raising=False)
        monkeypatch.delenv(f"LIGHTHOUSE_{provider.upper()}_MODELS", raising=False)
    for name in (
        "LIGHTHOUSE_MODEL_PROVIDER",
        "LIGHTHOUSE_MODEL_URL",
        "LIGHTHOUSE_MODEL",
        "LIGHTHOUSE_MODEL_KEY",
        "LIGHTHOUSE_MODEL_PROTOCOL",
        "LIGHTHOUSE_MODEL_REASONING",
    ):
        monkeypatch.delenv(name, raising=False)
    asked, replies = [], []

    def send(request, timeout):
        asked.append(
            {
                "url": request.full_url,
                "headers": dict(request.header_items()),
                "body": json.loads(request.data),
            }
        )
        assert timeout == model.TIMEOUT
        return BytesIO(json.dumps(replies.pop(0)).encode())

    monkeypatch.setattr(model.urllib.request, "urlopen", send)
    return asked, replies


@pytest.mark.parametrize("provider", model.PROVIDERS)
def test_each_provider_uses_its_own_api_key_and_protocol(transport, monkeypatch, provider):
    asked, replies = transport
    spec = model.PROVIDERS[provider]
    name = spec["models"][0]
    monkeypatch.setenv(spec["key_env"], "provider-secret")
    monkeypatch.setenv("LIGHTHOUSE_MODEL_KEY", "wrong-shared-secret")
    if spec["protocol"] == "messages":
        replies.append({"content": [{"type": "text", "text": "ok"}]})
        path, header = "/messages", "X-api-key"
    elif spec["protocol"] == "responses":
        replies.append(
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ]
            }
        )
        path, header = "/responses", "Authorization"
    else:
        replies.append({"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
        path, header = "/chat/completions", "Authorization"
    result = model.chat(
        [{"role": "system", "content": "Use evidence."}, {"role": "user", "content": "hi"}],
        selection=f"{provider}:{name}",
    )
    assert result["content"] == "ok"
    assert asked[0]["url"] == spec["url"] + path
    assert asked[0]["headers"][header] == (
        "provider-secret" if provider == "anthropic" else "Bearer provider-secret"
    )
    assert "wrong-shared-secret" not in json.dumps(asked)
    assert "temperature" not in asked[0]["body"]


def test_responses_tool_round_trip_keeps_reasoning_and_call_ids(transport, monkeypatch):
    asked, replies = transport
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    output = [
        {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "signed-context"},
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_1",
            "name": "look",
            "arguments": '{"key":"d1"}',
        },
    ]
    replies.extend(
        [
            {"output": output},
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Found d1."}],
                    }
                ]
            },
        ]
    )
    conversation = [{"role": "user", "content": "Check d1."}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "look",
                "parameters": {"type": "object", "properties": {"key": {"type": "string"}}},
            },
        }
    ]
    reply = model.chat(conversation, tools, selection="openai:gpt-6-astra")
    conversation.extend(
        [reply, {"role": "tool", "tool_call_id": "call_1", "content": '{"key":"d1"}'}]
    )
    assert model.chat(conversation, tools, selection="openai:gpt-6-astra")["content"] == "Found d1."
    assert asked[0]["body"]["store"] is False
    assert asked[0]["body"]["tools"][0]["strict"] is False
    assert asked[1]["body"]["input"][1:3] == output
    assert asked[1]["body"]["input"][-1] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"key":"d1"}',
    }


@pytest.mark.parametrize(
    "provider,name,key_env,header",
    [
        ("anthropic", "claude-sonnet-5-5", "ANTHROPIC_API_KEY", "X-api-key"),
        ("commandcode", "claude-sonnet-4-6", "COMMANDCODE_API_KEY", "Authorization"),
    ],
)
def test_messages_round_trip_keeps_signed_thinking_and_groups_parallel_results(
    transport, monkeypatch, provider, name, key_env, header
):
    asked, replies = transport
    monkeypatch.setenv(key_env, "key")
    content = [
        {"type": "thinking", "thinking": "inspect", "signature": "signed-context"},
        {"type": "tool_use", "id": "t1", "name": "look", "input": {"key": "d1"}},
        {"type": "tool_use", "id": "t2", "name": "look", "input": {"key": "d2"}},
    ]
    replies.extend([{"content": content}, {"content": [{"type": "text", "text": "Found both."}]}])
    conversation = [
        {"role": "system", "content": "Evidence only."},
        {"role": "user", "content": "Check both."},
    ]
    tools = [{"type": "function", "function": {"name": "look", "parameters": {"type": "object"}}}]
    reply = model.chat(conversation, tools, selection=f"{provider}:{name}")
    conversation.extend(
        [
            reply,
            {"role": "tool", "tool_call_id": "t1", "content": "d1"},
            {"role": "tool", "tool_call_id": "t2", "content": "d2"},
        ]
    )
    assert (
        model.chat(conversation, tools, selection=f"{provider}:{name}")["content"] == "Found both."
    )
    assert asked[0]["url"].endswith("/messages") and header in asked[0]["headers"]
    assert asked[0]["body"]["system"] == "Evidence only."
    assert asked[1]["body"]["messages"][1]["content"] == content
    assert [block["tool_use_id"] for block in asked[1]["body"]["messages"][-1]["content"]] == [
        "t1",
        "t2",
    ]
    assert "input_schema" in asked[0]["body"]["tools"][0]


def test_catalog_has_no_credentials_or_endpoints_and_honours_allowlists(transport, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai")
    monkeypatch.setenv("GROQ_API_KEY", "secret-groq")
    monkeypatch.setenv("LIGHTHOUSE_OPENAI_MODELS", "custom-deployment, custom-deployment")
    monkeypatch.setenv("LIGHTHOUSE_GROQ_MODELS", "")
    found = model.catalog()
    assert found == [
        {"id": "openai:custom-deployment", "provider": "OpenAI", "model": "custom-deployment"}
    ]
    assert all(set(choice) == {"id", "provider", "model"} for choice in found)
    assert "secret" not in json.dumps(found) and "https://" not in json.dumps(found)


@pytest.mark.parametrize(
    "selection", ["openai:gpt-6-astra", "unknown:model", "https://host/path", "groq:unlisted"]
)
def test_disabled_or_arbitrary_model_selection_never_sends_request(transport, selection):
    with pytest.raises(ValueError, match="not enabled"):
        model.chat([{"role": "user", "content": "hi"}], selection=selection)
    assert not transport[0]


def test_named_default_ignores_legacy_provider_key_and_endpoint(transport, monkeypatch):
    monkeypatch.setenv("LIGHTHOUSE_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("LIGHTHOUSE_MODEL_KEY", "ollama-key")
    monkeypatch.setenv("LIGHTHOUSE_MODEL_URL", "https://ollama.com/v1")
    assert not model.readiness()["ready"]
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    use = model.settings()
    assert use["url"] == "https://api.openai.com/v1" and use["key"] == "openai-key"


def test_provider_context_survives_the_real_desk_tool_loop(transport):
    from types import SimpleNamespace
    import anyio
    from app.desk import converse

    private = {
        "_provider_content": [{"type": "thinking", "signature": "signed"}],
        "_response_items": [{"type": "reasoning", "encrypted_content": "encrypted"}],
        "reasoning_content": "provider-state",
    }
    seen = []

    def think(conversation, tools):
        seen.append([dict(message) for message in conversation])
        if len(seen) == 1:
            return {
                "content": "",
                "tool_calls": [{"id": "t1", "function": {"name": "look", "arguments": "{}"}}],
                **private,
            }
        return {"content": "Done."}

    class Session:
        async def call_tool(self, name, arguments):
            return SimpleNamespace(isError=False, content=[SimpleNamespace(text='{"key":"d1"}')])

    async def run():
        return await converse(Session(), [{"role": "user", "content": "hi"}], think, tools=[])

    assert anyio.run(run)["text"] == "Done."
    assistant = seen[1][1]
    assert all(assistant[key] == value for key, value in private.items())


def test_legacy_custom_key_cannot_enable_an_unrelated_provider(transport, monkeypatch):
    monkeypatch.setenv("LIGHTHOUSE_MODEL_URL", "https://custom.example/v1")
    monkeypatch.setenv("LIGHTHOUSE_MODEL_KEY", "custom-provider-secret")
    assert not any(choice["id"].startswith("ollama:") for choice in model.catalog())
    with pytest.raises(ValueError, match="not enabled"):
        model.settings("ollama:gemma4:31b")
