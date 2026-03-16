"""Multi-agent orchestration: Claude invocation and worker coordination."""

import asyncio
import json
import time

from app.models import Task, WorkerResult, pipeline_stats


async def call_claude(
    prompt: str,
    working_dir: str,
    on_stream=None,
) -> tuple[bool, str, float]:
    """Call Claude CLI and return (success, output, cost_usd).

    Streams output chunks to on_stream(chunk: str) if provided.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "--output-format", "stream-json",
            "--verbose",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        proc.stdin.write(prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()

        final_output = ""
        cost_usd = 0.0

        buf = b""
        while True:
            raw_chunk = await proc.stdout.read(65536)
            if not raw_chunk:
                break
            buf += raw_chunk
            while b"\n" in buf:
                raw_line, buf = buf.split(b"\n", 1)
                line = raw_line.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    etype = event.get("type")
                    if etype == "assistant" and on_stream:
                        for block in event.get("message", {}).get("content", []):
                            if block.get("type") == "text":
                                chunk = block["text"]
                                if asyncio.iscoroutinefunction(on_stream):
                                    await on_stream(chunk)
                                else:
                                    on_stream(chunk)
                    elif etype == "result":
                        final_output = event.get("result", "")
                        cost_usd = float(event.get("cost_usd") or 0.0)
                        if event.get("subtype") == "error" or event.get("is_error"):
                            await proc.wait()
                            pipeline_stats.add_call(cost_usd)
                            return False, final_output or "Claude returned an error", cost_usd
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

        stderr_data = await proc.stderr.read()
        await proc.wait()

        if proc.returncode != 0 and not final_output:
            err = stderr_data.decode().strip() or f"Exit code {proc.returncode}"
            return False, err, 0.0

        pipeline_stats.add_call(cost_usd)
        return True, final_output, cost_usd

    except FileNotFoundError:
        return False, "'claude' CLI not found. Install: npm install -g @anthropic-ai/claude-code", 0.0
    except Exception as e:
        return False, str(e), 0.0


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
        "- Aim for 2-5 subtasks depending on complexity\n"
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


async def run_worker(
    task: Task,
    worker_prompt: str,
    working_dir: str,
    on_start=None,
    on_complete=None,
    on_stream=None,
) -> WorkerResult:
    """Run a single worker agent on a subtask."""
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
        result = WorkerResult(task_id=task.id, success=True, output=output, elapsed=elapsed)
    else:
        task.status = "failed"
        task.error = output
        task.elapsed = elapsed
        result = WorkerResult(task_id=task.id, success=False, output="", elapsed=elapsed, error=output)

    if on_complete:
        on_complete(task, result)
    return result


async def run_workers_parallel(
    tasks: list[Task],
    worker_prompts: list[str],
    working_dir: str,
    max_concurrent: int = 4,
    on_start=None,
    on_complete=None,
    on_stream=None,
) -> list[WorkerResult]:
    """Run multiple worker agents in parallel with concurrency limit."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def limited_worker(task, prompt):
        worker_stream = None
        if on_stream:
            def worker_stream(chunk, _task=task):
                on_stream(chunk, _task.id)
        async with semaphore:
            return await run_worker(
                task, prompt, working_dir,
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
