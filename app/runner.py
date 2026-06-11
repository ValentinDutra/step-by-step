"""Pipeline orchestration mixin for PipelineApp.

Requires the host class to define:
  - self.working_dir: str
  - self.running: reactive[bool]
  - self._stage_outputs: dict[str, str]
  - self._last_prompt: str
  - self._last_decomposed_tasks: list[Task]
  - self._log_buffer: list[str]
  - self._write_log(text: str)
  - self._clear_stream()
  - self._set_stream_header(text: str)
  - self._append_stream(chunk: str, worker_id: int | None)
  - self.query_one(selector, widget_type)
  - self.query(selector)
"""

from textual import work
from textual.widgets import Label, RichLog, TextArea

from app.agents import decompose_task
from app.evaluation import evaluate_should_iterate
from app.git import create_branch, run_commit_pr_stage
from app.config import (
    load_config,
    resolve_limits,
    resolve_pipeline,
    provider_for,
    preflight,
)
from app.models import Task, pipeline_stats
from app.pipeline import run_stage, run_stage_parallel
from app.pipeline_graph import gate_loopback_target, rerun_order, stage_prev
from app.stages import StageStatus
from app.widgets import StagePill


class PipelineRunnerMixin:
    """Mixin providing run_pipeline and rerun_from_stage workers."""

    def _resolve_or_report(self, stats_bar, prompt_input):
        """Resolve the configured pipeline, or report an invalid config and abort.

        Returns the resolved ``list[Stage]`` on success (also setting
        ``self._default_provider`` from ``[defaults]``), or ``None`` after
        rendering the error (caller should return).
        """
        try:
            config = load_config(self.working_dir, getattr(self, "config_path", ""))
            stages = resolve_pipeline(config, self.working_dir)
            self._limits = resolve_limits(config)
            defaults = config.get("defaults", {})
            self._default_provider = provider_for(
                defaults.get("provider", "claude"),
                defaults.get("model", ""),
                timeout_seconds=self._limits.provider_timeout_seconds,
            )
            return stages
        except ValueError as exc:
            self._write_log(f"[red]✗ Config error:[/red] {exc}")
            stats_bar.update("Config error")
            stats_bar.remove_class("working")
            stats_bar.add_class("error")
            prompt_input.disabled = False
            self.running = False
            return None

    @work(exclusive=True)
    async def run_pipeline(self, prompt: str):
        self.running = True
        stats_bar = self.query_one("#stats-bar", Label)
        prompt_input = self.query_one("#prompt-input", TextArea)

        stats_bar.remove_class("success", "error")
        stats_bar.add_class("working")
        prompt_input.disabled = True

        pipeline_stats.reset()

        stages = self._resolve_or_report(stats_bar, prompt_input)
        if stages is None:
            return

        missing = preflight({s.name: (s.provider, s.model) for s in stages})
        if missing:
            for message in missing:
                self._write_log(f"[red]✗ {message}[/red]")
            stats_bar.update("Missing provider CLI")
            stats_bar.remove_class("working")
            stats_bar.add_class("error")
            prompt_input.disabled = False
            self.running = False
            return

        pills = list(self.query(StagePill))
        for pill in pills:
            pill.update_status(StageStatus.PENDING)
            pill.remove_class("pill-rerunnable")

        self._last_prompt = prompt
        self._stage_outputs.clear()
        self._last_decomposed_tasks = []

        self.query_one("#log-container", RichLog).clear()
        self._log_buffer.clear()
        self._clear_stream()
        self._set_stream_header("Pipeline started…")
        self._write_log(f"[bold]Pipeline started:[/bold] {prompt}\n")

        # ── Branch creation (only when a commit_pr phase is present) ──────
        commit_stage = next((s for s in stages if s.kind == "commit_pr"), None)
        if commit_stage is not None:
            self._write_log("[bold yellow]▶ Creating branch…[/bold yellow]")
            branch_name = await create_branch(
                prompt,
                self.working_dir,
                commit_stage.provider,
                on_log=lambda msg: self._write_log(f"  [dim]{msg}[/dim]"),
            )
            if branch_name:
                self._write_log(f"[green]✓ Branch:[/green] [bold]{branch_name}[/bold]\n")
            else:
                self._write_log("[yellow]⚠ Branch creation skipped[/yellow]\n")

        failed = await self._run_dispatch_loop(stages, pills, prompt, stats_bar)

        # ── Final status ─────────────────────────────────────────────────
        stats = pipeline_stats
        final_stats = (
            f"Calls: {stats.total_calls} | Cost: {stats.format_cost()} "
            f"| Time: {stats.format_stage_time()}"
        )

        stats_bar.remove_class("working")
        if not failed:
            stats_bar.add_class("success")
            stats_bar.update(f"✓ Done — {final_stats}")
            self._write_log("\n[bold green]All stages completed![/bold green]")
            self._set_stream_header(f"Done — {final_stats}")
        else:
            stats_bar.add_class("error")
            stats_bar.update(f"✗ Failed — {final_stats}")

        prompt_input.disabled = False
        self.running = False
        for pill in self.query(StagePill):
            pill.add_class("pill-rerunnable")

    async def _run_dispatch_loop(self, stages, pills, prompt, stats_bar) -> bool:
        """Run the resolved pipeline, dispatching each stage by ``kind``.

        Threads each stage's output to the next, re-runs a ``gate``'s loop-back
        range (nearest preceding ``decompose`` .. gate) when it asks for another
        iteration — capped by the gate's ``max_iterations`` — and returns
        ``True`` if any stage failed.
        """
        outputs: list[str] = [""] * len(stages)
        decomposed_tasks: list[Task] = []
        gate_iterations: dict[int, int] = {}
        feedback = ""
        index = 0

        while index < len(stages):
            stage = stages[index]
            pill = pills[index] if index < len(pills) else None
            prev_output = outputs[index - 1] if index > 0 else ""
            iteration_context = "" if stage.kind == "gate" else feedback

            if pill is not None:
                pill.update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header(stage.name)
            self._write_log(f"\n[bold yellow]▶ {stage.name}[/bold yellow]")

            def on_stream(chunk, _self=self):
                _self._append_stream(chunk)

            # ── decompose: split the plan into parallel subtasks ─────────
            if stage.kind == "decompose":
                plan_arg = prev_output
                if feedback:
                    plan_arg = f"{prev_output}\n\n{feedback}" if prev_output else feedback
                stage.start()
                decomposed_tasks = await decompose_task(
                    prompt, plan_arg, self.working_dir, stage.provider
                )
                stage.complete(f"Decomposed into {len(decomposed_tasks)} subtasks")
                self._last_decomposed_tasks = decomposed_tasks
                # A decompose produces tasks (a side channel), not prose. Forward
                # the incoming plan so the next stage's prev_output stays the plan,
                # not the "Decomposed into N subtasks" status line.
                outputs[index] = prev_output
                self._stage_outputs[stage.name] = prev_output
                if pill is not None:
                    pill.update_status(StageStatus.COMPLETED, stage.elapsed)
                self._write_log(
                    f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)} "
                    f"→ [bold]{len(decomposed_tasks)} subtask(s)[/bold]"
                )
                for task in decomposed_tasks:
                    files = ", ".join(task.files) if task.files else "—"
                    self._write_log(
                        f"  [dim]#{task.id}: {task.description[:80]}  ({files})[/dim]"
                    )
                index += 1
                continue

            # ── run the stage by kind ────────────────────────────────────
            if stage.kind == "parallel":
                def on_worker_complete(task, result, _self=self):
                    color = "green" if result.success else "red"
                    status_str = "completed" if result.success else "failed"
                    _self._write_log(
                        f"  [{color}]W{task.id} {status_str}[/{color}] "
                        f"[dim]{StagePill._fmt(task.elapsed)}[/dim]"
                    )

                def on_parallel_stream(chunk, worker_id, _self=self):
                    _self._append_stream(chunk, worker_id)

                self._set_stream_header(
                    f"{stage.name} — {len(decomposed_tasks)} workers"
                )
                output = await run_stage_parallel(
                    stage, decomposed_tasks, prompt, prev_output, self.working_dir,
                    iteration_context=iteration_context,
                    on_worker_complete=on_worker_complete,
                    on_stream=on_parallel_stream,
                )
            elif stage.kind == "commit_pr":
                def on_pr_log(msg, _self=self):
                    _self._write_log(f"  [dim]{msg}[/dim]")

                output = await run_commit_pr_stage(
                    stage, prompt, prev_output, self.working_dir,
                    on_stream=on_stream, on_log=on_pr_log,
                )
            else:  # simple or gate
                output = await run_stage(
                    stage, prompt, prev_output, self.working_dir,
                    iteration_context=iteration_context, on_stream=on_stream,
                )

            if pill is not None:
                pill.update_status(stage.status, stage.elapsed)

            if stage.status != StageStatus.COMPLETED:
                self._write_log(f"[red]✗ {stage.name} failed:[/red] {stage.error}")
                stats_bar.remove_class("working")
                stats_bar.update(f"Failed at: {stage.name}")
                return True

            outputs[index] = output
            self._stage_outputs[stage.name] = output
            self._write_log(
                f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)}"
            )
            preview = output[:300].strip()
            if preview and stage.kind != "commit_pr":
                self._write_log(f"[dim]{preview}[/dim]\n")

            # ── gate: evaluate, and loop back to the nearest decompose ───
            if stage.kind == "gate":
                should_loop = await evaluate_should_iterate(
                    output, self.working_dir, self._default_provider
                )
                target = gate_loopback_target(stages, index)
                count = gate_iterations.get(index, 0)
                if should_loop and target is not None and count < stage.max_iterations:
                    gate_iterations[index] = count + 1
                    feedback = (
                        f"Code Quality & Technical Debt review #{count + 1} found issues "
                        f"that require a full re-implementation pass:\n{output[:3000]}\n\n"
                        "Fix ALL reported quality and technical debt issues in the new implementation."
                    )
                    self._write_log(
                        f"\n[bold yellow]Quality/debt issues — re-running from "
                        f"{stages[target].name} (attempt {count + 1})[/bold yellow]"
                    )
                    for reset_index in range(target, index + 1):
                        if reset_index < len(pills):
                            pills[reset_index].update_status(StageStatus.PENDING)
                    index = target
                    continue
                if should_loop and count >= stage.max_iterations:
                    self._write_log(
                        f"\n[yellow]Gate reached max_iterations "
                        f"({stage.max_iterations}); proceeding[/yellow]"
                    )
                feedback = ""

            index += 1

        return False

    @work(exclusive=True)
    async def rerun_from_stage(self, from_stage_name: str) -> None:
        self.running = True
        stats_bar = self.query_one("#stats-bar", Label)
        prompt_input = self.query_one("#prompt-input", TextArea)
        pills = list(self.query(StagePill))

        stats_bar.remove_class("success", "error")
        stats_bar.add_class("working")
        prompt_input.disabled = True
        pipeline_stats.reset()

        for pill in pills:
            pill.remove_class("pill-rerunnable")

        stages = self._resolve_or_report(stats_bar, prompt_input)
        if stages is None:
            return

        order = rerun_order(stages)
        if from_stage_name not in order:
            self._write_log(
                f"[red]✗ '{from_stage_name}' is not in the current pipeline[/red]"
            )
            stats_bar.remove_class("working")
            stats_bar.add_class("error")
            stats_bar.update("Stage not in pipeline")
            prompt_input.disabled = False
            self.running = False
            for pill in self.query(StagePill):
                pill.add_class("pill-rerunnable")
            return

        from_idx = order.index(from_stage_name)
        for pill in pills[from_idx:]:
            pill.update_status(StageStatus.PENDING)

        prev_name = stage_prev(stages).get(from_stage_name)
        prev_output = self._stage_outputs.get(prev_name, "") if prev_name else ""
        prompt = self._last_prompt

        first_decompose = next(
            (i for i, s in enumerate(stages) if s.kind == "decompose"), None
        )
        decomposed_tasks = (
            self._last_decomposed_tasks
            if first_decompose is not None and from_idx > first_decompose
            else []
        )
        failed = False

        self._write_log(
            f"\n[bold cyan]━━━ Re-running from: {from_stage_name} ━━━[/bold cyan]\n"
            f"[dim]Using context from previous run[/dim]"
        )

        for index in range(from_idx, len(stages)):
            stage = stages[index]
            pill = pills[index] if index < len(pills) else None
            if pill is not None:
                pill.update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header(stage.name)

            def on_stream(chunk, _self=self):
                _self._append_stream(chunk)

            if stage.kind == "decompose":
                self._write_log(
                    f"\n[bold yellow]▶ {stage.name}[/bold yellow] "
                    f"[dim](manager splitting tasks)[/dim]"
                )
                stage.start()
                decomposed_tasks = await decompose_task(
                    prompt, prev_output, self.working_dir, stage.provider
                )
                stage.complete(f"Decomposed into {len(decomposed_tasks)} subtasks")
                self._last_decomposed_tasks = decomposed_tasks
                if pill is not None:
                    pill.update_status(StageStatus.COMPLETED, stage.elapsed)
                self._write_log(
                    f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)} "
                    f"→ [bold]{len(decomposed_tasks)} subtask(s)[/bold]"
                )
                for task in decomposed_tasks:
                    files = ", ".join(task.files) if task.files else "—"
                    self._write_log(
                        f"  [dim]#{task.id}: {task.description[:80]}  ({files})[/dim]"
                    )
                # Forward the plan unchanged; the decompose's product is the task
                # list, not the "Decomposed into N subtasks" status line.
                self._stage_outputs[stage.name] = prev_output
                continue

            if stage.kind == "parallel":
                def on_worker_complete(task, result, _self=self):
                    color = "green" if result.success else "red"
                    status_str = "completed" if result.success else "failed"
                    _self._write_log(
                        f"  [{color}]W{task.id} {status_str}[/{color}] "
                        f"[dim]{StagePill._fmt(task.elapsed)}[/dim]"
                    )

                def on_parallel_stream(chunk, worker_id, _self=self):
                    _self._append_stream(chunk, worker_id)

                self._set_stream_header(
                    f"{stage.name} — {len(decomposed_tasks)} workers"
                )
                self._write_log(
                    f"\n[bold yellow]▶ {stage.name}[/bold yellow] "
                    f"[dim]({len(decomposed_tasks)} parallel workers)[/dim]"
                )
                output = await run_stage_parallel(
                    stage, decomposed_tasks, prompt, prev_output, self.working_dir,
                    on_worker_complete=on_worker_complete,
                    on_stream=on_parallel_stream,
                )
            elif stage.kind == "commit_pr":
                self._write_log(f"\n[bold yellow]▶ {stage.name}[/bold yellow]")

                def on_pr_log(msg, _self=self):
                    _self._write_log(f"  [dim]{msg}[/dim]")

                output = await run_commit_pr_stage(
                    stage, prompt, prev_output, self.working_dir,
                    on_stream=on_stream, on_log=on_pr_log,
                )
            else:  # simple or gate (single pass on re-run)
                self._write_log(f"\n[bold yellow]▶ {stage.name}[/bold yellow]")
                output = await run_stage(
                    stage, prompt, prev_output, self.working_dir, on_stream=on_stream
                )

            if pill is not None:
                pill.update_status(stage.status, stage.elapsed)
            if stage.status == StageStatus.COMPLETED:
                self._write_log(
                    f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)}"
                )
                preview = output[:300].strip()
                if preview and stage.kind != "commit_pr":
                    self._write_log(f"[dim]{preview}[/dim]\n")
                self._stage_outputs[stage.name] = output
                prev_output = output
            else:
                self._write_log(f"[red]✗ {stage.name} failed:[/red] {stage.error}")
                failed = True
                break

        stats = pipeline_stats
        final_stats = (
            f"Calls: {stats.total_calls} | Cost: {stats.format_cost()} "
            f"| Time: {stats.format_stage_time()}"
        )

        stats_bar.remove_class("working")
        if not failed:
            stats_bar.add_class("success")
            stats_bar.update(f"✓ Done — {final_stats}")
            self._write_log("\n[bold green]Re-run complete![/bold green]")
            self._set_stream_header(f"Done — {final_stats}")
        else:
            stats_bar.add_class("error")
            stats_bar.update(f"✗ Failed — {final_stats}")

        prompt_input.disabled = False
        self.running = False
        for pill in self.query(StagePill):
            pill.add_class("pill-rerunnable")
