"""Tests for .env parsing (routes.load_env)."""

import os

import pytest

from routes import load_env


@pytest.fixture(autouse=True)
def _clean_env():
    for k in ("TEST_KEY_A", "TEST_KEY_B", "TEST_KEY_C", "TEST_KEY_D"):
        os.environ.pop(k, None)
    yield
    for k in ("TEST_KEY_A", "TEST_KEY_B", "TEST_KEY_C", "TEST_KEY_D"):
        os.environ.pop(k, None)


def test_parses_simple_pairs(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text("TEST_KEY_A=hello\nTEST_KEY_B=world\n")
    load_env([str(env_file)])
    assert os.environ["TEST_KEY_A"] == "hello"
    assert os.environ["TEST_KEY_B"] == "world"


def test_inline_comment_stripped(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text("TEST_KEY_A=value123 # keep me out\n")
    load_env([str(env_file)])
    assert os.environ["TEST_KEY_A"] == "value123"


def test_embedded_equals_kept(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text("TEST_KEY_A=abc=def=ghi\n")
    load_env([str(env_file)])
    assert os.environ["TEST_KEY_A"] == "abc=def=ghi"


def test_quotes_and_whitespace_stripped(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text('TEST_KEY_A =  "  quoted  value "  \n')
    load_env([str(env_file)])
    assert os.environ["TEST_KEY_A"] == "  quoted  value "


def test_comments_and_blank_lines_skipped(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text("# a comment\n\nTEST_KEY_A=1\n")
    load_env([str(env_file)])
    assert os.environ["TEST_KEY_A"] == "1"
    assert "TEST_KEY_B" not in os.environ
