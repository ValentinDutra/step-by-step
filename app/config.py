"""Per-phase provider configuration loaded from TOML.

Precedence (first existing wins):
    explicit ``--config PATH``
    <repo>/step-by-step.toml
    $XDG_CONFIG_HOME/step-by-step/config.toml   (default ~/.config/...)
    built-in all-Claude default
"""

import os
import shutil
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from app.providers.base import LLMProvider
from app.providers.claude import ClaudeProvider
from app.providers.codex import CodexProvider
from app.providers.gemini import GeminiProvider
from app.skills import load_skill
from app.stages import STAGES, Stage

_PROVIDERS = {
    "claude": ClaudeProvider,
    "codex": CodexProvider,
    "gemini": GeminiProvider,
}

_BINARIES = {"claude": "claude", "codex": "codex", "gemini": "gemini"}

_INSTALL_HINTS = {
    "claude": "npm install -g @anthropic-ai/claude-code",
    "codex": "npm install -g @openai/codex",
    "gemini": "npm install -g @google/gemini-cli",
}

_DEFAULT_CONFIG = {"defaults": {"provider": "claude", "model": ""}}


@dataclass(frozen=True)
class Limits:
    provider_timeout_seconds: int = 600
    max_ram_pct: float = 75.0
    max_cost_usd: float | None = None
    default_max_iterations: int = 3
    prev_output_chars: int = 8000
    worker_prev_output_chars: int = 6000
    evaluation_output_chars: int = 4000
    commit_context_chars: int = 3000
    diff_stat_chars: int = 1500
    feedback_chars: int = 3000


_FLOAT_LIMIT_KEYS = {"max_ram_pct", "max_cost_usd"}


def _is_positive_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
    )


def resolve_limits(config: dict) -> Limits:
    """Build :class:`Limits` from the optional ``[limits]`` section.

    Unknown keys and out-of-range values fail fast so a typo never silently
    falls back to a default.
    """
    section = config.get("limits", {})
    valid_keys = [field.name for field in fields(Limits)]
    unknown = sorted(set(section) - set(valid_keys))
    if unknown:
        raise ValueError(
            f"Unknown key(s) in [limits]: {', '.join(unknown)}. "
            f"Valid keys: {', '.join(valid_keys)}"
        )

    resolved: dict = {}
    for key, value in section.items():
        if key in _FLOAT_LIMIT_KEYS:
            if not _is_positive_number(value) or (key == "max_ram_pct" and value > 100):
                expected = "a number in (0, 100]" if key == "max_ram_pct" else "a positive number"
                raise ValueError(f"[limits] {key} must be {expected}, got {value!r}")
            resolved[key] = float(value)
        else:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(
                    f"[limits] {key} must be a positive integer, got {value!r}"
                )
            resolved[key] = value
    return Limits(**resolved)


def provider_for(name: str, model: str, timeout_seconds: int = 600) -> LLMProvider:
    """Build the provider for ``name``, or raise ``ValueError`` if unknown."""
    cls = _PROVIDERS.get(name)
    if cls is None:
        valid = ", ".join(sorted(_PROVIDERS))
        raise ValueError(f"Unknown provider '{name}'. Valid providers: {valid}")
    return cls(model, timeout_seconds=timeout_seconds)


def _user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "step-by-step" / "config.toml"


def load_config(repo_dir: str, explicit_path: str | None = None) -> dict:
    """Return the first existing config in precedence order, else the default."""
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.append(Path(repo_dir) / "step-by-step.toml")
    candidates.append(_user_config_path())
    for path in candidates:
        if path.is_file():
            with open(path, "rb") as handle:
                return tomllib.load(handle)
    return {"defaults": dict(_DEFAULT_CONFIG["defaults"])}


def resolve_providers(
    config: dict, phase_names: list[str]
) -> dict[str, tuple[LLMProvider, str]]:
    """Map each phase to a (provider, model). Fails fast on invalid config."""
    defaults = config.get("defaults", {})
    default_provider = defaults.get("provider", "claude")
    default_model = defaults.get("model", "")
    provider_for(default_provider, default_model)  # validate the default eagerly
    limits = resolve_limits(config)

    phases = config.get("phases", {})
    valid = set(phase_names)
    for phase_name in phases:
        if phase_name not in valid:
            listed = ", ".join(phase_names)
            raise ValueError(
                f"Unknown phase '{phase_name}' in config. Valid phases: {listed}"
            )

    resolved: dict[str, tuple[LLMProvider, str]] = {}
    for phase_name in phase_names:
        entry = phases.get(phase_name, {})
        name = entry.get("provider", default_provider)
        model = entry.get("model", default_model)
        resolved[phase_name] = (
            provider_for(name, model, timeout_seconds=limits.provider_timeout_seconds),
            model,
        )
    return resolved


