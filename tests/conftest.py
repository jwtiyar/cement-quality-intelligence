"""Pytest configuration for cement_app.

Makes the project root importable and configures test isolation and default
fixtures so tests don't leak environment variables or depend on external APIs.
"""

import os
import sys
import pytest

# Ensure the cement_app directory (parent of tests/) is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SYNTHETIC_CSV_PATH = os.path.join(FIXTURES_DIR, "synthetic_cement_data.csv")
SPARSE_CSV_PATH = os.path.join(FIXTURES_DIR, "sparse_cement_data.csv")


@pytest.fixture
def synthetic_csv_path():
    return SYNTHETIC_CSV_PATH


@pytest.fixture
def sparse_csv_path():
    return SPARSE_CSV_PATH


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    """Ensure tests run in isolation with cleared credentials by default."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

