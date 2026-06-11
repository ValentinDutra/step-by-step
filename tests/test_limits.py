import asyncio

import pytest

from app.config import (
    Confirm,
    Limits,
    provider_for,
    resolve_artifacts,
    resolve_confirm,
    resolve_limits,
    resolve_pipeline,
)
from app.pipeline import run_stage
from app.providers.base import ProviderResult
from app.stages import Stage


class _RecordingProvider:
    name = "stub"

    def __init__(self):
        self.prompts = []

    async def run(self, prompt, working_dir, on_stream=None):
        self.prompts.append(prompt)
        return ProviderResult(True, "ok", cost_usd=None)


def test_defaults_when_section_absent():
    assert resolve_limits({}) == Limits()


def test_overrides_applied_and_ints_accepted_for_float_fields():
    limits = resolve_limits(
        {
            "limits": {
                "provider_timeout_seconds": 1200,
                "max_ram_pct": 60,
                "max_cost_usd": 5,
                "prev_output_chars": 12000,
            }
        }
    )
    assert limits.provider_timeout_seconds == 1200
    assert limits.max_ram_pct == 60.0
    assert limits.max_cost_usd == 5.0
    assert limits.prev_output_chars == 12000
    assert limits.worker_prev_output_chars == 6000  # untouched default


def test_unknown_key_rejected():
    with pytest.raises(ValueError, match="Unknown key\\(s\\) in \\[limits\\]: timeout"):
        resolve_limits({"limits": {"timeout": 600}})


@pytest.mark.parametrize(
    "key, value",
    [
        ("max_ram_pct", 0),
        ("max_ram_pct", 150),
        ("provider_timeout_seconds", -1),
        ("provider_timeout_seconds", 1.5),
        ("max_cost_usd", 0),
        ("feedback_chars", 0),
        ("default_max_iterations", True),
    ],
)
def test_bad_ranges_rejected(key, value):
    with pytest.raises(ValueError, match=f"\\[limits\\] {key} must be"):
        resolve_limits({"limits": {key: value}})


def test_default_max_iterations_reaches_stage(tmp_path):
    config = {"limits": {"default_max_iterations": 5}}
    stages = resolve_pipeline(config, str(tmp_path))
    gate = next(stage for stage in stages if stage.kind == "gate")
    assert gate.max_iterations == 5


def test_run_stage_truncates_prev_output_per_limits(tmp_path):
    provider = _RecordingProvider()
    stage = Stage(name="X", prompt_template="PREV:{prev_output}", provider=provider)
    output = asyncio.run(
        run_stage(
            stage, "task", "a" * 100, str(tmp_path), limits=Limits(prev_output_chars=10)
        )
    )
    assert output == "ok"
    assert provider.prompts == ["PREV:" + "a" * 10]


def test_provider_for_timeout_reaches_provider():
    provider = provider_for("claude", "", timeout_seconds=42)
    assert provider.timeout_seconds == 42


def test_configured_timeout_propagates_through_resolve_pipeline(tmp_path):
    config = {"limits": {"provider_timeout_seconds": 1200}}
    stages = resolve_pipeline(config, str(tmp_path))
    assert all(stage.provider.timeout_seconds == 1200 for stage in stages)


@pytest.mark.parametrize(
    "resolve, match",
    [
        (
            lambda: resolve_pipeline({"defaults": {"skip_permissions": "yes"}}, "."),
            "skip_permissions must be a boolean",
        ),
        (
            lambda: resolve_confirm({"confirm": {"step": "yes"}}, ["Planning"]),
            "step must be a boolean",
        ),
        (
            lambda: resolve_confirm({"confirm": {"phases": "Planning"}}, ["Planning"]),
            "phases must be a list of strings",
        ),
        (
            lambda: resolve_artifacts({"artifacts": {"enabled": "yes"}}),
            "enabled must be a boolean",
        ),
        (
            lambda: resolve_artifacts({"artifacts": {"dir": ""}}),
            "dir must be a non-empty string",
        ),
    ],
)
def test_invalid_config_value_types_rejected(resolve, match):
    with pytest.raises(ValueError, match=match):
        resolve()


def test_resolve_confirm_defaults():
    assert resolve_confirm({}, ["Planning"]) == Confirm()


def test_resolve_confirm_unknown_key_rejected():
    with pytest.raises(ValueError, match="Unknown key\\(s\\) in \\[confirm\\]: pause"):
        resolve_confirm({"confirm": {"pause": True}}, ["Planning"])


def test_resolve_confirm_unknown_phase_rejected():
    with pytest.raises(ValueError, match="not in the pipeline: Bogus"):
        resolve_confirm({"confirm": {"phases": ["Bogus"]}}, ["Planning"])


def test_resolve_confirm_valid_settings_accepted():
    confirm = resolve_confirm(
        {"confirm": {"phases": ["Planning"], "step": True, "review_tasks": True}},
        ["Planning", "Commit & PR"],
    )
    assert confirm.phases == ("Planning",)
    assert confirm.step is True
    assert confirm.review_tasks is True


def test_explicit_phase_max_iterations_wins_over_default(tmp_path):
    config = {
        "limits": {"default_max_iterations": 5},
        "phases": {"Code Quality": {"max_iterations": 2}},
    }
    stages = resolve_pipeline(config, str(tmp_path))
    gate = next(stage for stage in stages if stage.kind == "gate")
    assert gate.max_iterations == 2
