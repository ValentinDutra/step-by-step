import pytest

from app.skills import load_skill, render_prompt, strip_frontmatter


def _write_skill(repo, name, body):
    skill_dir = repo / ".step-by-step" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(body)


def test_load_skill_returns_frontmatter_stripped_body(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    _write_skill(
        tmp_path,
        "research",
        "---\ndescription: do research\nmodel: opus\n---\n\nResearch the problem.\n",
    )
    body = load_skill("research", str(tmp_path))
    assert body == "Research the problem.\n"


def test_load_skill_missing_raises_with_searched_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    with pytest.raises(ValueError, match="not found"):
        load_skill("nope", str(tmp_path))


def test_strip_frontmatter_noop_without_block():
    assert strip_frontmatter("no frontmatter here") == "no frontmatter here"


def test_render_prompt_substitutes_tokens_and_keeps_literal_braces():
    template = 'Task: {prompt}\nPrev: {prev_output}\nExample: {"json": 1}'
    rendered = render_prompt(template, "build X", "the plan")
    assert "Task: build X" in rendered
    assert "Prev: the plan" in rendered
    assert '{"json": 1}' in rendered  # untouched literal braces
