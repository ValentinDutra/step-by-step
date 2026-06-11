"""Persistent per-run artifacts: prompt, full stage outputs, and run stats."""

import json
import re
from datetime import datetime
from pathlib import Path

from app.models import PipelineStats
from app.stages import Stage


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "stage"


class RunArtifacts:
    """Writes one directory per pipeline run under ``<repo>/<base_dir>/``."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir

    @classmethod
    def start(cls, repo_dir: str, base_dir: str, prompt: str) -> "RunArtifacts":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(repo_dir) / base_dir
        base.mkdir(parents=True, exist_ok=True)
        run_dir = base / timestamp
        suffix = 2
        while True:
            try:
                run_dir.mkdir(exist_ok=False)
                break
            except FileExistsError:
                run_dir = base / f"{timestamp}-{suffix}"
                suffix += 1
        (run_dir / "prompt.txt").write_text(prompt)
        return cls(run_dir)

    def record_stage(self, index: int, stage: Stage) -> None:
        base_name = f"{index + 1:02d}-{_slugify(stage.name)}"
        path = self.run_dir / f"{base_name}.md"
        attempt = 2
        while path.exists():
            path = self.run_dir / f"{base_name}-{attempt}.md"
            attempt += 1
        header = (
            f"# {stage.name}\n\n"
            f"- provider: {stage.provider_name}\n"
            f"- model: {stage.model or '(default)'}\n"
            f"- status: {stage.status.value}\n"
            f"- elapsed: {stage.elapsed:.1f}s\n\n"
        )
        body = stage.output or stage.error or ""
        path.write_text(header + body)

    def finish(self, stats: PipelineStats, failed: bool) -> None:
        payload = {
            "total_calls": stats.total_calls,
            "total_cost_usd": stats.total_cost_usd,
            "calls_without_cost": stats.calls_without_cost,
            "total_stage_time": stats.total_stage_time,
            "failed": failed,
        }
        (self.run_dir / "run.json").write_text(json.dumps(payload, indent=2))
