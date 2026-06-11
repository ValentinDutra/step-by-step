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


def test_empty_pipeline_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    with pytest.raises(ValueError, match="empty"):
        resolve_pipeline({"pipeline": []}, str(tmp_path))


def test_duplicate_names_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    with pytest.raises(ValueError, match="Duplicate"):
        resolve_pipeline({"pipeline": ["Planning", "Planning"]}, str(tmp_path))


def test_parallel_without_decompose_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    with pytest.raises(ValueError, match="requires a 'decompose'"):
        resolve_pipeline({"pipeline": ["Planning", "Implementation"]}, str(tmp_path))


def test_more_than_one_commit_pr_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = {
        "pipeline": ["Commit & PR", "Publish"],
        "phases": {"Publish": {"kind": "commit_pr", "prompt": "ship it"}},
    }
    with pytest.raises(ValueError, match="commit_pr"):
        resolve_pipeline(config, str(tmp_path))


def test_more_than_one_gate_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = {
        "pipeline": ["Code Quality", "Review"],
        "phases": {"Review": {"kind": "gate", "prompt": "review"}},
    }
    with pytest.raises(ValueError, match="gate"):
        resolve_pipeline(config, str(tmp_path))


def test_custom_non_simple_kind_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = {
        "pipeline": ["Research"],
        "phases": {"Research": {"kind": "decompose", "prompt": "x"}},
    }
    with pytest.raises(ValueError, match="must be kind 'simple'"):
        resolve_pipeline(config, str(tmp_path))


def test_both_skill_and_prompt_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    _write_skill(tmp_path, "x", "body\n")
    config = {"phases": {"Planning": {"skill": "x", "prompt": "y"}}}
    with pytest.raises(ValueError, match="both 'skill' and 'prompt'"):
        resolve_pipeline(config, str(tmp_path))


def test_custom_phase_without_skill_or_prompt_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = {"pipeline": ["Research"], "phases": {"Research": {"kind": "simple"}}}
    with pytest.raises(ValueError, match="must declare a 'skill' or 'prompt'"):
        resolve_pipeline(config, str(tmp_path))


def test_eval_prompt_on_non_gate_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = {"phases": {"Planning": {"eval_prompt": "good? {prev_output}"}}}
    with pytest.raises(ValueError, match="only 'gate' phases"):
        resolve_pipeline(config, str(tmp_path))


def test_both_eval_skill_and_eval_prompt_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    _write_skill(tmp_path, "judge", "verdict {prev_output}\n")
    config = {"phases": {"Code Quality": {"eval_skill": "judge", "eval_prompt": "x"}}}
    with pytest.raises(ValueError, match="both 'eval_skill' and 'eval_prompt'"):
        resolve_pipeline(config, str(tmp_path))


def test_eval_skill_resolves_into_gate_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    _write_skill(tmp_path, "judge", "verdict {prev_output}\n")
    config = {"phases": {"Code Quality": {"eval_skill": "judge"}}}
    stages = {s.name: s for s in resolve_pipeline(config, str(tmp_path))}
    assert stages["Code Quality"].eval_prompt_template == "verdict {prev_output}\n"


def test_leftover_table_for_dropped_phase_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    config = {
        "pipeline": ["Planning", "Documentation"],
        "phases": {"Tests & Validation": {"provider": "gemini"}},
    }
    stages = resolve_pipeline(config, str(tmp_path))  # must not raise
    assert [s.name for s in stages] == ["Planning", "Documentation"]
