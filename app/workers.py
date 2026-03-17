"""Parallel worker execution and resource-aware concurrency control."""

import asyncio
import time

import psutil

from app.models import WorkerResult, Task


class ResourceAwareSemaphore:
    """TCP-style flow control driven purely by available RAM.

    Workers start only when RAM is below *max_ram_pct*.  Starts are
    serialized by an internal lock so each new process has time to appear
    in OS memory stats before the next candidate is evaluated.

    After the start delay we re-check RAM (double-check pattern): if the
    new process already pushed usage above the threshold we keep waiting,
    preventing cascading over-allocation with no hard worker cap.
    """

    def __init__(
        self,
        max_ram_pct: float = 75.0,
        poll_interval: float = 2.0,
        start_delay: float = 3.0,
    ) -> None:
        self._max_ram_pct = max_ram_pct
        self._poll_interval = poll_interval
        self._start_delay = start_delay
        self._start_lock = asyncio.Lock()

    def _ram_pct(self) -> float:
        return psutil.virtual_memory().percent

    async def __aenter__(self) -> "ResourceAwareSemaphore":
        async with self._start_lock:
            while True:
                if self._ram_pct() < self._max_ram_pct:
                    await asyncio.sleep(self._start_delay)
                    if self._ram_pct() < self._max_ram_pct:
                        return self
                await asyncio.sleep(self._poll_interval)

    async def __aexit__(self, *_: object) -> None:
        pass  # RAM is reclaimed by the OS when the subprocess exits


async def run_worker(
    task: Task,
    worker_prompt: str,
    working_dir: str,
    on_start=None,
    on_complete=None,
    on_stream=None,
) -> WorkerResult:
    """Run a single worker agent on a subtask."""
    from app.claude import call_claude

    start = time.time()
    task.status = "running"
    if on_start:
        on_start(task)

    success, output, _ = await call_claude(worker_prompt, working_dir, on_stream=on_stream)
    elapsed = time.time() - start

    if success:
        task.status = "completed"
        task.output = output
        task.elapsed = elapsed
        result = WorkerResult(
            task_id=task.id, success=True, output=output, elapsed=elapsed
        )
    else:
        task.status = "failed"
        task.error = output
        task.elapsed = elapsed
        result = WorkerResult(
            task_id=task.id, success=False, output="", elapsed=elapsed, error=output
        )

    if on_complete:
        on_complete(task, result)
    return result


async def run_workers_parallel(
    tasks: list[Task],
    worker_prompts: list[str],
    working_dir: str,
    max_ram_pct: float = 75.0,
    on_start=None,
    on_complete=None,
    on_stream=None,
) -> list[WorkerResult]:
    """Run multiple worker agents in parallel, throttled by available RAM."""
    semaphore = ResourceAwareSemaphore(max_ram_pct=max_ram_pct)

    async def limited_worker(task, prompt):
        worker_stream = None
        if on_stream:

            def worker_stream(chunk, _task=task):
                on_stream(chunk, _task.id)

        async with semaphore:
            return await run_worker(
                task,
                prompt,
                working_dir,
                on_start=on_start,
                on_complete=on_complete,
                on_stream=worker_stream,
            )

    results = await asyncio.gather(
        *[limited_worker(t, p) for t, p in zip(tasks, worker_prompts)]
    )
    return list(results)


def aggregate_results(results: list[WorkerResult]) -> str:
    """Combine outputs from multiple workers into a unified output."""
    parts = []
    for r in results:
        if r.success and r.output:
            parts.append(f"## Worker {r.task_id} Output\n\n{r.output}")
    return "\n\n---\n\n".join(parts)
