import textwrap

from app import config as config_module
from app.check import run_check


def _write(path, content):
    path.write_text(textwrap.dedent(content))


def test_valid_config_prints_phases_and_returns_0(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    monkeypatch.setattr(config_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "step-by-step.toml", '[defaults]\nprovider="claude"\n')

    code = run_check(str(repo), "")
    out = capsys.readouterr().out

    assert code == 0
    assert "step-by-step.toml" in out
    assert "Planning" in out and "Commit & PR" in out
    assert "provider_timeout_seconds = 600" in out
    assert "all provider CLIs found" in out


def test_unknown_provider_returns_1_with_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "step-by-step.toml", '[defaults]\nprovider="gpt"\n')

    code = run_check(str(repo), "")
    out = capsys.readouterr().out

    assert code == 1
    assert "Config error" in out
    assert "Unknown provider" in out


def test_no_config_reports_builtin_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    monkeypatch.setattr(config_module.shutil, "which", lambda name: f"/usr/bin/{name}")

    code = run_check(str(tmp_path), "")
    out = capsys.readouterr().out

    assert code == 0
    assert "built-in default" in out


def test_missing_provider_cli_is_reported_but_returns_0(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    monkeypatch.setattr(config_module.shutil, "which", lambda name: None)

    code = run_check(str(tmp_path), "")
    out = capsys.readouterr().out

    assert code == 0
    assert "Preflight:" in out
    assert "claude" in out
