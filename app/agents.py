"""Manager agent: task decomposition."""

import json

from app.claude import call_claude
from app.models import Task


async def decompose_task(prompt: str, plan: str, working_dir: str) -> list[Task]:
    """Manager agent: decompose a plan into independent parallel subtasks."""
    decompose_prompt = (
        "You are a task decomposition agent. Given a plan, break it into independent subtasks "
        "that can be worked on IN PARALLEL by different engineers.\n\n"
        f"ORIGINAL TASK: {prompt}\n\n"
        f"PLAN:\n{plan}\n\n"
        "Output a JSON array of subtasks. Each subtask should have:\n"
        '- "id": sequential integer starting at 1\n'
        '- "description": what to implement (be specific and self-contained, include enough context)\n'
        '- "files": list of files this subtask will create or modify\n\n'
        "Rules:\n"
        "- Each subtask must be independent enough to work on in parallel\n"
        "- Include enough context in each description so a worker can act without seeing other subtasks\n"
        "- Create as many subtasks as the complexity genuinely requires — no artificial limit\n"
        "- If the task is simple and cannot be split, return a single subtask\n"
        "- Output ONLY the JSON array, no markdown fences or other text\n"
    )

    success, output, _ = await call_claude(decompose_prompt, working_dir)
    if not success:
        return [Task(id=1, description=prompt)]

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
