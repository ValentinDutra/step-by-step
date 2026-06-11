import pytest

from app.config import resolve_pipeline
from app.providers.claude import ClaudeProvider
from app.providers.codex import CodexProvider
from app.providers.gemini import GeminiProvider

DANGER_FLAGS = {
    ClaudeProvider: "--dangerously-skip-permissions",
    CodexProvider: "--dangerously-bypass-approvals-and-sandbox",
    GeminiProvider: "--yolo",
}


def _build(provider):
    if isinstance(provider, GeminiProvider):
        return provider._build_cmd("hi")
    return provider._build_cmd()


@pytest.mark.parametrize("provider_cls", [ClaudeProvider, CodexProvider, GeminiProvider])
def test_danger_flag_present_by_default(provider_cls):
    assert DANGER_FLAGS[provider_cls] in _build(provider_cls())


@pytest.mark.parametrize("provider_cls", [ClaudeProvider, CodexProvider, GeminiProvider])
def test_danger_flag_omitted_when_skip_permissions_false(provider_cls):
    assert DANGER_FLAGS[provider_cls] not in _build(provider_cls(skip_permissions=False))


@pytest.mark.parametrize("provider_cls", [ClaudeProvider, CodexProvider, GeminiProvider])
def test_extra_args_appended_last(provider_cls):
    cmd = _build(provider_cls(model="m", extra_args=("--flag-a", "value")))
    assert cmd[-2:] == ["--flag-a", "value"]


def test_codex_keeps_exec_dash_positional():
    assert CodexProvider()._build_cmd()[:4] == ["codex", "exec", "-", "--json"]


def test_phase_skip_permissions_false_reaches_stage_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = {"phases": {"Code Quality": {"skip_permissions": False}}}
    stages = {s.name: s for s in resolve_pipeline(config, str(tmp_path))}
    assert stages["Code Quality"].provider.skip_permissions is False
    assert stages["Planning"].provider.skip_permissions is True


def test_extra_args_must_be_list_of_strings(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = {"defaults": {"extra_args": "nope"}}
    with pytest.raises(ValueError, match="extra_args must be a list of strings"):
        resolve_pipeline(config, str(tmp_path))
