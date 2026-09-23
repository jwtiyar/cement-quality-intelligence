"""API tests — Pydantic validation, route behavior, error mapping."""

import os
import re
import asyncio
import threading
import time

import httpx
import pytest
from fastapi import FastAPI
from sklearn.feature_extraction.text import TfidfVectorizer

import routes
import state
from routes import ml_reliability_context, router
from schemas import PredictionContext


class ApiClient:
    """Synchronous facade over HTTPX's supported ASGI transport."""

    def __init__(self, app: FastAPI):
        self.app = app

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.request("POST", path, **kwargs)


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    state.reload_from_csv()
    return ApiClient(app)


@pytest.fixture(autouse=True)
def disable_optional_typesafe(monkeypatch):
    """Keep API assertions deterministic even when the user has a local key."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


BASE_MATERIALS = {
    "limestone": {"SiO2": 3.0, "Al2O3": 0.8, "Fe2O3": 0.5, "CaO": 52.0, "MgO": 0.5, "Na2O": 0.05, "K2O": 0.1, "SO3": 0.1, "LOI": 42.0, "H2O": 2.0},
    "shale": {"SiO2": 60.0, "Al2O3": 16.0, "Fe2O3": 7.0, "CaO": 3.0, "MgO": 2.0, "Na2O": 0.3, "K2O": 2.0, "SO3": 0.5, "LOI": 5.0, "H2O": 8.0},
    "sand": {"SiO2": 92.0, "Al2O3": 3.0, "Fe2O3": 1.5, "CaO": 0.5, "MgO": 0.1, "Na2O": 0.1, "K2O": 0.3, "SO3": 0.0, "LOI": 1.0, "H2O": 1.0},
    "pyrite": {"SiO2": 8.0, "Al2O3": 2.0, "Fe2O3": 75.0, "CaO": 1.0, "MgO": 0.5, "Na2O": 0.1, "K2O": 0.2, "SO3": 0.3, "LOI": 10.0, "H2O": 3.0},
}


class TestRawmixEndpoint:
    def test_slow_typesafe_review_does_not_block_other_requests(self, monkeypatch):
        import typesafe_ai

        started = threading.Event()

        def slow_review(state, questions):
            started.set()
            time.sleep(0.25)
            return None

        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        monkeypatch.setattr(typesafe_ai, "_evaluate", slow_review)
        state.reload_from_csv()
        app = FastAPI()
        app.include_router(router)

        async def exercise():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
                slow = asyncio.create_task(async_client.post("/api/rawmix/calculate", json={
                    "mode": "solve",
                    "cement_type": "OPC",
                    "materials": BASE_MATERIALS,
                    "hfo": {"heat": 730, "calorific": 9800, "sulfur": 2.5},
                    "targets": {"LSF": 95.0, "SM": 2.4, "AM": 1.5},
                }))
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.01)
                assert started.is_set()
                assert not slow.done()
                assert (await async_client.get("/api/data")).status_code == 200
                assert (await slow).status_code == 200

        asyncio.run(exercise())

    def test_valid_solve(self, client):
        resp = client.post("/api/rawmix/calculate", json={
            "mode": "solve",
            "cement_type": "OPC",
            "materials": BASE_MATERIALS,
            "hfo": {"heat": 730, "calorific": 9800, "sulfur": 2.5},
            "targets": {"LSF": 95.0, "SM": 2.4, "AM": 1.5},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["feasibility"] == "feasible"
        assert abs(body["clinker"]["LSF"] - 95.0) <= 0.5
        assert body["typesafe"] == {"enabled": False}

    def test_invalid_target_type_rejected_422(self, client):
        resp = client.post("/api/rawmix/calculate", json={
            "mode": "solve",
            "cement_type": "OPC",
            "materials": BASE_MATERIALS,
            "targets": {"LSF": "high", "SM": 2.4, "AM": 1.5},
        })
        assert resp.status_code == 422

    def test_negative_oxide_rejected_422(self, client):
        mats = {k: dict(v) for k, v in BASE_MATERIALS.items()}
        mats["shale"]["CaO"] = -5.0
        resp = client.post("/api/rawmix/calculate", json={
            "mode": "solve",
            "cement_type": "OPC",
            "materials": mats,
            "targets": {"LSF": 95.0, "SM": 2.4, "AM": 1.5},
        })
        assert resp.status_code == 422

    def test_unknown_cement_type_rejected_422(self, client):
        resp = client.post("/api/rawmix/calculate", json={
            "mode": "solve",
            "cement_type": "XYZ",
            "materials": BASE_MATERIALS,
            "targets": {"LSF": 95.0, "SM": 2.4, "AM": 1.5},
        })
        assert resp.status_code == 422

    def test_invalid_mode_rejected_422(self, client):
        resp = client.post("/api/rawmix/calculate", json={
            "mode": "mystery",
            "cement_type": "OPC",
            "materials": BASE_MATERIALS,
            "targets": {"LSF": 95.0, "SM": 2.4, "AM": 1.5},
        })
        assert resp.status_code == 422

    def test_calc_mode_alias_accepted(self, client):
        # The frontend has always sent mode="calc" for recipe mode
        resp = client.post("/api/rawmix/calculate", json={
            "mode": "calc",
            "cement_type": "OPC",
            "materials": BASE_MATERIALS,
            "hfo": {"heat": 730, "calorific": 9800, "sulfur": 2.5},
            "recipe": {"limestone": 78, "shale": 18, "sand": 2, "pyrite": 2},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["feasibility"] == "valid"
        assert body["solve_method"] == "recipe"

    def test_missing_material_semantic_400(self, client):
        # All 4 materials are required; Pydantic can't know that, the solver
        # validates it and the route maps ValueError -> 400.
        mats = {k: dict(v) for k, v in BASE_MATERIALS.items()}
        del mats["sand"]
        resp = client.post("/api/rawmix/calculate", json={
            "mode": "solve",
            "cement_type": "OPC",
            "materials": mats,
            "targets": {"LSF": 95.0, "SM": 2.4, "AM": 1.5},
        })
        assert resp.status_code == 400
        assert "Missing materials" in resp.json()["detail"]


class TestChemistryEndpoint:
    def test_valid(self, client):
        resp = client.post("/api/chemistry/analyze", json={
            "SiO2": 21.5, "Al2O3": 5.5, "Fe2O3": 3.5, "CaO": 65.0,
            "MgO": 1.5, "SO3": 0.8,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["moduli"]["LSF"] > 85
        assert body["phases_valid"] is True

    def test_out_of_range_rejected_422(self, client):
        resp = client.post("/api/chemistry/analyze", json={
            "SiO2": 200.0, "Al2O3": 5.0, "Fe2O3": 3.0, "CaO": 60.0,
        })
        assert resp.status_code == 422

    def test_missing_required_rejected_422(self, client):
        resp = client.post("/api/chemistry/analyze", json={"CaO": 60.0})
        assert resp.status_code == 422


class TestPredictEndpoint:
    def test_valid(self, client):
        resp = client.post("/api/predict", json={
            "Cement_Type": "OPC",
            "SiO2": 21.5, "Al2O3": 5.5, "Fe2O3": 3.5, "CaO": 65.0,
            "MgO": 1.5, "SO3": 0.8, "Fineness": 3800,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "prediction" in body
        assert body["predictionSource"] == "recent_mean"
        assert isinstance(body["recentAverage"], (int, float))
        assert isinstance(body["mlPrediction"], (int, float))
        assert body["prediction"] == body["recentAverage"]
        assert "confidence" in body
        assert body["typesafe"]["enabled"] is False

    def test_unknown_type_rejected_422(self, client):
        resp = client.post("/api/predict", json={"Cement_Type": "XYZ"})
        assert resp.status_code == 422

    def test_negative_prediction_feature_rejected_422(self, client):
        resp = client.post("/api/predict", json={"CaO": -1})
        assert resp.status_code == 422

    def test_extra_fields_ignored(self, client):
        resp = client.post("/api/predict", json={
            "Cement_Type": "OPC",
            "bogus_field": 123,
        })
        assert resp.status_code == 200


class TestChatEndpoint:
    def test_chat_deadline_includes_typesafe_reranking(self, client, monkeypatch):
        documents = ["strength test", "cement report"]
        vectorizer = TfidfVectorizer().fit(documents)
        monkeypatch.setattr(routes, "get_rag_index", lambda: {
            "chunks": [
                {"text": text, "source": "manual.pdf", "page": index + 1}
                for index, text in enumerate(documents)
            ],
            "vectorizer": vectorizer,
            "tfidf_matrix": vectorizer.transform(documents),
        })
        def slow_rerank(query, candidates):
            time.sleep(0.2)
            return candidates

        monkeypatch.setattr(routes, "rerank_contexts", slow_rerank)
        monkeypatch.setattr(routes, "CHAT_TIMEOUT_SECONDS", 0.05)

        response = client.post("/api/chat", json={"message": "strength test", "provider": "codex"})

        assert response.status_code == 504

    def test_empty_message_rejected_422(self, client):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 422

    def test_bad_history_role_rejected_422(self, client):
        resp = client.post("/api/chat", json={
            "message": "hi",
            "history": [{"role": "admin", "content": "hello"}],
        })
        assert resp.status_code == 422

    def test_bad_provider_rejected_422(self, client):
        resp = client.post("/api/chat", json={"message": "hi", "provider": "unknown"})
        assert resp.status_code == 422

    def test_codex_provider_uses_rag_prompt_without_gemini_key(self, client, monkeypatch):
        captured = {}

        async def fake_ask_codex(prompt):
            captured["prompt"] = prompt
            return "Codex document answer", "Codex test model"

        monkeypatch.setattr("routes.ask_codex", fake_ask_codex)
        resp = client.post("/api/chat", json={
            "message": "What does the manual say about LSF?",
            "provider": "codex",
            "history": [{"role": "user", "content": "We are checking raw mix."}],
        })

        assert resp.status_code == 200
        assert resp.json()["response"] == "Codex document answer"
        assert resp.json()["provider"] == "codex"
        assert resp.json()["model"] == "Codex test model"
        assert "REFERENCE MANUALS & TECHNICAL STANDARDS" in captured["prompt"]
        assert "We are checking raw mix." in captured["prompt"]
        assert "What does the manual say about LSF?" in captured["prompt"]

    def test_invalid_typesafe_probability_rejected_422(self, client):
        resp = client.post("/api/chat", json={
            "message": "Can I use the latest estimate?",
            "prediction_context": {
                "cement_type": "OPC",
                "prediction": 42.5,
                "prediction_source": "recent_mean",
                "confidence": "exploratory",
                "confidence_label": "Exploratory simulation",
                "r2": 0.4,
                "rmse": 3.2,
                "typesafe": {"enabled": True, "safe_to_show": False, "probability": 1.2, "status": "rejected"},
            },
        })
        assert resp.status_code == 422

    def test_held_prediction_is_explicit_in_gemini_context(self):
        context = PredictionContext.model_validate({
            "cement_type": "SRC",
            "prediction": 38.5,
            "prediction_source": "recent_mean",
            "confidence": "chemistry_only",
            "confidence_label": "Chemistry guidance only — ML confidence low",
            "r2": -0.2,
            "rmse": 5.0,
            "typesafe": {"enabled": True, "safe_to_show": False, "probability": 0.74, "status": "rejected"},
        })

        prompt_context = ml_reliability_context(context)

        assert "SRC 38.50 MPa" in prompt_context
        assert "TypeSafe safe-to-show=False (74%)" in prompt_context
        assert "HELD FOR QUALIFIED REVIEW" in prompt_context
        assert "never present them as production recommendations" in prompt_context

    def test_predict_to_chat_end_to_end_payload_compatibility(self, client, monkeypatch):
        from unittest.mock import AsyncMock
        import routes

        pred_resp = client.post("/api/predict", json={"Cement_Type": "OPC"})
        assert pred_resp.status_code == 200
        pred_data = pred_resp.json()

        assert "prediction" in pred_data
        assert "prediction_source" in pred_data
        assert "typesafe" in pred_data

        prediction_context = {
            "cement_type": "OPC",
            "prediction": pred_data["prediction"],
            "prediction_source": pred_data["prediction_source"],
            "confidence": pred_data["confidence"],
            "confidence_label": pred_data["confidenceLabel"],
            "r2": pred_data["r2"],
            "rmse": pred_data["rmse"],
            "typesafe": pred_data["typesafe"],
        }

        validated = PredictionContext.model_validate(prediction_context)
        assert validated.prediction == pred_data["prediction"]

        monkeypatch.setattr(routes, "ask_codex", AsyncMock(return_value=("Assistant response", "codex-test")))
        chat_resp = client.post("/api/chat", json={
            "message": "What does this estimate mean?",
            "provider": "codex",
            "prediction_context": prediction_context,
        })
        assert chat_resp.status_code == 200
        assert chat_resp.json()["response"] == "Assistant response"

    @pytest.mark.skipif(
        bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        reason="API key present — unconfigured-key path not testable",
    )
    def test_no_api_key_500(self, client):
        resp = client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 500
        assert "not configured" in resp.json()["detail"]


class TestDataEndpoints:
    def test_data_cache(self, client):
        resp = client.get("/api/data")
        assert resp.status_code == 200
        body = resp.json()
        assert body["dataset"]["csvLastModified"] is not None
        assert "ml" in body
        assert set(body["ml"]) == {"OPC", "SRC", "SBC"}

    def test_record_found(self, client):
        latest = client.get("/api/latest_date", params={"type": "OPC"})
        assert latest.status_code == 200
        assert latest.json()["found"] is True

        resp = client.get(
            "/api/record",
            params={"date": latest.json()["date"], "type": "OPC"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is True
        assert "Strength_28D" in body["record"]

    def test_record_not_found(self, client):
        resp = client.get("/api/record", params={"date": "1900-01-01", "type": "OPC"})
        assert resp.status_code == 200
        assert resp.json() == {"found": False}

    def test_record_bad_date_400(self, client):
        resp = client.get("/api/record", params={"date": "not-a-date", "type": "OPC"})
        assert resp.status_code == 400

    def test_latest_date(self, client):
        resp = client.get("/api/latest_date", params={"type": "OPC"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is True
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", body["date"])

    def test_export_csv(self, client):
        resp = client.get("/api/export/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "Date" in resp.text[:200]

    def test_monthly_valid(self, client):
        resp = client.get("/api/monthly", params={"year": 2026, "month": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["labels"]) == 31

    def test_monthly_bad_params_422(self, client):
        resp = client.get("/api/monthly", params={"year": "x", "month": 13})
        assert resp.status_code == 422
