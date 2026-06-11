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


def provider_for(name: str, model: str) -> LLMProvider:
    """Build the provider for ``name``, or raise ``ValueError`` if unknown."""
    cls = _PROVIDERS.get(name)
    if cls is None:
        valid = ", ".join(sorted(_PROVIDERS))
        raise ValueError(f"Unknown provider '{name}'. Valid providers: {valid}")
    return cls(model)


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
        resolved[phase_name] = (provider_for(name, model), model)
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

    phases = config.get("phases", {})
    registry = {stage.name: stage for stage in STAGES}
    names = config.get("pipeline") or [stage.name for stage in STAGES]

    stages: list[Stage] = []
    for name in names:
        entry = phases.get(name, {})
        provider_name = entry.get("provider", default_provider)
        model = entry.get("model", default_model)
        provider = provider_for(provider_name, model)

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
                max_iterations=entry.get("max_iterations", 3),
            )
        )

    return stages


def preflight(resolved: dict[str, tuple[LLMProvider, str]]) -> list[str]:
    """Return install-hint messages for any referenced provider binary missing
    from PATH. Empty list means all required CLIs are available."""
    missing = []
    referenced = {provider.name for provider, _ in resolved.values()}
    for name in sorted(referenced):
        if shutil.which(_BINARIES[name]) is None:
            missing.append(f"'{_BINARIES[name]}' not found. Install: {_INSTALL_HINTS[name]}")
    return missing
