"""
Streaming answers (Server-Sent Events), LLM fallbacks, hardware detection and model choice
"""

import io
import json
from typing import Any

import pytest

from app.hardware import GPUInfo, HardwareInfo, choose_ollama_model, recommendations

GB = 1024**3


def _events(response) -> list[tuple[str, Any]]:
    """Parse an SSE body into (event, data) pairs."""
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def _upload(client, name: str, text: str) -> None:
    client.post("/ingest", files={"files": (name, io.BytesIO(text.encode()), "text/plain")})


def _fake_llm(monkeypatch, tokens: list[str], fail_after: int | None = None):
    """Make the LLM 'available' and stream the given tokens (optionally failing midway)."""
    from app.services.llm import LLMService

    async def stream(self, messages):
        for i, token in enumerate(tokens):
            if fail_after is not None and i == fail_after:
                raise RuntimeError("connection reset")
            yield token

    async def complete(self, messages):
        return "".join(tokens), 42

    monkeypatch.setattr(LLMService, "is_available", lambda self: True)
    monkeypatch.setattr(LLMService, "resolved_model", property(lambda self: "fake-model"))
    monkeypatch.setattr(LLMService, "stream", stream)
    monkeypatch.setattr(LLMService, "complete", complete)


# ---------------------------------------------------------------------------
# /ask/stream
# ---------------------------------------------------------------------------


