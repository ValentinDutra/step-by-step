"""Skill resolution and prompt rendering.

A skill is a folder containing ``SKILL.md`` (the Claude Code skill convention),
referenced by name and resolved across a project dir and a user dir — mirroring
the config precedence in ``app/config.py``.
"""

import os
import re
from pathlib import Path

_TOKEN = re.compile(r"\{(prompt|prev_output|iteration_context)\}")


def _xdg_step_by_step_dir() -> Path:
    """The user-level ``step-by-step`` config dir (same base as the config)."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "step-by-step"


def skill_dirs(repo_dir: str) -> list[Path]:
    """Skill search dirs, in precedence order (project first, then user)."""
    return [
        Path(repo_dir) / ".step-by-step" / "skills",
        _xdg_step_by_step_dir() / "skills",
    ]


def strip_frontmatter(text: str) -> str:
    """Drop a leading ``---`` YAML frontmatter block if present."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[index + 1:]).lstrip("\n")
    return text


def load_skill(name: str, repo_dir: str) -> str:
    """Return the frontmatter-stripped body of the first ``<dir>/<name>/SKILL.md``.

    Raises ``ValueError`` listing the searched paths when no skill is found.
    """
    searched: list[str] = []
    for directory in skill_dirs(repo_dir):
        candidate = directory / name / "SKILL.md"
        searched.append(str(candidate))
        if candidate.is_file():
            return strip_frontmatter(candidate.read_text())
    raise ValueError(
        f"Skill '{name}' not found. Searched: {', '.join(searched)}"
    )


def render_prompt(
    template: str, prompt: str, prev_output: str, iteration_context: str = ""
) -> str:
    """Substitute the ``{prompt}`` / ``{prev_output}`` / ``{iteration_context}``
    tokens in one pass, leaving any other literal braces untouched."""
    values = {
        "prompt": prompt,
        "prev_output": prev_output,
        "iteration_context": iteration_context,
    }
    return _TOKEN.sub(lambda match: values[match.group(1)], template)
