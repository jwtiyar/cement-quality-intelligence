"""API tests — Pydantic validation, route behavior, error mapping."""

import os
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import state
from routes import router


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    state.reload_from_csv()
    return TestClient(app)


BASE_MATERIALS = {
    "limestone": {"SiO2": 3.0, "Al2O3": 0.8, "Fe2O3": 0.5, "CaO": 52.0, "MgO": 0.5, "Na2O": 0.05, "K2O": 0.1, "SO3": 0.1, "LOI": 42.0, "H2O": 2.0},
    "shale": {"SiO2": 60.0, "Al2O3": 16.0, "Fe2O3": 7.0, "CaO": 3.0, "MgO": 2.0, "Na2O": 0.3, "K2O": 2.0, "SO3": 0.5, "LOI": 5.0, "H2O": 8.0},
    "sand": {"SiO2": 92.0, "Al2O3": 3.0, "Fe2O3": 1.5, "CaO": 0.5, "MgO": 0.1, "Na2O": 0.1, "K2O": 0.3, "SO3": 0.0, "LOI": 1.0, "H2O": 1.0},
    "pyrite": {"SiO2": 8.0, "Al2O3": 2.0, "Fe2O3": 75.0, "CaO": 1.0, "MgO": 0.5, "Na2O": 0.1, "K2O": 0.2, "SO3": 0.3, "LOI": 10.0, "H2O": 3.0},
}


class TestRawmixEndpoint:
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
        assert "confidence" in body

    def test_unknown_type_rejected_422(self, client):
        resp = client.post("/api/predict", json={"Cement_Type": "XYZ"})
        assert resp.status_code == 422

    def test_extra_fields_ignored(self, client):
        resp = client.post("/api/predict", json={
            "Cement_Type": "OPC",
            "bogus_field": 123,
        })
        assert resp.status_code == 200


class TestChatEndpoint:
    def test_empty_message_rejected_422(self, client):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 422

    def test_bad_history_role_rejected_422(self, client):
        resp = client.post("/api/chat", json={
            "message": "hi",
            "history": [{"role": "admin", "content": "hello"}],
        })
        assert resp.status_code == 422

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
