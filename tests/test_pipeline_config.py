import pytest

import app.prompts as p
from app.config import resolve_pipeline
from app.stages import STAGES

BUILTIN_ORDER = [s.name for s in STAGES]


def _write_skill(repo, name, body):
    skill_dir = repo / ".step-by-step" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(body)


def test_no_pipeline_yields_builtins_in_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    stages = resolve_pipeline({}, str(tmp_path))
    assert [s.name for s in stages] == BUILTIN_ORDER
    by_name = {s.name: s for s in stages}
    assert by_name["Decomposition"].kind == "decompose"
    assert by_name["Implementation"].kind == "parallel"
    assert by_name["Code Quality"].kind == "gate"
    assert by_name["Commit & PR"].kind == "commit_pr"


def test_custom_pipeline_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    stages = resolve_pipeline({"pipeline": ["Planning", "Documentation"]}, str(tmp_path))
    assert [s.name for s in stages] == ["Planning", "Documentation"]


def test_custom_simple_phase_uses_skill_body(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    _write_skill(tmp_path, "research", "Investigate {prompt} first.\n")
    config = {
        "pipeline": ["Research", "Planning"],
        "phases": {"Research": {"kind": "simple", "skill": "research"}},
    }
    stages = {s.name: s for s in resolve_pipeline(config, str(tmp_path))}
    assert stages["Research"].kind == "simple"
    assert stages["Research"].prompt_template == "Investigate {prompt} first.\n"


def test_builtin_skill_override(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    _write_skill(tmp_path, "my-planning", "Custom planning prompt.\n")
    config = {"phases": {"Planning": {"skill": "my-planning"}}}
    stages = {s.name: s for s in resolve_pipeline(config, str(tmp_path))}
    assert stages["Planning"].prompt_template == "Custom planning prompt.\n"
    assert stages["Planning"].prompt_template != p.PLANNING


def test_phase_provider_override(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = {"phases": {"Planning": {"provider": "gemini"}}}
    stages = {s.name: s for s in resolve_pipeline(config, str(tmp_path))}
    assert stages["Planning"].provider.name == "gemini"
