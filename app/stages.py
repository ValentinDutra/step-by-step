"""Pipeline stage definitions."""

import time
from dataclasses import dataclass, field
from enum import Enum

from app.models import Task, pipeline_stats
from app.providers.base import LLMProvider
from app.providers.claude import ClaudeProvider
import app.prompts as p


class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Stage:
    name: str
    prompt_template: str
    iterable: bool = False
    parallel: bool = False
    worker_prompt_template: str = ""
    provider: LLMProvider | None = None
    provider_name: str = "claude"
    model: str = ""
    status: StageStatus = StageStatus.PENDING
    elapsed: float = 0.0
    output: str = ""
    error: str = ""
    tasks: list[Task] = field(default_factory=list)
    _start_time: float = 0.0

    def start(self):
        self.status = StageStatus.RUNNING
        self._start_time = time.time()

    def complete(self, output: str):
        self.elapsed = time.time() - self._start_time
        self.output = output
        self.status = StageStatus.COMPLETED
        pipeline_stats.add_stage_time(self.elapsed)

    def fail(self, error: str):
        self.elapsed = time.time() - self._start_time
        self.error = error
        self.status = StageStatus.FAILED


STAGES = [
    Stage(name="Planning",          prompt_template=p.PLANNING),
    Stage(name="Decomposition",     prompt_template=""),
    Stage(name="Implementation",    prompt_template=p.IMPLEMENTATION,
          worker_prompt_template=p.IMPLEMENTATION_WORKER, iterable=True, parallel=True),
    Stage(name="Tests & Validation", prompt_template=p.TESTS,
          worker_prompt_template=p.TESTS_WORKER, iterable=True, parallel=True),
    Stage(name="Code Quality",      prompt_template=p.CODE_QUALITY),
    Stage(name="Documentation",     prompt_template=p.DOCUMENTATION),
    Stage(name="Commit & PR",       prompt_template=p.COMMIT_PR),
]


def create_stages(
    resolved: dict[str, tuple[LLMProvider, str]] | None = None
) -> list[Stage]:
    """Create a fresh set of pipeline stages.

    ``resolved`` maps phase name -> (provider, model). Phases absent from it (or
    when it is ``None``) default to Claude, preserving the original behavior.
    """
    stages = []
    for s in STAGES:
        if resolved and s.name in resolved:
            provider, model = resolved[s.name]
            provider_name = provider.name
        else:
            provider, model, provider_name = ClaudeProvider(), "", "claude"
        stages.append(
            Stage(
                name=s.name,
                prompt_template=s.prompt_template,
                iterable=s.iterable,
                parallel=s.parallel,
                worker_prompt_template=s.worker_prompt_template,
                provider=provider,
                provider_name=provider_name,
                model=model,
            )
        )
    return stages
