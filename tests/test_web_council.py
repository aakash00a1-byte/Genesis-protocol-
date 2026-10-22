"""Webhook routing for the multi-LLM council (/council).

The Space webhook runs a deliberation and queues the reconciled answer. These
tests drive the real Flask route, with the reply queue redirected to a temp dir
and the council fed in-process providers, so the routing and the answer
formatting are exercised for real.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from genesis_protocol.ai.council import LLMCouncil  # noqa: E402
from genesis_protocol.ai.providers.base_provider import AIResponse  # noqa: E402


class FakeProvider:
    def __init__(self, name, answer):
        self.name = name
        self.answer = answer

    def is_configured(self):
        return True

    def should_use(self):
        return True

    def get_default_model(self):
        return f"{self.name}-model"

    async def generate(self, request):
        return AIResponse(content=self.answer, provider=self.name,
                          model=f"{self.name}-model", tokens_used=5, latency_ms=3)


class FakeScoring:
    def analyze_intent(self, query):
        return None

    def score_models(self, query, intent, available):
        from genesis_protocol.ai.scoring_engine import ModelScore
        return [ModelScore(provider=p, model_name=f"{p}-model", score=1.0)
                for p in available]


class FakeChain:
    def __init__(self, providers):
        self._providers = providers
        self._scoring = FakeScoring()

    def get_available_providers(self):
        return list(self._providers)

    def _map_model_to_provider(self, model, provider, provider_obj):
        return model


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.app as appmod

    monkeypatch.setattr(appmod, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))

    providers = {
        "alpha": FakeProvider("alpha", "The answer is 42."),
        "beta": FakeProvider("beta", "The answer is 42."),
        "gamma": FakeProvider("gamma", "Something unrelated."),
    }
    # The handler imports get_council at call time, so patching the module
    # attribute is enough to inject the fake chain.
    from genesis_protocol.ai import council as council_mod
    monkeypatch.setattr(council_mod, "get_council", lambda: LLMCouncil(chain=FakeChain(providers)))

    appmod.app.config["TESTING"] = True
    return appmod.app.test_client(), tmp_path


def _msg(text, chat_id=1863492058):
    return {"message": {"text": text, "from": {"id": chat_id}, "chat": {"id": chat_id}}}


def _replies(tmp_path):
    import json
    path = tmp_path / "replies.json"
    return json.loads(path.read_text()) if path.exists() else []


def test_council_without_question_shows_help(client):
    c, tmp_path = client
    resp = c.post("/api/telegram/webhook", json=_msg("/council"))
    assert resp.status_code == 200
    assert resp.get_json()["queued"] == "council-help"
    assert any("Council" in r["text"] for r in _replies(tmp_path))


def test_council_answers_and_reports_members(client):
    c, tmp_path = client
    resp = c.post("/api/telegram/webhook", json=_msg("/council what is the answer?"))
    assert resp.status_code == 200
    assert resp.get_json()["queued"] == "council"
    replies = _replies(tmp_path)
    assert replies
    assert "Council" in replies[-1]["text"]
    assert "42" in replies[-1]["text"]


def test_council_vote_strategy_parsed(client):
    c, tmp_path = client
    resp = c.post("/api/telegram/webhook", json=_msg("/council vote what is the answer?"))
    assert resp.status_code == 200
    text = _replies(tmp_path)[-1]["text"]
    assert "vote" in text.lower()
    assert "42" in text