def resolve_pipeline(config: dict, repo_dir: str) -> list[Stage]:
    """Build the ordered list of stages for the configured pipeline.

    Absent a ``pipeline`` key, the built-in phases run in their default order.
    Each phase's provider/model follows the same precedence as
    ``resolve_providers``; a built-in phase takes its kind/templates from the
    registry, while a custom phase is ``simple`` and supplies its prompt via a
    ``skill`` folder or an inline ``prompt``. Validation lives in
    ``_validate_pipeline``.
    """
    defaults = config.get("defaults", {})
    default_provider = defaults.get("provider", "claude")
    default_model = defaults.get("model", "")
    provider_for(default_provider, default_model)  # validate the default eagerly

    limits = resolve_limits(config)
    phases = config.get("phases", {})
    registry = {stage.name: stage for stage in STAGES}
    if "pipeline" in config:
        names = config["pipeline"]
    else:
        names = [stage.name for stage in STAGES]

    stages: list[Stage] = []
    for name in names:
        entry = phases.get(name, {})
        provider_name = entry.get("provider", default_provider)
        model = entry.get("model", default_model)
        provider = provider_for(
            provider_name, model, timeout_seconds=limits.provider_timeout_seconds
        )

        builtin = registry.get(name)
        if builtin is not None:
            kind = builtin.kind
            prompt_template = builtin.prompt_template
            worker_prompt_template = builtin.worker_prompt_template
            iterable = builtin.iterable
            parallel = builtin.parallel
        else:
            kind = entry.get("kind", "simple")
            prompt_template = ""
            worker_prompt_template = ""
            iterable = False
            parallel = False

        if "skill" in entry:
            prompt_template = load_skill(entry["skill"], repo_dir)
        elif "prompt" in entry:
            prompt_template = entry["prompt"]

        stages.append(
            Stage(
                name=name,
                prompt_template=prompt_template,
                worker_prompt_template=worker_prompt_template,
                iterable=iterable,
                parallel=parallel,
                provider=provider,
                provider_name=provider.name,
                model=model,
                kind=kind,
                max_iterations=entry.get("max_iterations", limits.default_max_iterations),
            )
        )

    _validate_pipeline(stages, phases, registry)
    return stages


def _validate_pipeline(
    stages: list[Stage], phases: dict, registry: dict[str, Stage]
) -> None:
    """Fail-fast structural validation of the resolved pipeline."""
    if not stages:
        raise ValueError("Pipeline is empty; at least one phase is required.")

    names = [stage.name for stage in stages]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(
            f"Duplicate phase name(s) in pipeline: {', '.join(duplicates)}"
        )

    if sum(1 for stage in stages if stage.kind == "commit_pr") > 1:
        raise ValueError(
            "Pipeline has more than one 'commit_pr' phase; at most one is allowed."
        )
    if sum(1 for stage in stages if stage.kind == "gate") > 1:
        raise ValueError(
            "Pipeline has more than one 'gate' phase; at most one is allowed."
        )

    seen_decompose = False
    for stage in stages:
        if stage.kind == "decompose":
            seen_decompose = True
        if stage.kind == "parallel" and not seen_decompose:
            raise ValueError(
                f"Phase '{stage.name}' (parallel) requires a 'decompose' phase before it."
            )

    for stage in stages:
        entry = phases.get(stage.name, {})
        has_skill = "skill" in entry
        has_prompt = "prompt" in entry
        if has_skill and has_prompt:
            raise ValueError(
                f"Phase '{stage.name}' declares both 'skill' and 'prompt'; declare exactly one."
            )
        if stage.name not in registry:  # custom phase
            if stage.kind != "simple":
                raise ValueError(
                    f"Custom phase '{stage.name}' must be kind 'simple', got '{stage.kind}'."
                )
            if not has_skill and not has_prompt:
                raise ValueError(
                    f"Custom phase '{stage.name}' must declare a 'skill' or 'prompt'."
                )


def preflight(resolved: dict[str, tuple[LLMProvider, str]]) -> list[str]:
    """Return install-hint messages for any referenced provider binary missing
    from PATH. Empty list means all required CLIs are available."""
    missing = []
    referenced = {provider.name for provider, _ in resolved.values()}
    for name in sorted(referenced):
        if shutil.which(_BINARIES[name]) is None:
            missing.append(f"'{_BINARIES[name]}' not found. Install: {_INSTALL_HINTS[name]}")
    return missing
