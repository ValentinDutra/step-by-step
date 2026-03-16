"""Pipeline stage runners."""

from app.agents import Task, call_claude, run_workers_parallel, aggregate_results
from app.stages import Stage, StageStatus, MAX_CONCURRENT_WORKERS


async def run_stage(
    stage: Stage,
    prompt: str,
    prev_output: str,
    working_dir: str,
    iteration_context: str = "",
    on_stream=None,
) -> str:
    """Run a single pipeline stage (manager mode — single agent)."""
    stage.start()

    full_prompt = stage.prompt_template.format(
        prompt=prompt,
        prev_output=prev_output[:8000],
        iteration_context=iteration_context,
    )

    success, output, _ = await call_claude(full_prompt, working_dir, on_stream=on_stream)

    if success:
        stage.complete(output)
        return output
    else:
        stage.fail(output)
        return ""


async def run_stage_parallel(
    stage: Stage,
    tasks: list[Task],
    prompt: str,
    prev_output: str,
    working_dir: str,
    iteration_context: str = "",
    on_worker_start=None,
    on_worker_complete=None,
    on_stream=None,
) -> str:
    """Run a pipeline stage in parallel worker mode (fan-out to multiple agents)."""
    stage.start()
    stage.tasks = tasks

    worker_prompts = []
    for task in tasks:
        wp = stage.worker_prompt_template.format(
            prompt=prompt,
            task_description=task.description,
            task_files=", ".join(task.files) if task.files else "as needed",
            prev_output=prev_output[:6000],
            iteration_context=iteration_context,
        )
        worker_prompts.append(wp)

    results = await run_workers_parallel(
        tasks,
        worker_prompts,
        working_dir,
        max_concurrent=MAX_CONCURRENT_WORKERS,
        on_start=on_worker_start,
        on_complete=on_worker_complete,
        on_stream=on_stream,
    )

    failures = [r for r in results if not r.success]
    if failures:
        error_msgs = "; ".join(f"Worker {r.task_id}: {r.error}" for r in failures)
        stage.fail(error_msgs)
        return ""

    output = aggregate_results(results)
    stage.complete(output)
    return output
