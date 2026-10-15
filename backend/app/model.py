"""API-key model providers for the application. Lighthouse Memory has no model dependency.

Named providers use their own keys. Existing LIGHTHOUSE_MODEL_URL/KEY settings remain
supported. Request selections resolve only through the server's configured model list.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

URL = "https://ollama.com/v1"
MODEL = "deepseek-v4.1-flash"
TIMEOUT = 120
MOST = 5_000_000

# IDs and protocols checked against official provider docs, October 2026. Operators can
# replace a provider's choices with LIGHTHOUSE_<PROVIDER>_MODELS (comma-separated IDs).
PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "protocol": "responses",
        "models": ("gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna", "gpt-5.4-mini"),
    },
    "anthropic": {
        "name": "Anthropic",
        "url": "https://api.anthropic.com/v1",
        "key_env": "ANTHROPIC_API_KEY",
        "protocol": "messages",
        "models": ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"),
    },
    "gemini": {
        "name": "Google Gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "protocol": "chat",
        "models": ("gemini-3.8-flash", "gemini-3.1-flash-lite"),
    },
    "groq": {
        "name": "Groq",
        "url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "protocol": "chat",
        "models": ("llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant"),
    },
    "deepseek": {
        "name": "DeepSeek",
        "url": "https://api.deepseek.com",
        "key_env": "DEEPSEEK_API_KEY",
        "protocol": "chat",
        "models": ("deepseek-flash", "deepseek-v4-pro"),
    },
    "mistral": {
        "name": "Mistral",
        "url": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY",
        "protocol": "chat",
        "models": ("mistral-small-latest", "mistral-large-latest"),
    },
    "openrouter": {
        "name": "OpenRouter",
        "url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "protocol": "chat",
        "models": ("openai/gpt-5.4-mini",),
    },
    "commandcode": {
        "name": "Command Code",
        "url": "https://api.commandcode.ai/provider/v1",
        "key_env": "COMMANDCODE_API_KEY",
        "protocol": "chat",
        "models": ("deepseek/deepseek-v4-flash", "claude-sonnet-4-6"),
    },
    "ollama": {
        "name": "Ollama Cloud",
        "url": URL,
        "key_env": "OLLAMA_API_KEY",
        "protocol": "chat",
        "models": ("gemma4:31b", "deepseek-v4.1-flash"),
    },
}


def _models(provider: str) -> tuple[str, ...]:
    override = os.environ.get(f"LIGHTHOUSE_{provider.upper()}_MODELS")
    return (
        tuple(dict.fromkeys(part.strip() for part in override.split(",") if part.strip()))
        if override is not None
        else PROVIDERS[provider]["models"]
    )


def _profile(provider: str, name: str) -> dict:
    spec = PROVIDERS[provider]
    key = os.environ.get(spec["key_env"], "").strip()
    if (
        provider == "ollama"
        and os.environ.get("LIGHTHOUSE_MODEL_URL", URL).rstrip("/") == URL
        and os.environ.get("LIGHTHOUSE_MODEL_PROVIDER", "") in {"", "ollama"}
    ):
        key = key or os.environ.get("LIGHTHOUSE_MODEL_KEY", "").strip()
    protocol = spec["protocol"]
    if provider == "commandcode" and name.startswith("claude-"):
        protocol = "messages"
    return {
        "provider": provider,
        "url": spec["url"],
        "model": name,
        "key": key,
        "protocol": protocol,
        "reasoning": "",
    }


def settings(selection: str | None = None) -> dict:
    """Resolve a server-configured model; never accept endpoint or credential overrides."""
    if selection and selection != "default":
        provider, separator, name = selection.partition(":")
        if not separator or provider not in PROVIDERS or name not in _models(provider):
            raise ValueError("Model selection is not enabled.")
        use = _profile(provider, name)
        if not use["key"]:
            raise ValueError("Model selection is not enabled.")
        return use
    provider = os.environ.get("LIGHTHOUSE_MODEL_PROVIDER", "").strip().lower()
    if provider:
        if provider not in PROVIDERS:
            raise ValueError("Unknown LIGHTHOUSE_MODEL_PROVIDER.")
        use = _profile(
            provider,
            os.environ.get("LIGHTHOUSE_MODEL", "").strip() or PROVIDERS[provider]["models"][0],
        )
    else:
        use = {
            "provider": "custom",
            "url": os.environ.get("LIGHTHOUSE_MODEL_URL", URL).rstrip("/"),
            "model": os.environ.get("LIGHTHOUSE_MODEL", "").strip() or MODEL,
            "key": os.environ.get("LIGHTHOUSE_MODEL_KEY", "").strip(),
            "protocol": os.environ.get("LIGHTHOUSE_MODEL_PROTOCOL", "chat"),
        }
    use["reasoning"] = os.environ.get("LIGHTHOUSE_MODEL_REASONING", "")
    if use["protocol"] not in {"chat", "responses", "messages"}:
        raise ValueError("Unknown LIGHTHOUSE_MODEL_PROTOCOL.")
    return use


def _ready(use: dict) -> bool:
    # Legacy local endpoints remain compatible. Every named hosted provider needs its key.
    return bool(
        use["key"] or (use["provider"] == "custom" and not use["url"].startswith("https://"))
    )


def catalog() -> list[dict]:
    """Customer-safe choices. Never return URLs, key names, credentials, or diagnostics."""
    choices = []
    try:
        default = settings()
    except ValueError:
        default = None
    if default and _ready(default):
        choices.append(
            {"id": "default", "provider": "Workspace default", "model": default["model"]}
        )
    for provider, spec in PROVIDERS.items():
        for name in _models(provider):
            use = _profile(provider, name)
            if use["key"] and not (
                default
                and _ready(default)
                and all(use[k] == default[k] for k in ("url", "model", "protocol"))
            ):
                choices.append(
                    {"id": f"{provider}:{name}", "provider": spec["name"], "model": name}
                )
    return choices


def readiness() -> dict:
    """Private operator status; availability is configuration-only, not an account probe."""
    try:
        use = settings()
    except ValueError as exc:
        return {"model": "", "service": "", "ready": False, "problem": str(exc)}
    service = urllib.parse.urlsplit(use["url"]).hostname or use["url"]
    problem = None if _ready(use) else f"no key for {service}: configure the provider API key"
    if use["provider"] == "custom" and problem:
        problem = f"no key for {service}: set LIGHTHOUSE_MODEL_KEY"
    return {"model": use["model"], "service": service, "ready": problem is None, "problem": problem}


def _messages_body(messages: list[dict], tools: list[dict] | None, use: dict) -> dict:
    system, turns = [], []
    for message in messages:
        role = message["role"]
        if role in {"system", "developer"}:
            system.append(message.get("content") or "")
            continue
        if role == "tool":
            role, content = (
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": message["tool_call_id"],
                        "content": message.get("content") or "",
                    }
                ],
            )
        elif message.get("_provider_content") is not None:
            content = message["_provider_content"]
        else:
            content = (
                [{"type": "text", "text": message["content"]}] if message.get("content") else []
            )
            for call in message.get("tool_calls") or []:
                content.append(
                    {
                        "type": "tool_use",
                        "id": call["id"],
                        "name": call["function"]["name"],
                        "input": json.loads(call["function"]["arguments"]),
                    }
                )
        if not content:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(content)
        else:
            turns.append({"role": role, "content": content})
    body = {
        "model": use["model"],
        "system": "\n\n".join(system),
        "messages": turns,
        "max_tokens": 8192,
    }
    if tools:
        body["tools"] = [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"]["parameters"],
            }
            for t in tools
        ]
    return body


def _responses_body(messages: list[dict], tools: list[dict] | None, use: dict) -> dict:
    items = []
    for message in messages:
        if message.get("_response_items") is not None:
            items.extend(message["_response_items"])
        elif message["role"] == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message["tool_call_id"],
                    "output": message.get("content") or "",
                }
            )
        else:
            if message.get("content"):
                items.append({"role": message["role"], "content": message["content"]})
            for call in message.get("tool_calls") or []:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call["id"],
                        "name": call["function"]["name"],
                        "arguments": call["function"]["arguments"],
                    }
                )
    body = {"model": use["model"], "input": items, "store": False, "max_output_tokens": 8192}
    if tools:
        body["tools"] = [
            {"type": "function", **tool["function"], "strict": False} for tool in tools
        ]
    if use["reasoning"]:
        body["reasoning"] = {"effort": use["reasoning"]}
    return body


def _reply(answer: dict, protocol: str) -> dict:
    if protocol == "chat":
        return answer["choices"][0]["message"]
    content = answer["content"] if protocol == "messages" else answer["output"]
    text, calls = [], []
    for part in content:
        if protocol == "messages" and part["type"] == "text":
            text.append(part["text"])
        elif part["type"] == "message":
            text.extend(
                block["text"] for block in part["content"] if block["type"] == "output_text"
            )
        elif part["type"] in {"tool_use", "function_call"}:
            calls.append(
                {
                    "id": part["id"] if protocol == "messages" else part["call_id"],
                    "type": "function",
                    "function": {
                        "name": part["name"],
                        "arguments": json.dumps(part["input"])
                        if protocol == "messages"
                        else part["arguments"],
                    },
                }
            )
    if not text and not calls:
        raise ValueError("No final text or function call.")
    private = "_provider_content" if protocol == "messages" else "_response_items"
    return {"role": "assistant", "content": "\n".join(text), "tool_calls": calls, private: content}


def chat(
    messages: list[dict], tools: list[dict] | None = None, *, selection: str | None = None
) -> dict:
    """One model turn, normalized for the Desk's bounded tool loop."""
    use = settings(selection)
    if not _ready(use):
        raise RuntimeError("no key for the selected model provider")
    protocol = use["protocol"]
    headers = {"Content-Type": "application/json"}
    if use["key"]:
        headers["Authorization"] = f"Bearer {use['key']}"
    if protocol == "messages":
        body = _messages_body(messages, tools, use)
        path = "/messages"
        headers["anthropic-version"] = "2023-06-01"
        if use["provider"] != "commandcode":
            headers.pop("Authorization", None)
            headers["x-api-key"] = use["key"]
    elif protocol == "responses":
        body, path = _responses_body(messages, tools, use), "/responses"
    else:
        # Protocol metadata is retained inside the loop, never sent to unrelated APIs.
        body = {
            "model": use["model"],
            "messages": [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages],
            "stream": False,
        }
        path = "/chat/completions"
        if tools:
            body["tools"] = tools
        if use["reasoning"]:
            body["reasoning_effort"] = use["reasoning"]
        if use["provider"] == "deepseek":
            body["thinking"] = {"type": "disabled"}
    request = urllib.request.Request(f"{use['url']}{path}", json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            answer = json.loads(response.read(MOST))
    except urllib.error.HTTPError as exc:
        detail = exc.read(2_000).decode(errors="replace")
        raise RuntimeError(f"the model service answered {exc.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"the model service at {use['url']} cannot be reached: {exc}") from None
    except (ValueError, UnicodeError):
        raise RuntimeError("the model service gave an invalid JSON response") from None
    try:
        reply = _reply(answer, protocol)
        if not isinstance(reply, dict):
            raise TypeError
        return reply
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError("the model service gave no message") from None
