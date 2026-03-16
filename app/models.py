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
    start_time: float = 0.0

    def reset(self):
        self.total_cost_usd = 0.0
        self.total_calls = 0
        self.start_time = time.time()

    def add_call(self, cost_usd: float):
        self.total_cost_usd += cost_usd
        self.total_calls += 1

    @property
    def elapsed(self) -> float:
        if self.start_time == 0.0:
            return 0.0
        return time.time() - self.start_time

    def format_elapsed(self) -> str:
        secs = int(self.elapsed)
        if secs < 60:
            return f"{secs}s"
        m, s = divmod(secs, 60)
        return f"{m}m {s}s"


pipeline_stats = PipelineStats()
