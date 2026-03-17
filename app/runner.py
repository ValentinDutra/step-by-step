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
from app.claude import evaluate_should_iterate
from app.git import create_branch, run_commit_pr_stage
from app.models import Task, pipeline_stats
from app.pipeline import run_stage, run_stage_parallel
from app.runner_steps import PipelineStepsMixin
from app.stages import StageStatus, create_stages
from app.widgets import RERUN_ORDER, STAGE_PREV, StagePill


class PipelineRunnerMixin(PipelineStepsMixin):
    """Mixin providing run_pipeline and rerun_from_stage workers."""

    @work(exclusive=True)
    async def run_pipeline(self, prompt: str):
        self.running = True
        stats_bar = self.query_one("#stats-bar", Label)
        prompt_input = self.query_one("#prompt-input", TextArea)

        stats_bar.remove_class("success", "error")
        stats_bar.add_class("working")
        prompt_input.disabled = True

        pipeline_stats.reset()

        stages = create_stages()
        pills = list(self.query(StagePill))
        stage_map = {s.name: (i, s) for i, s in enumerate(stages)}

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

        # ── Branch creation ──────────────────────────────────────────────
        self._write_log("[bold yellow]▶ Creating branch…[/bold yellow]")
        branch_name = await create_branch(
            prompt,
            self.working_dir,
            on_log=lambda msg: self._write_log(f"  [dim]{msg}[/dim]"),
        )
        if branch_name:
            self._write_log(f"[green]✓ Branch:[/green] [bold]{branch_name}[/bold]\n")
        else:
            self._write_log("[yellow]⚠ Branch creation skipped[/yellow]\n")

        failed = False
        decomposed_tasks: list[Task] = []
        prev_output = ""

        # ── Phase 1: Planning (once) ─────────────────────────────────────
        plan_idx, plan_stage = stage_map["Planning"]
        pills[plan_idx].update_status(StageStatus.RUNNING)
        self._clear_stream()
        self._set_stream_header("Planning")
        self._write_log(f"\n[bold yellow]▶ Planning[/bold yellow]")

        def on_plan_stream(chunk, _self=self):
            _self._append_stream(chunk)

        plan_output = await run_stage(
            plan_stage, prompt, "", self.working_dir, on_stream=on_plan_stream
        )
        pills[plan_idx].update_status(plan_stage.status, plan_stage.elapsed)

        if plan_stage.status == StageStatus.COMPLETED:
            self._write_log(
                f"[green]✓ Planning[/green] — {StagePill._fmt(plan_stage.elapsed)}"
            )
            preview = plan_output[:300].strip()
            if preview:
                self._write_log(f"[dim]{preview}[/dim]\n")
            self._stage_outputs["Planning"] = plan_output
            prev_output = plan_output
        else:
            self._write_log(f"[red]✗ Planning failed:[/red] {plan_stage.error}")
            failed = True

        # ── Phase 2: Decomposition (once) ────────────────────────────────
        if not failed:
            decomp_idx, decomp_stage = stage_map["Decomposition"]
            decomp_pill = pills[decomp_idx]
            decomp_pill.update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header("Decomposition — splitting tasks…")
            self._write_log(
                f"\n[bold yellow]▶ Decomposition[/bold yellow] "
                f"[dim](manager splitting tasks)[/dim]"
            )

            decomp_stage.start()
            decomposed_tasks = await decompose_task(prompt, plan_output, self.working_dir)
            decomp_stage.complete(f"Decomposed into {len(decomposed_tasks)} subtasks")
            self._last_decomposed_tasks = decomposed_tasks

            decomp_pill.update_status(StageStatus.COMPLETED, decomp_stage.elapsed)
            self._write_log(
                f"[green]✓ Decomposition[/green] — {StagePill._fmt(decomp_stage.elapsed)} "
                f"→ [bold]{len(decomposed_tasks)} subtask(s)[/bold]"
            )
            for t in decomposed_tasks:
                files = ", ".join(t.files) if t.files else "—"
                self._write_log(f"  [dim]#{t.id}: {t.description[:80]}  ({files})[/dim]")

        # ── Phase 3: Implementation + Tests loop ──────────────────────────
        if not failed:
            success, prev_output = await self._run_impl_tests_loop(
                pills, stage_map, decomposed_tasks, prompt, prev_output
            )
            if not success:
                failed = True
                stats_bar.remove_class("working")
                stats_bar.update("Failed at: Implementation / Tests & Validation")

        # ── Phase 4: Code Quality & Technical Debt loop ───────────────────
        cq_idx, cq_stage = stage_map["Code Quality"]
        quality_iteration = 0

        while not failed:
            quality_iteration += 1
            cq_stage.status = StageStatus.PENDING
            cq_stage.elapsed = 0.0
            cq_stage.output = ""
            cq_stage.error = ""

            pills[cq_idx].update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header("Code Quality & Technical Debt")
            self._write_log(f"\n[bold yellow]▶ Code Quality & Technical Debt[/bold yellow]")

            def on_cq_stream(chunk, _self=self):
                _self._append_stream(chunk)

            cq_output = await run_stage(
                cq_stage, prompt, prev_output, self.working_dir, on_stream=on_cq_stream
            )
            pills[cq_idx].update_status(cq_stage.status, cq_stage.elapsed)

            if cq_stage.status != StageStatus.COMPLETED:
                self._write_log(f"[red]✗ Code Quality failed:[/red] {cq_stage.error}")
                failed = True
                break

            self._write_log(
                f"[green]✓ Code Quality[/green] — {StagePill._fmt(cq_stage.elapsed)}"
            )
            preview = cq_output[:300].strip()
            if preview:
                self._write_log(f"[dim]{preview}[/dim]\n")
            self._stage_outputs["Code Quality"] = cq_output

            self._set_stream_header("Evaluating quality & technical debt…")
            should_loop = await evaluate_should_iterate(cq_output, self.working_dir)
            if not should_loop:
                prev_output = cq_output
                self._write_log(
                    "\n[bold green]Quality & debt resolved — proceeding to documentation[/bold green]"
                )
                break

            quality_context = (
                f"Code Quality & Technical Debt review #{quality_iteration} found issues "
                f"that require a full re-implementation pass:\n{cq_output[:3000]}\n\n"
                "Fix ALL reported quality and technical debt issues in the new implementation."
            )
            self._write_log(
                f"\n[bold yellow]Quality/debt issues — re-running from Decomposition "
                f"(attempt {quality_iteration})[/bold yellow]"
            )

            for pill_stage_name in ("Decomposition", "Implementation", "Tests & Validation"):
                pills[RERUN_ORDER.index(pill_stage_name)].update_status(StageStatus.PENDING)
            pills[cq_idx].update_status(StageStatus.PENDING)

            d_i, d_stage = stage_map["Decomposition"]
            planning_out = self._stage_outputs.get("Planning", "")
            decomp_context = (
                f"{planning_out}\n\n{quality_context}" if planning_out else quality_context
            )

            pills[d_i].update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header("Decomposition — re-splitting with quality feedback…")
            self._write_log(
                f"\n[bold yellow]▶ Decomposition[/bold yellow] "
                f"[dim](re-splitting with quality feedback)[/dim]"
            )

            d_stage.start()
            decomposed_tasks = await decompose_task(prompt, decomp_context, self.working_dir)
            d_stage.complete(f"Decomposed into {len(decomposed_tasks)} subtasks")
            self._last_decomposed_tasks = decomposed_tasks

            pills[d_i].update_status(StageStatus.COMPLETED, d_stage.elapsed)
            self._write_log(
                f"[green]✓ Decomposition[/green] — {StagePill._fmt(d_stage.elapsed)} "
                f"→ [bold]{len(decomposed_tasks)} subtask(s)[/bold]"
            )
            for t in decomposed_tasks:
                files = ", ".join(t.files) if t.files else "—"
                self._write_log(f"  [dim]#{t.id}: {t.description[:80]}  ({files})[/dim]")

            success, prev_output = await self._run_impl_tests_loop(
                pills,
                stage_map,
                decomposed_tasks,
                prompt,
                planning_out,
                base_context=quality_context,
                label_suffix=" (quality fix)",
            )
            if not success:
                failed = True
                stats_bar.remove_class("working")
                stats_bar.update("Failed at: Implementation / Tests (quality fix)")

        # ── Phase 5: Documentation ────────────────────────────────────────
        if not failed:
            docs_idx, docs_stage = stage_map["Documentation"]
            pills[docs_idx].update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header("Documentation")
            self._write_log(f"\n[bold yellow]▶ Documentation[/bold yellow]")

            def on_docs_stream(chunk, _self=self):
                _self._append_stream(chunk)

            docs_output = await run_stage(
                docs_stage, prompt, prev_output, self.working_dir, on_stream=on_docs_stream
            )
            pills[docs_idx].update_status(docs_stage.status, docs_stage.elapsed)

            if docs_stage.status == StageStatus.COMPLETED:
                self._write_log(
                    f"[green]✓ Documentation[/green] — {StagePill._fmt(docs_stage.elapsed)}"
                )
                preview = docs_output[:300].strip()
                if preview:
                    self._write_log(f"[dim]{preview}[/dim]\n")
                self._stage_outputs["Documentation"] = docs_output
                prev_output = docs_output
            else:
                self._write_log(f"[red]✗ Documentation failed:[/red] {docs_stage.error}")
                stats_bar.update("Failed at: Documentation")
                failed = True

        # ── Phase 6: Commit & PR ─────────────────────────────────────────
        if not failed:
            pr_idx, pr_stage = stage_map["Commit & PR"]
            pills[pr_idx].update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header("Commit & PR")
            self._write_log(f"\n[bold yellow]▶ Commit & PR[/bold yellow]")

            def on_pr_stream(chunk, _self=self):
                _self._append_stream(chunk)

            def on_pr_log(msg, _self=self):
                self._write_log(f"  [dim]{msg}[/dim]")

            pr_output = await run_commit_pr_stage(
                pr_stage,
                prompt,
                prev_output,
                self.working_dir,
                on_stream=on_pr_stream,
                on_log=on_pr_log,
            )
            pills[pr_idx].update_status(pr_stage.status, pr_stage.elapsed)

            if pr_stage.status == StageStatus.COMPLETED:
                self._write_log(
                    f"[green]✓ Commit & PR[/green] — {StagePill._fmt(pr_stage.elapsed)}"
                )
                self._stage_outputs["Commit & PR"] = pr_output
            else:
                self._write_log(f"[red]✗ Commit & PR failed:[/red] {pr_stage.error}")
                stats_bar.update("Failed at: Commit & PR")
                failed = True

        # ── Final status ─────────────────────────────────────────────────
        stats = pipeline_stats
        final_stats = (
            f"Calls: {stats.total_calls} | Cost: ${stats.total_cost_usd:.4f} "
            f"| Time: {stats.format_stage_time()}"
        )

        stats_bar.remove_class("working")
        if not failed:
            stats_bar.add_class("success")
            stats_bar.update(f"✓ Done — {final_stats}")
            self._write_log(f"\n[bold green]All stages completed![/bold green]")
            self._set_stream_header(f"Done — {final_stats}")
        else:
            stats_bar.add_class("error")
            stats_bar.update(f"✗ Failed — {final_stats}")

        prompt_input.disabled = False
        self.running = False
        for pill in self.query(StagePill):
            pill.add_class("pill-rerunnable")

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

        from_idx = RERUN_ORDER.index(from_stage_name)
        for pill in pills[from_idx:]:
            pill.update_status(StageStatus.PENDING)

        prev_name = STAGE_PREV.get(from_stage_name)
        prev_output = self._stage_outputs.get(prev_name, "") if prev_name else ""
        prompt = self._last_prompt
        decomposed_tasks = (
            self._last_decomposed_tasks
            if from_idx > RERUN_ORDER.index("Decomposition")
            else []
        )

        fresh_stages = {s.name: s for s in create_stages()}
        failed = False

        self._write_log(
            f"\n[bold cyan]━━━ Re-running from: {from_stage_name} ━━━[/bold cyan]\n"
            f"[dim]Using context from previous run[/dim]"
        )

        for stage_name in RERUN_ORDER[from_idx:]:
            pill_idx = RERUN_ORDER.index(stage_name)
            pill = pills[pill_idx]
            stage = fresh_stages[stage_name]

            pill.update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header(stage_name)

            if stage_name == "Decomposition":
                self._set_stream_header("Decomposition — splitting tasks…")
                self._write_log(
                    f"\n[bold yellow]▶ Decomposition[/bold yellow] "
                    f"[dim](manager splitting tasks)[/dim]"
                )
                stage.start()
                decomposed_tasks = await decompose_task(prompt, prev_output, self.working_dir)
                stage.complete(f"Decomposed into {len(decomposed_tasks)} subtasks")
                self._last_decomposed_tasks = decomposed_tasks
                pill.update_status(StageStatus.COMPLETED, stage.elapsed)
                self._write_log(
                    f"[green]✓ Decomposition[/green] — {StagePill._fmt(stage.elapsed)} "
                    f"→ [bold]{len(decomposed_tasks)} subtask(s)[/bold]"
                )
                for t in decomposed_tasks:
                    files = ", ".join(t.files) if t.files else "—"
                    self._write_log(f"  [dim]#{t.id}: {t.description[:80]}  ({files})[/dim]")

            elif stage_name == "Commit & PR":
                self._write_log(f"\n[bold yellow]▶ {stage_name}[/bold yellow]")

                def on_pr_stream(chunk, _self=self):
                    _self._append_stream(chunk)

                def on_pr_log(msg, _self=self):
                    _self._write_log(f"  [dim]{msg}[/dim]")

                output = await run_commit_pr_stage(
                    stage, prompt, prev_output, self.working_dir,
                    on_stream=on_pr_stream, on_log=on_pr_log,
                )
                pill.update_status(stage.status, stage.elapsed)
                if stage.status == StageStatus.COMPLETED:
                    self._write_log(
                        f"[green]✓ {stage_name}[/green] — {StagePill._fmt(stage.elapsed)}"
                    )
                    self._stage_outputs[stage_name] = output
                    prev_output = output
                else:
                    self._write_log(f"[red]✗ {stage_name} failed:[/red] {stage.error}")
                    failed = True
                    break

            elif stage.parallel and decomposed_tasks:
                self._set_stream_header(f"{stage_name} — {len(decomposed_tasks)} workers")
                self._write_log(
                    f"\n[bold yellow]▶ {stage_name}[/bold yellow] "
                    f"[dim]({len(decomposed_tasks)} parallel workers)[/dim]"
                )

                def on_worker_complete(task, result, _self=self):
                    color = "green" if result.success else "red"
                    status_str = "completed" if result.success else "failed"
                    _self._write_log(
                        f"  [{color}]W{task.id} {status_str}[/{color}] "
                        f"[dim]{StagePill._fmt(task.elapsed)}[/dim]"
                    )

                def on_parallel_stream(chunk, worker_id, _self=self):
                    _self._append_stream(chunk, worker_id)

                output = await run_stage_parallel(
                    stage, decomposed_tasks, prompt, prev_output, self.working_dir,
                    on_worker_start=lambda task: None,
                    on_worker_complete=on_worker_complete,
                    on_stream=on_parallel_stream,
                )
                pill.update_status(stage.status, stage.elapsed)
                if stage.status == StageStatus.COMPLETED:
                    self._write_log(
                        f"[green]✓ {stage_name}[/green] — {StagePill._fmt(stage.elapsed)} "
                        f"[dim]({len(decomposed_tasks)} workers)[/dim]"
                    )
                    self._stage_outputs[stage_name] = output
                    prev_output = output
                else:
                    self._write_log(f"[red]✗ {stage_name} failed:[/red] {stage.error}")
                    failed = True
                    break

            else:
                self._write_log(f"\n[bold yellow]▶ {stage_name}[/bold yellow]")

                def on_rerun_stream(chunk, _self=self):
                    _self._append_stream(chunk)

                output = await run_stage(
                    stage, prompt, prev_output, self.working_dir, on_stream=on_rerun_stream
                )
                pill.update_status(stage.status, stage.elapsed)
                if stage.status == StageStatus.COMPLETED:
                    self._write_log(
                        f"[green]✓ {stage_name}[/green] — {StagePill._fmt(stage.elapsed)}"
                    )
                    preview = output[:300].strip()
                    if preview:
                        self._write_log(f"[dim]{preview}[/dim]\n")
                    self._stage_outputs[stage_name] = output
                    prev_output = output
                else:
                    self._write_log(f"[red]✗ {stage_name} failed:[/red] {stage.error}")
                    failed = True
                    break

        stats = pipeline_stats
        final_stats = (
            f"Calls: {stats.total_calls} | Cost: ${stats.total_cost_usd:.4f} "
            f"| Time: {stats.format_stage_time()}"
        )

        stats_bar.remove_class("working")
        if not failed:
            stats_bar.add_class("success")
            stats_bar.update(f"✓ Done — {final_stats}")
            self._write_log(f"\n[bold green]Re-run complete![/bold green]")
            self._set_stream_header(f"Done — {final_stats}")
        else:
            stats_bar.add_class("error")
            stats_bar.update(f"✗ Failed — {final_stats}")

        prompt_input.disabled = False
        self.running = False
        for pill in self.query(StagePill):
            pill.add_class("pill-rerunnable")
