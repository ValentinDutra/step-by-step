import asyncio

from app.agents import decompose_task
from app.config import Limits
from app.evaluation import evaluate_should_iterate
from app.providers.base import ProviderResult


class _StubProvider:
    name = "stub"

    def __init__(self, output="[]", success=True):
        self.output = output
        self.success = success
        self.prompts = []

    async def run(self, prompt, working_dir, on_stream=None):
        self.prompts.append(prompt)
        return ProviderResult(self.success, self.output, cost_usd=None)


def test_custom_decompose_template_used_with_substitutions(tmp_path):
    provider = _StubProvider(output='[{"id": 1, "description": "d"}]')
    tasks = asyncio.run(
        decompose_task(
            "my task",
            "the plan",
            str(tmp_path),
            provider,
            template="SPLIT {prompt} USING {prev_output}",
        )
    )
    assert provider.prompts == ["SPLIT my task USING the plan"]
    assert len(tasks) == 1
    assert tasks[0].description == "d"


def test_default_decompose_template_used_when_empty(tmp_path):
    provider = _StubProvider(output='[{"id": 1, "description": "d"}]')
    asyncio.run(decompose_task("my task", "the plan", str(tmp_path), provider))
    rendered = provider.prompts[0]
    assert "ORIGINAL TASK: my task" in rendered
    assert "PLAN:\nthe plan" in rendered
    assert "JSON array" in rendered


def test_custom_eval_template_sent_with_stage_output(tmp_path):
    provider = _StubProvider(output="yes")
    should_iterate = asyncio.run(
        evaluate_should_iterate(
            "the output", str(tmp_path), provider, template="JUDGE: {prev_output}"
        )
    )
    assert provider.prompts == ["JUDGE: the output"]
    assert should_iterate is True


def test_default_eval_template_truncates_stage_output_per_limits(tmp_path):
    provider = _StubProvider(output="no")
    should_iterate = asyncio.run(
        evaluate_should_iterate(
            "x" * 100, str(tmp_path), provider, limits=Limits(evaluation_output_chars=10)
        )
    )
    assert should_iterate is False
    rendered = provider.prompts[0]
    assert "quality gate agent" in rendered
    assert "x" * 10 in rendered
    assert "x" * 11 not in rendered


def test_non_json_output_falls_back_to_single_task(tmp_path):
    provider = _StubProvider(output="not json at all")
    tasks = asyncio.run(decompose_task("my task", "plan", str(tmp_path), provider))
    assert len(tasks) == 1
    assert tasks[0].id == 1
    assert tasks[0].description == "my task"
