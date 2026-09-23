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


def pytest_addoption(parser):
    parser.addoption(
        "--run-private-data",
        action="store_true",
        default=False,
        help="Run tests that require the private production dataset (>10k records)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "private_data: mark test as requiring the private production CSV"
    )
    if not config.getoption("--run-private-data", default=False):
        os.environ["CEMENT_DATA_CSV"] = SYNTHETIC_CSV_PATH


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-private-data", default=False):
        skip_private = pytest.mark.skip(
            reason="Private dataset tests are opt-in. Pass --run-private-data with a production CSV to run."
        )
        for item in items:
            if "private_data" in item.keywords:
                item.add_marker(skip_private)


@pytest.fixture
def synthetic_csv_path():
    return SYNTHETIC_CSV_PATH


@pytest.fixture
def sparse_csv_path():
    return SPARSE_CSV_PATH


@pytest.fixture(scope="session", autouse=True)
def isolate_test_session(tmp_path_factory):
    """Keep module-scoped setup from writing assistant files into the project."""
    previous_directory = os.getcwd()
    os.chdir(tmp_path_factory.mktemp("cement-session"))
    try:
        yield
    finally:
        os.chdir(previous_directory)


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch, tmp_path):
    """Ensure tests run in isolation with cleared credentials by default."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
