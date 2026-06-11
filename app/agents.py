"""Manager agent: task decomposition."""

import json

from app.models import Task
from app.prompts import DECOMPOSITION
from app.skills import render_prompt


async def decompose_task(
    prompt: str, plan: str, working_dir: str, provider, template: str = ""
) -> list[Task]:
    """Manager agent: decompose a plan into independent parallel subtasks.

    ``template`` overrides the built-in prompt (config ``skill``/``prompt`` keys
    on the decompose phase); it must keep the JSON-array output contract.
    """
    decompose_prompt = render_prompt(template or DECOMPOSITION, prompt, plan)

    result = await provider.run(decompose_prompt, working_dir)
    if not result.success:
        return [Task(id=1, description=prompt)]

    output = result.output
    try:
        text = output.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        tasks_data = json.loads(text)
        return [
            Task(id=t["id"], description=t["description"], files=t.get("files", []))
            for t in tasks_data
        ]
    except (json.JSONDecodeError, KeyError, TypeError):
        return [Task(id=1, description=prompt)]
