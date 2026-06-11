import pytest

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
