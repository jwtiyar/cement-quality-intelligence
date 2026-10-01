"""Tests for seasonal and 3-month averages endpoint and calculation logic."""

import pytest
from fastapi import FastAPI
import httpx
import asyncio
from types import SimpleNamespace

import pandas as pd

import routes
import state
from routes import router


class ApiClient:
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


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    state.reload_from_csv()
    return ApiClient(app)


class TestAveragesEndpoint:
    def test_default_all_time(self, client):
        resp = client.get("/api/averages")
        assert resp.status_code == 200
        body = resp.json()
        assert body["periodType"] == "all"
        assert "Full Dataset" in body["periodLabel"]
        assert body["totalRecords"] > 0
        assert "OPC" in body["avgStrength"]
        assert "SRC" in body["avgStrength"]
        assert "SBC" in body["avgStrength"]
        assert "overall" in body["avgStrength"]
        assert "OPC" in body["avgC3S"]
        assert "SRC" in body["avgC3S"]
        assert "SBC" in body["avgC3S"]
        assert "overall" in body["avgC3S"]
        assert len(body["seasonalBreakdown"]) == 4
        assert len(body["quarterlyBreakdown"]) == 4
        assert len(body["availableYears"]) >= 1

    def test_season_filter(self, client):
        resp = client.get("/api/averages", params={"period_type": "season", "season": "summer"})
        assert resp.status_code == 200
        body = resp.json()
        assert "Summer" in body["periodLabel"]
        assert body["totalRecords"] > 0
        assert body["avgStrength"]["OPC"] is not None
        assert body["avgC3S"]["OPC"] is not None
        assert len(body["seasonalBreakdown"]) == 4

    def test_quarter_filter(self, client):
        resp = client.get("/api/averages", params={"period_type": "quarter", "quarter": "Q1"})
        assert resp.status_code == 200
        body = resp.json()
        assert "Q1" in body["periodLabel"]
        assert body["totalRecords"] > 0
        assert body["avgStrength"]["OPC"] is not None

    def test_custom_months_filter(self, client):
        resp = client.get("/api/averages", params={"period_type": "months", "months": "5,6,7"})
        assert resp.status_code == 200
        body = resp.json()
        assert "May" in body["periodLabel"]
        assert body["totalRecords"] > 0

    def test_year_and_season_filter(self, client):
        resp = client.get("/api/averages", params={"period_type": "season", "season": "spring", "year": "2024"})
        assert resp.status_code == 200
        body = resp.json()
        assert "Spring" in body["periodLabel"]
        assert "2024" in body["periodLabel"]
        assert body["totalRecords"] > 0

    def test_data_cache_includes_averages(self, client):
        resp = client.get("/api/data")
        assert resp.status_code == 200
        body = resp.json()
        assert "averages" in body
        assert len(body["averages"]["seasonalBreakdown"]) == 4
        assert body["averages"]["periodLabel"] == "Full Dataset (All Time)"

    @pytest.mark.parametrize("period,expected_mean,expected_coverage", [
        ({"period_type": "season", "season": "winter"}, 50.0, "Dec 2024 – Feb 2025"),
        ({"period_type": "months", "months": "12,1,2"}, 50.0, "Dec 2024 – Feb 2025"),
        ({"period_type": "months", "months": "11,12,1"}, 40.0, "Nov 2024 – Jan 2025"),
    ])
    def test_cross_year_period_uses_starting_year(self, client, monkeypatch, period, expected_mean, expected_coverage):
        df = pd.DataFrame({
            "Year": [2023, 2024, 2024, 2024, 2024, 2025, 2025, 2025],
            "Month_Num": [12, 1, 2, 11, 12, 1, 2, 12],
            "Cement_Type": ["OPC"] * 8,
            "Strength_28D": [900, 800, 700, 30, 40, 50, 60, 600],
            "C3S": [900, 800, 700, 30, 40, 50, 60, 600],
        })
        monkeypatch.setattr(state, "get_snapshot", lambda: SimpleNamespace(df=df))
        response = client.get("/api/averages", params={**period, "year": "2024"})
        assert response.status_code == 200
        body = response.json()
        assert body["totalRecords"] == 3
        assert body["avgStrength"]["OPC"] == expected_mean
        assert body["avgC3S"]["OPC"] == expected_mean
        assert body["sampleCounts"]["Strength_28D"]["OPC"] == 3
        assert expected_coverage in body["periodLabel"]
        assert body["yearsCoverage"] == expected_coverage
        winter = next(s for s in body["seasonalBreakdown"] if s["key"] == "winter")
        assert winter["avgStrength"]["OPC"] == 50.0
        assert winter["label"] == "Dec 2024 – Feb 2025"
