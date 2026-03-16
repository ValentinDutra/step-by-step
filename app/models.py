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
    total_stage_time: float = 0.0
    start_time: float = 0.0

    def reset(self):
        self.total_cost_usd = 0.0
        self.total_calls = 0
        self.total_stage_time = 0.0
        self.start_time = time.time()

    def add_call(self, cost_usd: float):
        self.total_cost_usd += cost_usd
        self.total_calls += 1

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


pipeline_stats = PipelineStats()
