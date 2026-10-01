"""Tests for seasonal and 3-month averages endpoint and calculation logic."""

import pytest
from fastapi import FastAPI
import httpx
import asyncio

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
