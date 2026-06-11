"""Quality-gate evaluator: decide whether a stage needs another iteration."""


async def evaluate_should_iterate(
    stage_output: str, working_dir: str, provider
) -> bool:
    """Ask the given provider whether the stage output has blocking issues."""
    prompt = (
        "You are a quality gate agent. Review the following stage output and decide "
        "whether it contains genuine issues that require another implementation iteration.\n\n"
        "Answer ONLY with 'yes' if there are real issues that need fixing, "
        "or 'no' if the output is satisfactory and the pipeline can proceed.\n\n"
        f"STAGE OUTPUT:\n{stage_output[:4000]}"
    )
    result = await provider.run(prompt, working_dir)
    if not result.success:
        return False
    return result.output.strip().lower().startswith("yes")
