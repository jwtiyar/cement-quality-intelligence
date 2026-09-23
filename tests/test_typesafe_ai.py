"""Offline contract tests for the optional TypeSafe decision adapter."""

import json
from types import SimpleNamespace

import httpx2
import typesafe_sdk

import typesafe_ai


def test_installed_sdk_serializes_questions_and_parses_answers(monkeypatch):
    real_client = typesafe_sdk.TypeSafeClient

    def respond(request):
        payload = json.loads(request.content)
        assert payload["state"]["cement_type"] == "OPC"
        assert payload["questions"]["recommended_action"]["type"] == "choice"
        assert payload["questions"]["requires_human_review"]["type"] == "noul"
        return httpx2.Response(200, json={
            "model": "jev-latest",
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "answers": {
                "recommended_action": {
                    "type": "choice", "choice": "monitor", "confidence": 0.9,
                    "probabilities": {"monitor": 0.9, "adjust_recipe": 0.05, "stop_and_review": 0.05},
                },
                "requires_human_review": {"type": "noul", "noul": 0.1},
            },
        })

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", lambda: real_client(
        api_key="test-key", base_url="https://typesafe.test", transport=httpx2.MockTransport(respond),
    ))
    result = typesafe_ai.judge_rawmix("OPC", {"LSF": 95.0}, [])
    assert result["enabled"] is True
    assert result["action"] == "monitor"
    assert result["requires_human_review"] is False


def test_typesafe_adapter_bounds_optional_network_call(monkeypatch):
    sentinel = object()

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def system_one(self, *, state, questions, timeout, retry):
            assert timeout == 8.0
            assert retry.max_retries == 0
            return sentinel

    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", Client)

    assert typesafe_ai._evaluate({"sample": "OPC"}, {}) is sentinel


def test_optional_adapter_is_a_noop_without_response(monkeypatch):
    monkeypatch.setattr(typesafe_ai, "_evaluate", lambda state, questions: None)
    candidates = [{"text": "first"}, {"text": "second"}]

    assert typesafe_ai.judge_rawmix("OPC", {"LSF": 95.0}, []) == {"enabled": False}
    assert typesafe_ai.rerank_contexts("query", candidates) is candidates
    assert typesafe_ai.assess_prediction("OPC", 42.0, "predictive", 0.8, 2.0) == {
        "enabled": False,
        "safe_to_show": None,
        "probability": None,
        "status": "not_reviewed",
    }


def test_malformed_response_falls_back_to_deterministic_behavior(monkeypatch):
    monkeypatch.setattr(typesafe_ai, "_evaluate", lambda state, questions: SimpleNamespace())
    candidates = [{"text": "first"}, {"text": "second"}]

    assert typesafe_ai.judge_rawmix("OPC", {"LSF": 95.0}, []) == {"enabled": False}
    assert typesafe_ai.rerank_contexts("query", candidates) is candidates
    assert typesafe_ai.assess_prediction("OPC", 42.0, "predictive", 0.8, 2.0) == {
        "enabled": False,
        "safe_to_show": None,
        "probability": None,
        "status": "not_reviewed",
    }


def test_rawmix_judgment_preserves_typed_decision(monkeypatch):
    captured = {}

    def evaluate(state, questions):
        captured["state"] = state
        captured["questions"] = questions
        return SimpleNamespace(
            choices={
                "recommended_action": SimpleNamespace(
                    choice="adjust_recipe",
                    confidence=0.91,
                    probabilities={"monitor": 0.04, "adjust_recipe": 0.91, "stop_and_review": 0.05},
                )
            },
            nouls={"requires_human_review": SimpleNamespace(noul=0.88)},
        )

    monkeypatch.setattr(typesafe_ai, "_evaluate", evaluate)
    result = typesafe_ai.judge_rawmix(
        "OPC",
        {"LSF": 95.0, "SM": 2.4, "AM": 1.5},
        [{"severity": "warning", "message": "high liquid phase"}],
    )

    assert result["enabled"] is True
    assert result["action"] == "adjust_recipe"
    assert result["confidence"] == 0.91
    assert result["requires_human_review"] is True
    assert result["review_probability"] == 0.88
    assert captured["state"]["cement_type"] == "OPC"
    assert set(captured["questions"]) == {"recommended_action", "requires_human_review"}


def test_contexts_are_reranked_by_typesafe_relevance(monkeypatch):
    def evaluate(state, questions):
        return SimpleNamespace(
            nouls={
                "candidate_0": SimpleNamespace(noul=0.2),
                "candidate_1": SimpleNamespace(noul=0.85),
            }
        )

    monkeypatch.setattr(typesafe_ai, "_evaluate", evaluate)
    result = typesafe_ai.rerank_contexts(
        "What affects strength?",
        [{"id": "low", "text": "unrelated"}, {"id": "high", "text": "strength evidence"}],
    )

    assert [item["id"] for item in result] == ["high", "low"]
    assert [item["typesafe_score"] for item in result] == [0.85, 0.2]


def test_prediction_gate_requires_high_typesafe_probability(monkeypatch):
    monkeypatch.setattr(
        typesafe_ai,
        "_evaluate",
        lambda state, questions: SimpleNamespace(
            nouls={"safe_to_show": SimpleNamespace(noul=0.74)}
        ),
    )

    result = typesafe_ai.assess_prediction("SRC", 38.5, "chemistry_only", -0.2, 5.0)

    assert result == {
        "enabled": True,
        "safe_to_show": False,
        "probability": 0.74,
        "status": "rejected",
    }


def test_prediction_gate_approves_when_typesafe_probability_high(monkeypatch):
    monkeypatch.setattr(
        typesafe_ai,
        "_evaluate",
        lambda state, questions: SimpleNamespace(
            nouls={"safe_to_show": SimpleNamespace(noul=0.85)}
        ),
    )

    result = typesafe_ai.assess_prediction("OPC", 42.0, "predictive", 0.8, 2.0)

    assert result == {
        "enabled": True,
        "safe_to_show": True,
        "probability": 0.85,
        "status": "approved",
    }
