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

from app.agents import Task, decompose_task
from app.git import run_commit_pr_stage
from app.models import pipeline_stats
from app.pipeline import run_stage, run_stage_parallel
from app.stages import MAX_ITERATIONS, StageStatus, create_stages
from app.widgets import RERUN_ORDER, STAGE_PREV, StagePill


class PipelineRunnerMixin:
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

        prev_output = ""
        iteration = 0
        failed = False
        decomposed_tasks: list[Task] = []

        stage_map = {s.name: (i, s) for i, s in enumerate(stages)}

        iterable_stages = [(i, s) for i, s in enumerate(stages) if s.iterable]
        post_stages = [(i, s) for i, s in enumerate(stages) if not s.iterable and s.name not in ("Decomposition", "Code Quality")]
        cq_idx, cq_stage = stage_map["Code Quality"]

        while iteration < MAX_ITERATIONS:
            iteration += 1
            iteration_context = ""
            if iteration > 1:
                self._write_log(f"\n[bold cyan]━━━ Iteration {iteration}/{MAX_ITERATIONS} ━━━[/bold cyan]")
                iteration_context = (
                    f"This is iteration {iteration}/{MAX_ITERATIONS} of the refinement loop.\n"
                    f"Previous test/validation feedback:\n{prev_output[:4000]}\n\n"
                    "Focus on fixing the issues identified in the previous iteration.\n\n"
                )

            for i, stage in iterable_stages:
                stage.status = StageStatus.PENDING
                stage.elapsed = 0.0
                stage.output = ""
                stage.error = ""
                pill = pills[i]

                if stage.parallel and decomposed_tasks:
                    pill.update_status(StageStatus.RUNNING)
                    self._clear_stream()
                    self._set_stream_header(
                        f"{stage.name} — {len(decomposed_tasks)} workers (iter {iteration}/{MAX_ITERATIONS})"
                    )
                    self._write_log(
                        f"\n[bold yellow]▶ {stage.name}[/bold yellow] "
                        f"[dim]({len(decomposed_tasks)} parallel workers)[/dim]"
                    )

                    def on_worker_complete(task, result, _pill=pill, _self=self):
                        status_str = "completed" if result.success else "failed"
                        color = "green" if result.success else "red"
                        _self._write_log(
                            f"  [{color}]W{task.id} {status_str}[/{color}] "
                            f"[dim]{StagePill._fmt(task.elapsed)}[/dim]"
                        )

                    def on_parallel_stream(chunk, worker_id, _self=self):
                        _self._append_stream(chunk, worker_id)

                    output = await run_stage_parallel(
                        stage,
                        decomposed_tasks,
                        prompt,
                        prev_output,
                        self.working_dir,
                        iteration_context=iteration_context,
                        on_worker_start=lambda task: None,
                        on_worker_complete=on_worker_complete,
                        on_stream=on_parallel_stream,
                    )

                    pill.update_status(stage.status, stage.elapsed)

                    if stage.status == StageStatus.COMPLETED:
                        self._write_log(
                            f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)} "
                            f"[dim]({len(decomposed_tasks)} workers)[/dim]"
                        )
                        self._stage_outputs[stage.name] = output
                        prev_output = output
                        iteration_context = ""
                    else:
                        self._write_log(f"[red]✗ {stage.name} failed:[/red] {stage.error}")
                        stats_bar.remove_class("working")
                        stats_bar.update(f"Failed at: {stage.name}")
                        failed = True
                        break
                else:
                    pill.update_status(StageStatus.RUNNING)
                    self._clear_stream()
                    self._set_stream_header(f"{stage.name} (iter {iteration}/{MAX_ITERATIONS})")
                    self._write_log(f"\n[bold yellow]▶ {stage.name}[/bold yellow]")

                    def on_single_stream(chunk, _self=self):
                        _self._append_stream(chunk)

                    output = await run_stage(
                        stage, prompt, prev_output, self.working_dir,
                        iteration_context,
                        on_stream=on_single_stream,
                    )

                    pill.update_status(stage.status, stage.elapsed)

                    if stage.status == StageStatus.COMPLETED:
                        self._write_log(f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)}")
                        preview = output[:300].strip()
                        if preview:
                            self._write_log(f"[dim]{preview}[/dim]\n")
                        self._stage_outputs[stage.name] = output
                        prev_output = output
                        iteration_context = ""

                        if stage.name == "Planning":
                            decomp_idx, decomp_stage = stage_map["Decomposition"]
                            decomp_pill = pills[decomp_idx]
                            decomp_pill.update_status(StageStatus.RUNNING)
                            self._clear_stream()
                            self._set_stream_header("Decomposition — splitting tasks…")
                            self._write_log(f"\n[bold yellow]▶ Decomposition[/bold yellow] [dim](manager splitting tasks)[/dim]")

                            decomp_stage.start()
                            decomposed_tasks = await decompose_task(prompt, prev_output, self.working_dir)
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
                    else:
                        self._write_log(f"[red]✗ {stage.name} failed:[/red] {stage.error}")
                        stats_bar.remove_class("working")
                        stats_bar.update(f"Failed at: {stage.name}")
                        failed = True
                        break

            if failed:
                break

            from app.stages import has_issues
            if not has_issues(prev_output):
                self._write_log(f"\n[bold green]No issues found — exiting loop after {iteration} iteration(s)[/bold green]")
                break
            elif iteration < MAX_ITERATIONS:
                self._write_log("\n[bold yellow]Issues detected — looping back for refinement…[/bold yellow]")

        # ── Quality refinement loop ──────────────────────────────────────────
        MAX_QUALITY_RETRIES = 2
        quality_retry = 0
        quality_fix_context = ""

        while not failed:
            cq_stage.status = StageStatus.PENDING
            cq_stage.elapsed = 0.0
            cq_stage.output = ""
            cq_stage.error = ""

            pills[cq_idx].update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header("Code Quality")
            self._write_log(f"\n[bold yellow]▶ Code Quality[/bold yellow]")

            def on_cq_stream(chunk, _self=self):
                _self._append_stream(chunk)

            cq_output = await run_stage(
                cq_stage, prompt, prev_output, self.working_dir,
                quality_fix_context,
                on_stream=on_cq_stream,
            )
            pills[cq_idx].update_status(cq_stage.status, cq_stage.elapsed)

            if cq_stage.status != StageStatus.COMPLETED:
                self._write_log(f"[red]✗ Code Quality failed:[/red] {cq_stage.error}")
                failed = True
                break

            self._write_log(f"[green]✓ Code Quality[/green] — {StagePill._fmt(cq_stage.elapsed)}")
            preview = cq_output[:300].strip()
            if preview:
                self._write_log(f"[dim]{preview}[/dim]\n")
            self._stage_outputs["Code Quality"] = cq_output

            from app.stages import has_issues
            if not has_issues(cq_output) or quality_retry >= MAX_QUALITY_RETRIES:
                if has_issues(cq_output):
                    self._write_log(f"[dim]Max quality retries reached — continuing.[/dim]")
                prev_output = cq_output
                break

            quality_retry += 1
            quality_fix_context = (
                f"Code Quality review found these issues (attempt {quality_retry}):\n"
                f"{cq_output[:3000]}\n\n"
                "Re-decompose and re-implement to fix ALL reported issues."
            )
            self._write_log(
                f"\n[bold yellow]Code quality issues — re-running from Decomposition "
                f"(attempt {quality_retry}/{MAX_QUALITY_RETRIES})[/bold yellow]"
            )

            for name in ("Decomposition", "Implementation", "Tests & Validation"):
                pills[RERUN_ORDER.index(name)].update_status(StageStatus.PENDING)
            pills[cq_idx].update_status(StageStatus.PENDING)

            d_i, d_stage = stage_map["Decomposition"]
            d_stage.status = StageStatus.PENDING
            planning_out = self._stage_outputs.get("Planning", "")
            decomp_context = f"{planning_out}\n\n{quality_fix_context}" if planning_out else quality_fix_context

            pills[d_i].update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header("Decomposition — re-splitting tasks…")
            self._write_log(f"\n[bold yellow]▶ Decomposition[/bold yellow] [dim](re-splitting with quality feedback)[/dim]")

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

            prev_output = planning_out

            for re_name in ("Implementation", "Tests & Validation"):
                re_i, re_stage = next((i, s) for i, s in enumerate(stages) if s.name == re_name)
                re_stage.status = StageStatus.PENDING
                re_stage.elapsed = 0.0
                re_stage.output = ""
                re_stage.error = ""
                re_pill = pills[re_i]

                re_pill.update_status(StageStatus.RUNNING)
                self._clear_stream()
                self._set_stream_header(re_name)

                if re_stage.parallel and decomposed_tasks:
                    self._write_log(
                        f"\n[bold yellow]▶ {re_name}[/bold yellow] "
                        f"[dim]({len(decomposed_tasks)} parallel workers)[/dim]"
                    )

                    def on_re_wc(task, result, _self=self):
                        color = "green" if result.success else "red"
                        status_str = "completed" if result.success else "failed"
                        _self._write_log(
                            f"  [{color}]W{task.id} {status_str}[/{color}] "
                            f"[dim]{StagePill._fmt(task.elapsed)}[/dim]"
                        )

                    def on_re_ps(chunk, worker_id, _self=self):
                        _self._append_stream(chunk, worker_id)

                    re_output = await run_stage_parallel(
                        re_stage, decomposed_tasks, prompt, prev_output, self.working_dir,
                        iteration_context=quality_fix_context,
                        on_worker_start=lambda task: None,
                        on_worker_complete=on_re_wc,
                        on_stream=on_re_ps,
                    )
                else:
                    self._write_log(f"\n[bold yellow]▶ {re_name}[/bold yellow]")

                    def on_re_ss(chunk, _self=self):
                        _self._append_stream(chunk)

                    re_output = await run_stage(
                        re_stage, prompt, prev_output, self.working_dir,
                        quality_fix_context,
                        on_stream=on_re_ss,
                    )

                re_pill.update_status(re_stage.status, re_stage.elapsed)

                if re_stage.status == StageStatus.COMPLETED:
                    self._write_log(f"[green]✓ {re_name}[/green] — {StagePill._fmt(re_stage.elapsed)}")
                    preview = re_output[:300].strip()
                    if preview:
                        self._write_log(f"[dim]{preview}[/dim]\n")
                    self._stage_outputs[re_name] = re_output
                    prev_output = re_output
                else:
                    self._write_log(f"[red]✗ {re_name} failed:[/red] {re_stage.error}")
                    failed = True
                    break
        # ── End quality refinement loop ──────────────────────────────────────

        if not failed:
            for i, stage in post_stages:
                pill = pills[i]
                pill.update_status(StageStatus.RUNNING)
                self._clear_stream()
                self._set_stream_header(stage.name)
                self._write_log(f"\n[bold yellow]▶ {stage.name}[/bold yellow]")

                if stage.name == "Commit & PR":
                    def on_pr_stream(chunk, _self=self):
                        _self._append_stream(chunk)

                    def on_pr_log(msg, _self=self):
                        _self._write_log(f"  [dim]{msg}[/dim]")

                    output = await run_commit_pr_stage(
                        stage, prompt, prev_output, self.working_dir,
                        on_stream=on_pr_stream,
                        on_log=on_pr_log,
                    )
                else:
                    def on_post_stream(chunk, _self=self):
                        _self._append_stream(chunk)

                    output = await run_stage(
                        stage, prompt, prev_output, self.working_dir,
                        on_stream=on_post_stream,
                    )

                pill.update_status(stage.status, stage.elapsed)

                if stage.status == StageStatus.COMPLETED:
                    self._write_log(f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)}")
                    if stage.name != "Commit & PR":
                        preview = output[:300].strip()
                        if preview:
                            self._write_log(f"[dim]{preview}[/dim]\n")
                    self._stage_outputs[stage.name] = output
                    prev_output = output
                else:
                    self._write_log(f"[red]✗ {stage.name} failed:[/red] {stage.error}")
                    stats_bar.update(f"Failed at: {stage.name}")
                    failed = True
                    break

        stats = pipeline_stats
        cost = stats.total_cost_usd
        calls = stats.total_calls
        elapsed_str = stats.format_elapsed()
        final_stats = f"Calls: {calls} | Cost: ${cost:.4f} | Time: {elapsed_str}"

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
        decomposed_tasks = self._last_decomposed_tasks if from_idx > RERUN_ORDER.index("Decomposition") else []

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
                self._write_log(f"\n[bold yellow]▶ Decomposition[/bold yellow] [dim](manager splitting tasks)[/dim]")
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
                    on_stream=on_pr_stream,
                    on_log=on_pr_log,
                )
                pill.update_status(stage.status, stage.elapsed)
                if stage.status == StageStatus.COMPLETED:
                    self._write_log(f"[green]✓ {stage_name}[/green] — {StagePill._fmt(stage.elapsed)}")
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

                output = await run_stage(stage, prompt, prev_output, self.working_dir, on_stream=on_rerun_stream)
                pill.update_status(stage.status, stage.elapsed)
                if stage.status == StageStatus.COMPLETED:
                    self._write_log(f"[green]✓ {stage_name}[/green] — {StagePill._fmt(stage.elapsed)}")
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
        final_stats = f"Calls: {stats.total_calls} | Cost: ${stats.total_cost_usd:.4f} | Time: {stats.format_elapsed()}"

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
