from codex_provider import _copy_auth_cache, _thread_params


def test_codex_thread_is_ephemeral_and_locked_down(tmp_path):
    params = _thread_params(str(tmp_path))

    assert params["ephemeral"] is True
    assert params["model"] == "gpt-5.6-luna"
    assert params["sandbox"] == "read-only"
    assert params["approvalPolicy"] == "never"
    assert params["config"]["mcp_servers"] == {}
    assert params["config"]["apps"]["_default"]["enabled"] is False
    assert params["config"]["features"]["web_search"] is False
    assert "Do not call tools" in params["baseInstructions"]


def test_auth_cache_is_copied_with_private_permissions(tmp_path, monkeypatch):
    source_home = tmp_path / "source"
    source_home.mkdir()
    (source_home / "auth.json").write_text('{"auth_mode":"chatgpt"}')
    monkeypatch.setenv("CODEX_HOME", str(source_home))

    target_home = tmp_path / "target"
    _copy_auth_cache(target_home)

    target_auth = target_home / "auth.json"
    assert target_auth.read_text() == '{"auth_mode":"chatgpt"}'
    assert target_auth.stat().st_mode & 0o777 == 0o600
