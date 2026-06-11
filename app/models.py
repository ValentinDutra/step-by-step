"""Shared data models for the multi-agent pipeline."""

import time
from dataclasses import dataclass, field
from enum import Enum


class AgentRole(Enum):
    MANAGER = "manager"
    WORKER = "worker"


@dataclass
class Task:
    id: int
    description: str
    files: list[str] = field(default_factory=list)
    status: str = "pending"
    output: str = ""
    elapsed: float = 0.0
    error: str = ""


@dataclass
class WorkerResult:
    task_id: int
    success: bool
    output: str
    elapsed: float
    error: str = ""


@dataclass
class PipelineStats:
    total_cost_usd: float = 0.0
    total_calls: int = 0
    calls_without_cost: int = 0
    total_stage_time: float = 0.0
    start_time: float = 0.0

    def reset(self):
        self.total_cost_usd = 0.0
        self.total_calls = 0
        self.calls_without_cost = 0
        self.total_stage_time = 0.0
        self.start_time = time.time()

    def add_call(self, cost_usd: float | None):
        self.total_calls += 1
        if cost_usd is None:
            self.calls_without_cost += 1
        else:
            self.total_cost_usd += cost_usd

    def add_stage_time(self, elapsed: float):
        self.total_stage_time += elapsed

    @property
    def elapsed(self) -> float:
        if self.start_time == 0.0:
            return 0.0
        return time.time() - self.start_time

    @staticmethod
    def _fmt(secs: float) -> str:
        s = int(secs)
        if s < 60:
            return f"{s}s"
        m, s = divmod(s, 60)
        return f"{m}m {s}s"

    def format_elapsed(self) -> str:
        return self._fmt(self.elapsed)

    def format_stage_time(self) -> str:
        return self._fmt(self.total_stage_time)

    def format_cost(self) -> str:
        base = f"${self.total_cost_usd:.4f}"
        if self.calls_without_cost:
            return f"{base} (+{self.calls_without_cost} n/a)"
        return base


def filter_tasks(tasks: list[Task], selected_ids: list[int]) -> list[Task]:
    """Keep only the tasks whose id is in ``selected_ids``, preserving order."""
    selected = set(selected_ids)
    return [task for task in tasks if task.id in selected]


def cost_cap_exceeded(stats: PipelineStats, max_cost_usd: float | None) -> bool:
    """True when a configured cost cap exists and accumulated cost reached it."""
    return max_cost_usd is not None and stats.total_cost_usd >= max_cost_usd


pipeline_stats = PipelineStats()
