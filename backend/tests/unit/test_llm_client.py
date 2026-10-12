import pytest
import requests

from app.llm.client import LLMError, OllamaClient
from app.pipeline.postprocessor import strip_self_references


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self.payload


@pytest.fixture
def calls(monkeypatch):
    """Record /api/chat calls; models listed in `failing` return HTTP 500."""
    recorded = {"payloads": [], "failing": set()}

    def fake_post(url, json, timeout):
        recorded["payloads"].append(json)
        if json["model"] in recorded["failing"]:
            return FakeResponse(status=500)
        return FakeResponse({"message": {"role": "assistant", "content": f"answer from {json['model']}"}})

    monkeypatch.setattr(requests, "post", fake_post)
    return recorded


def test_payload_uses_native_options(calls):
    client = OllamaClient("qwen3:8b", "qwen3:4b", temperature=0.2, num_ctx=8192, max_tokens=600)
    assert client.complete([{"role": "user", "content": "hi"}]) == "answer from qwen3:8b"
    payload = calls["payloads"][0]
    assert payload["think"] is False and payload["stream"] is False
    assert payload["options"] == {"temperature": 0.2, "num_ctx": 8192, "num_predict": 600}


def test_falls_back_to_the_smaller_model(calls):
    calls["failing"].add("qwen3:8b")
    client = OllamaClient("qwen3:8b", "qwen3:4b")
    assert client.complete([{"role": "user", "content": "hi"}]) == "answer from qwen3:4b"
    assert [p["model"] for p in calls["payloads"]] == ["qwen3:8b", "qwen3:4b"]


def test_raises_when_every_model_fails(calls):
    calls["failing"].update({"qwen3:8b", "qwen3:4b"})
    with pytest.raises(LLMError, match="qwen3:8b.*qwen3:4b"):
        OllamaClient("qwen3:8b", "qwen3:4b").complete([{"role": "user", "content": "hi"}])


def test_configured_checks_that_a_model_is_pulled(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout: FakeResponse({"models": [{"name": "qwen3:4b"}]}))
    assert OllamaClient("qwen3:8b", "qwen3:4b").configured
    assert not OllamaClient("llama3:70b").configured


def test_configured_is_false_when_ollama_is_down(monkeypatch):
    def down(url, timeout):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(requests, "get", down)
    assert not OllamaClient("qwen3:8b").configured


def test_think_blocks_are_removed():
    assert strip_self_references("<think>the user wants...</think>\nRest and hydrate.") == "Rest and hydrate."
    assert strip_self_references("Rest.<think>unterminated reasoning") == "Rest."


def test_warm_up_loads_the_main_model(calls):
    OllamaClient("qwen3:8b", "qwen3:4b", keep_alive="30m").warm_up()
    assert calls["payloads"][0]["model"] == "qwen3:8b"
    assert calls["payloads"][0]["messages"] == []
    assert calls["payloads"][0]["keep_alive"] == "30m"