def test_ask_stream_extractive(make_client):
    c = make_client()
    _upload(c, "backup.txt", "The NAS backup runs every night at 2am.")
    r = c.post("/ask/stream", json={"question": "when does the backup run?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _events(r)
    kinds = [e for e, _ in events]
    assert kinds[0] == "citations" and kinds[-1] == "done"
    assert events[0][1][0]["filename"] == "backup.txt"
    text = "".join(d["text"] for e, d in events if e == "token")
    assert "2am" in text
    assert events[-1][1]["method"] == "extractive" and events[-1][1]["retrieval"] == "bm25"


def test_ask_stream_with_no_documents(make_client):
    c = make_client()
    events = _events(c.post("/ask/stream", json={"question": "anything?"}))
    assert events[0] == ("citations", [])
    assert events[-1][1]["method"] == "none"


def test_ask_stream_llm_tokens_and_sources(make_client, monkeypatch):
    c = make_client(NAI_LLM_ENABLED="true")
    _upload(c, "backup.txt", "The NAS backup runs every night at 2am.")
    _fake_llm(monkeypatch, ["The backup ", "runs at ", "2am."])
    events = _events(c.post("/ask/stream", json={"question": "when does the backup run?"}))
    tokens = [d["text"] for e, d in events if e == "token"]
    assert tokens[:3] == ["The backup ", "runs at ", "2am."]
    assert "**Sources:**" in tokens[-1] and "backup.txt" in tokens[-1]
    assert events[-1][1]["method"] == "llm" and events[-1][1]["model"] == "ollama/fake-model"


def test_llm_failure_before_first_token_falls_back_to_extractive(make_client, monkeypatch):
    c = make_client(NAI_LLM_ENABLED="true")
    _upload(c, "backup.txt", "The NAS backup runs every night at 2am.")
    _fake_llm(monkeypatch, ["never sent"], fail_after=0)
    events = _events(c.post("/ask/stream", json={"question": "backup"}))
    assert events[-1][1]["method"] == "extractive"
    assert not any(e == "error" for e, _ in events)


def test_llm_failure_mid_stream_reports_error(make_client, monkeypatch):
    c = make_client(NAI_LLM_ENABLED="true")
    _upload(c, "backup.txt", "The NAS backup runs every night at 2am.")
    _fake_llm(monkeypatch, ["The backup ", "runs"], fail_after=1)
    events = _events(c.post("/ask/stream", json={"question": "backup"}))
    kinds = [e for e, _ in events]
    assert "error" in kinds and kinds[-1] == "done"
    assert events[-1][1]["method"] == "llm"


# ---------------------------------------------------------------------------
# /chat/stream
# ---------------------------------------------------------------------------


def test_chat_stream_persists_reply_and_continues(make_client, monkeypatch):
    c = make_client(NAI_LLM_ENABLED="true")
    _upload(c, "router.txt", "The router admin password is printed on its label.")
    _fake_llm(monkeypatch, ["Check ", "the label."])

    first = _events(
        c.post("/chat/stream", json={"messages": [{"role": "user", "content": "router password?"}]})
    )
    assert first[0][0] == "conversation"
    conv_id = first[0][1]["conversation_id"]
    assert first[1][0] == "citations" and first[1][1][0]["filename"] == "router.txt"
    assert first[-1][1]["conversation_id"] == conv_id

    second = _events(
        c.post(
            "/chat/stream",
            json={"conversation_id": conv_id, "messages": [{"role": "user", "content": "and the wifi?"}]},
        )
    )
    assert second[0][1]["conversation_id"] == conv_id

    history = c.get(f"/chat/{conv_id}").json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert history[1]["content"] == "Check the label."


def test_chat_stream_rejects_unknown_conversation(make_client):
    c = make_client()
    r = c.post(
        "/chat/stream", json={"conversation_id": "nope", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert r.status_code == 404


def test_stream_endpoints_require_auth(make_client):
    c = make_client(NAI_AUTH_ENABLED="true")
    assert c.post("/ask/stream", json={"question": "x"}).status_code == 401
    assert c.post("/chat/stream", json={"messages": [{"role": "user", "content": "x"}]}).status_code == 401


# ---------------------------------------------------------------------------
# Hardware and model choice
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hw", "tier"),
    [
        (HardwareInfo(cpu_count=4, memory_gb=8), "low"),
        (HardwareInfo(cpu_count=8, memory_gb=32), "standard"),
        (HardwareInfo(cpu_count=4, memory_gb=16, gpus=[GPUInfo("nvidia", "RTX 3060", 12.0)]), "gpu"),
        (HardwareInfo(cpu_count=4, memory_gb=16, gpus=[GPUInfo("intel", "card0")]), "low"),
    ],
)
def test_hardware_tier(hw, tier):
    assert hw.tier == tier


MODELS = [
    {"name": "llama3.2:3b", "size": 2 * GB},
    {"name": "gemma3:12b", "size": 8 * GB},
    {"name": "qwen3:32b", "size": 20 * GB},
    {"name": "nomic-embed-text", "size": 1 * GB},
]


def test_choose_model_uses_largest_that_fits_vram():
    gpu12 = HardwareInfo(cpu_count=8, memory_gb=32, gpus=[GPUInfo("nvidia", "RTX 3060", 12.0)])
    gpu24 = HardwareInfo(cpu_count=8, memory_gb=32, gpus=[GPUInfo("nvidia", "RTX 4090", 24.0)])
    assert choose_ollama_model(MODELS, gpu12) == "gemma3:12b"
    assert choose_ollama_model(MODELS, gpu24) == "qwen3:32b"


def test_choose_model_on_cpu_and_edge_cases():
    nas = HardwareInfo(cpu_count=4, memory_gb=8)
    assert choose_ollama_model(MODELS, nas) == "llama3.2:3b"
    tiny = HardwareInfo(cpu_count=2, memory_gb=2)
    assert choose_ollama_model(MODELS, tiny) == "llama3.2:3b"  # nothing fits: smallest chat model
    assert choose_ollama_model([{"name": "nomic-embed-text", "size": GB}], nas) is None
    assert choose_ollama_model([], nas) is None


def test_recommendations_mention_remote_ollama_on_weak_hardware():
    tips = " ".join(recommendations(HardwareInfo(cpu_count=4, memory_gb=8)))
    assert "NAI_LLM_BASE_URL" in tips and "NAI_RERANKER=false" in tips


def test_auto_model_resolves_from_ollama(make_client, monkeypatch):
    from app.services import get_llm_service

    make_client(NAI_LLM_ENABLED="true", NAI_LLM_MODEL="auto")
    monkeypatch.setattr("app.services.llm.ollama_models", lambda base: MODELS)
    monkeypatch.setattr(
        "app.services.llm.detect_hardware",
        lambda: HardwareInfo(cpu_count=8, memory_gb=32, gpus=[GPUInfo("nvidia", "RTX 3060", 12.0)]),
    )
    llm = get_llm_service()
    assert llm.resolved_model == "gemma3:12b"
    assert llm.model_name == "ollama/gemma3:12b"

    monkeypatch.setattr("app.services.llm.ollama_models", lambda base: [])
    assert llm.is_available() is False


def test_system_endpoint_reports_hardware_and_features(make_client):
    c = make_client()
    body = c.get("/system").json()
    assert body["hardware"]["tier"] in {"low", "standard", "gpu"}
    assert body["hardware"]["cpu_count"] >= 1
    assert body["features"]["ocr"] is False
    assert body["features"]["llm"]["enabled"] is False
    assert body["recommendations"]


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    [
        ("ollama", "llama3.2", "ollama/llama3.2"),
        ("ollama", "ollama/llama3.2", "ollama/llama3.2"),
        ("ollama", "hf.co/bartowski/Qwen3-8B-GGUF", "ollama/hf.co/bartowski/Qwen3-8B-GGUF"),
        # OpenAI-compatible servers: LiteLLM needs the prefix for model names it doesn't know
        ("openai", "my-local-model", "openai/my-local-model"),
        ("openai", "Qwen/Qwen3-8B", "openai/Qwen/Qwen3-8B"),
        ("anthropic", "claude-sonnet-5-5", "anthropic/claude-sonnet-5-5"),
    ],
)
def test_litellm_model_string(make_client, provider, model, expected):
    from app.services import get_llm_service

    make_client(NAI_LLM_ENABLED="true", NAI_LLM_PROVIDER=provider, NAI_LLM_MODEL=model)
    assert get_llm_service().model_name == expected


def test_system_reports_the_space_on_the_data_disk(make_client):
    """The web UI shows disk use in "This machine" as a block meter: total and used bytes of nAI's data disk."""
    storage = make_client().get("/system").json()["storage"]
    assert storage["total_bytes"] > 0 and 0 <= storage["used_bytes"] <= storage["total_bytes"]
    assert set(storage) == {"total_bytes", "used_bytes"}  # no path: /system must not reveal where data lives
