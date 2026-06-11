"""Quality-gate evaluator: decide whether a stage needs another iteration."""

from app.config import Limits
from app.prompts import GATE_EVALUATION
from app.skills import render_prompt


async def evaluate_should_iterate(
    stage_output: str,
    working_dir: str,
    provider,
    limits: Limits = Limits(),
    template: str = "",
) -> bool:
    """Ask the given provider whether the stage output has blocking issues.

    ``template`` overrides the built-in prompt (config ``eval_skill``/``eval_prompt``
    keys on the gate phase); it must keep the yes/no answer contract.
    """
    prompt = render_prompt(
        template or GATE_EVALUATION,
        "",
        stage_output[: limits.evaluation_output_chars],
    )
    result = await provider.run(prompt, working_dir)
    if not result.success:
        return False
    return result.output.strip().lower().startswith("yes")
