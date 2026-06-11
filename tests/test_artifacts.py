import json

import pytest

from app import artifacts as artifacts_module
from app.artifacts import RunArtifacts
from app.config import Artifacts, resolve_artifacts
from app.models import PipelineStats
from app.stages import Stage


def test_start_record_finish_produce_expected_files(tmp_path):
    artifacts = RunArtifacts.start(str(tmp_path), ".step-by-step/runs", "do the thing")
    assert (artifacts.run_dir / "prompt.txt").read_text() == "do the thing"

    stage = Stage(name="Tests & Validation", prompt_template="")
    stage.start()
    stage.complete("all good")
    artifacts.record_stage(3, stage)
    stage_file = artifacts.run_dir / "04-tests-validation.md"
    content = stage_file.read_text()
    assert "all good" in content
    assert "status: completed" in content

    stats = PipelineStats()
    stats.add_call(0.5)
    artifacts.finish(stats, failed=False)
    payload = json.loads((artifacts.run_dir / "run.json").read_text())
    assert payload["total_calls"] == 1
    assert payload["total_cost_usd"] == 0.5
    assert payload["failed"] is False


def test_failed_stage_records_error(tmp_path):
    artifacts = RunArtifacts.start(str(tmp_path), "runs", "p")
    stage = Stage(name="Planning", prompt_template="")
    stage.start()
    stage.fail("boom")
    artifacts.record_stage(0, stage)
    content = (artifacts.run_dir / "01-planning.md").read_text()
    assert "boom" in content
    assert "status: failed" in content


def test_start_is_collision_safe(tmp_path, monkeypatch):
    real_datetime = artifacts_module.datetime

    class _Frozen:
        @staticmethod
        def now():
            return real_datetime(2026, 1, 1, 12, 0, 0)

    monkeypatch.setattr(artifacts_module, "datetime", _Frozen)
    first = RunArtifacts.start(str(tmp_path), "runs", "p")
    second = RunArtifacts.start(str(tmp_path), "runs", "p")
    assert first.run_dir != second.run_dir
    assert second.run_dir.name == "20260101_120000-2"


def test_resolve_artifacts_defaults():
    assert resolve_artifacts({}) == Artifacts()
    assert resolve_artifacts({}).enabled is False


def test_resolve_artifacts_unknown_key_rejected():
    with pytest.raises(ValueError, match="Unknown key\\(s\\) in \\[artifacts\\]: enable"):
        resolve_artifacts({"artifacts": {"enable": True}})
