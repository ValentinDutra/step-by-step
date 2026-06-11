import textwrap

import pytest

from app.config import load_config, resolve_providers

PHASES = ["Planning", "Code Quality"]


def _write(path, content):
    path.write_text(textwrap.dedent(content))


def test_project_config_takes_precedence_over_user(tmp_path, monkeypatch):
    user_dir = tmp_path / "userhome"
    (user_dir / "step-by-step").mkdir(parents=True)
    _write(user_dir / "step-by-step" / "config.toml", '[defaults]\nprovider="gemini"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user_dir))

    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "step-by-step.toml", '[defaults]\nprovider="codex"\n')

    config = load_config(str(repo))
    assert config["defaults"]["provider"] == "codex"


def test_explicit_path_overrides_project(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "step-by-step.toml", '[defaults]\nprovider="codex"\n')
    explicit = tmp_path / "custom.toml"
    _write(explicit, '[defaults]\nprovider="gemini"\n')

    config = load_config(str(repo), str(explicit))
    assert config["defaults"]["provider"] == "gemini"


def test_no_config_defaults_to_claude(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = load_config(str(tmp_path / "repo-without-config"))
    resolved = resolve_providers(config, PHASES)
    assert all(provider.name == "claude" for provider, _ in resolved.values())


def test_defaults_applied_to_phases_without_override():
    config = {
        "defaults": {"provider": "codex", "model": "x"},
        "phases": {"Planning": {"provider": "gemini"}},
    }
    resolved = resolve_providers(config, PHASES)
    assert resolved["Planning"][0].name == "gemini"
    assert resolved["Code Quality"][0].name == "codex"


def test_unknown_provider_fails_fast():
    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_providers({"defaults": {"provider": "gpt"}}, PHASES)


def test_unknown_phase_name_fails_fast():
    with pytest.raises(ValueError, match="Unknown phase"):
        resolve_providers({"phases": {"Bogus": {"provider": "claude"}}}, PHASES)
