import pytest

from app.config import Limits, resolve_limits, resolve_pipeline


def test_defaults_when_section_absent():
    limits = resolve_limits({})
    assert limits == Limits()
    assert limits.provider_timeout_seconds == 600
    assert limits.max_ram_pct == 75.0
    assert limits.max_cost_usd is None
    assert limits.default_max_iterations == 3
    assert limits.prev_output_chars == 8000


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


def test_explicit_phase_max_iterations_wins_over_default(tmp_path):
    config = {
        "limits": {"default_max_iterations": 5},
        "phases": {"Code Quality": {"max_iterations": 2}},
    }
    stages = resolve_pipeline(config, str(tmp_path))
    gate = next(stage for stage in stages if stage.kind == "gate")
    assert gate.max_iterations == 2
