"""Pipeline step helpers: single-pass and looping impl+tests execution."""

from app.claude import evaluate_should_iterate
from app.pipeline import run_stage, run_stage_parallel
from app.stages import StageStatus
from app.widgets import RERUN_ORDER, StagePill


class PipelineStepsMixin:
    """Mixin providing reusable Implementation + Tests execution helpers."""

    async def _run_impl_and_tests(
        self,
        pills: list,
        stage_map: dict,
        decomposed_tasks: list,
        prompt: str,
        prev_output: str,
        iteration_context: str = "",
        label_suffix: str = "",
    ) -> tuple[bool, str, str]:
        """Run one pass of Implementation then Tests & Validation.

        Returns (success, impl_output, tests_output).
        """
        impl_idx, impl_stage = stage_map["Implementation"]
        tests_idx, tests_stage = stage_map["Tests & Validation"]

        for stage in (impl_stage, tests_stage):
            stage.status = StageStatus.PENDING
            stage.elapsed = 0.0
            stage.output = ""
            stage.error = ""

        # ── Implementation ───────────────────────────────────────────────
        impl_pill = pills[impl_idx]
        if impl_stage.parallel and decomposed_tasks:
            impl_pill.update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header(
                f"Implementation{label_suffix} — {len(decomposed_tasks)} workers"
            )
            self._write_log(
                f"\n[bold yellow]▶ Implementation[/bold yellow] "
                f"[dim]({len(decomposed_tasks)} parallel workers)[/dim]"
            )

            def on_impl_wc(task, result, _self=self):
                color = "green" if result.success else "red"
                status_str = "completed" if result.success else "failed"
                _self._write_log(
                    f"  [{color}]W{task.id} {status_str}[/{color}] "
                    f"[dim]{StagePill._fmt(task.elapsed)}[/dim]"
                )

            def on_impl_ps(chunk, worker_id, _self=self):
                _self._append_stream(chunk, worker_id)

            impl_output = await run_stage_parallel(
                impl_stage,
                decomposed_tasks,
                prompt,
                prev_output,
                self.working_dir,
                iteration_context=iteration_context,
                on_worker_start=lambda task: None,
                on_worker_complete=on_impl_wc,
                on_stream=on_impl_ps,
            )
        else:
            impl_pill.update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header(f"Implementation{label_suffix}")
            self._write_log(f"\n[bold yellow]▶ Implementation[/bold yellow]")

            def on_impl_ss(chunk, _self=self):
                _self._append_stream(chunk)

            impl_output = await run_stage(
                impl_stage,
                prompt,
                prev_output,
                self.working_dir,
                iteration_context,
                on_stream=on_impl_ss,
            )

        impl_pill.update_status(impl_stage.status, impl_stage.elapsed)
        if impl_stage.status != StageStatus.COMPLETED:
            self._write_log(f"[red]✗ Implementation failed:[/red] {impl_stage.error}")
            return False, "", ""

        self._write_log(
            f"[green]✓ Implementation[/green] — {StagePill._fmt(impl_stage.elapsed)}"
        )
        self._stage_outputs["Implementation"] = impl_output

        # ── Tests & Validation ───────────────────────────────────────────
        tests_pill = pills[tests_idx]
        if tests_stage.parallel and decomposed_tasks:
            tests_pill.update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header(
                f"Tests & Validation{label_suffix} — {len(decomposed_tasks)} workers"
            )
            self._write_log(
                f"\n[bold yellow]▶ Tests & Validation[/bold yellow] "
                f"[dim]({len(decomposed_tasks)} parallel workers)[/dim]"
            )

            def on_tests_wc(task, result, _self=self):
                color = "green" if result.success else "red"
                status_str = "completed" if result.success else "failed"
                _self._write_log(
                    f"  [{color}]W{task.id} {status_str}[/{color}] "
                    f"[dim]{StagePill._fmt(task.elapsed)}[/dim]"
                )

            def on_tests_ps(chunk, worker_id, _self=self):
                _self._append_stream(chunk, worker_id)

            tests_output = await run_stage_parallel(
                tests_stage,
                decomposed_tasks,
                prompt,
                impl_output,
                self.working_dir,
                iteration_context=iteration_context,
                on_worker_start=lambda task: None,
                on_worker_complete=on_tests_wc,
                on_stream=on_tests_ps,
            )
        else:
            tests_pill.update_status(StageStatus.RUNNING)
            self._clear_stream()
            self._set_stream_header(f"Tests & Validation{label_suffix}")
            self._write_log(f"\n[bold yellow]▶ Tests & Validation[/bold yellow]")

            def on_tests_ss(chunk, _self=self):
                _self._append_stream(chunk)

            tests_output = await run_stage(
                tests_stage,
                prompt,
                impl_output,
                self.working_dir,
                iteration_context,
                on_stream=on_tests_ss,
            )

        tests_pill.update_status(tests_stage.status, tests_stage.elapsed)
        if tests_stage.status != StageStatus.COMPLETED:
            self._write_log(
                f"[red]✗ Tests & Validation failed:[/red] {tests_stage.error}"
            )
            return False, impl_output, ""

        self._write_log(
            f"[green]✓ Tests & Validation[/green] — {StagePill._fmt(tests_stage.elapsed)}"
        )
        preview = tests_output[:300].strip()
        if preview:
            self._write_log(f"[dim]{preview}[/dim]\n")
        self._stage_outputs["Tests & Validation"] = tests_output
        return True, impl_output, tests_output

    async def _run_impl_tests_loop(
        self,
        pills: list,
        stage_map: dict,
        decomposed_tasks: list,
        prompt: str,
        prev_output: str,
        base_context: str = "",
        label_suffix: str = "",
    ) -> tuple[bool, str]:
        """Loop Implementation → Tests until Claude confirms no more issues.

        Returns (success, last_impl_output).
        """
        iteration = 0
        test_failure_context = ""

        while True:
            iteration += 1
            iteration_context = base_context

            if iteration > 1:
                self._write_log(
                    f"\n[bold cyan]━━━ Implementation iteration {iteration} ━━━[/bold cyan]"
                )
                for pill_stage_name in ("Implementation", "Tests & Validation"):
                    pills[RERUN_ORDER.index(pill_stage_name)].update_status(
                        StageStatus.PENDING
                    )
                if test_failure_context:
                    iteration_context = base_context + (
                        f"\nFix these test issues from the previous run:\n"
                        f"{test_failure_context[:3000]}\n\n"
                    )

            success, impl_output, tests_output = await self._run_impl_and_tests(
                pills,
                stage_map,
                decomposed_tasks,
                prompt,
                prev_output,
                iteration_context,
                label_suffix,
            )
            if not success:
                return False, ""

            self._set_stream_header("Evaluating test results…")
            should_loop = await evaluate_should_iterate(tests_output, self.working_dir)
            if not should_loop:
                self._write_log(
                    "\n[bold green]Tests passed — moving to quality review[/bold green]"
                )
                return True, impl_output

            test_failure_context = tests_output
            self._write_log(
                "\n[bold yellow]Test issues detected — re-running implementation…[/bold yellow]"
            )
