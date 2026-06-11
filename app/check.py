"""Config dry-run: validate and print the resolved pipeline without any LLM call."""

from dataclasses import asdict

from app.config import (
    find_config_path,
    load_config,
    preflight,
    resolve_limits,
    resolve_pipeline,
)


def run_check(repo_dir: str, config_path: str = "") -> int:
    """Print config source, resolved pipeline, limits, and preflight results.

    Returns 0 on a valid config (even with missing provider CLIs, which are
    reported), 1 on a validation error.
    """
    source = find_config_path(repo_dir, config_path)
    print(f"Config: {source if source is not None else 'built-in default'}")

    try:
        config = load_config(repo_dir, config_path)
        stages = resolve_pipeline(config, repo_dir)
        limits = resolve_limits(config)
    except ValueError as error:
        print(f"Config error: {error}")
        return 1

    phases = config.get("phases", {})
    print("\nPipeline:")
    for stage in stages:
        entry = phases.get(stage.name, {})
        if "skill" in entry:
            prompt_source = f"skill:{entry['skill']}"
        elif "prompt" in entry:
            prompt_source = "inline"
        else:
            prompt_source = "builtin"
        gate_info = (
            f"  max_iterations={stage.max_iterations}" if stage.kind == "gate" else ""
        )
        model = stage.model or "(default)"
        print(
            f"  {stage.name}  kind={stage.kind}  provider={stage.provider_name}  "
            f"model={model}  prompt={prompt_source}{gate_info}"
        )

    print("\nLimits:")
    for field_name, value in asdict(limits).items():
        print(f"  {field_name} = {value}")

    missing = preflight({stage.name: (stage.provider, stage.model) for stage in stages})
    if missing:
        print("\nPreflight:")
        for message in missing:
            print(f"  ✗ {message}")
    else:
        print("\nPreflight: all provider CLIs found")
    return 0
