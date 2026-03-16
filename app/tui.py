"""Terminal UI for the multi-agent development pipeline."""

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, HorizontalScroll, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import var
from textual.widgets import Footer, Header, Label, RichLog, Static, TextArea

from app.agents import Task, pipeline_stats
from app.pipeline import (
    MAX_ITERATIONS,
    StageStatus,
    create_stages,
    decompose_task,
    has_issues,
    run_commit_pr_stage,
    run_stage,
    run_stage_parallel,
)

STAGE_SHORT_NAMES = {
    "Planning": "Plan",
    "Decomposition": "Decomp",
    "Implementation": "Impl",
    "Tests & Validation": "Tests",
    "Code Quality": "Quality",
    "Documentation": "Docs",
    "Commit & PR": "PR",
}


class StagePill(Static):
    """Rounded-box stage card for the horizontal pipeline bar."""

    _ICONS = {
        StageStatus.PENDING:   "[dim]○[/dim]",
        StageStatus.RUNNING:   "[bold yellow]◉[/bold yellow]",
        StageStatus.COMPLETED: "[bold green]✓[/bold green]",
        StageStatus.FAILED:    "[bold red]✗[/bold red]",
    }

    def __init__(self, stage_name: str, index: int, is_parallel: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.stage_name = stage_name
        self.index = index
        self.is_parallel = is_parallel

    def _label_text(self, status: StageStatus, elapsed: float = 0.0) -> str:
        short = STAGE_SHORT_NAMES.get(self.stage_name, self.stage_name)
        if self.is_parallel:
            short += " ⇶"
        icon = self._ICONS[status]
        time_str = f"  [dim]{self._fmt(elapsed)}[/dim]" if elapsed > 0 else ""
        name = f"[bold]{short}[/bold]" if status == StageStatus.RUNNING else short
        return f"{icon}  {name}{time_str}"

    def compose(self) -> ComposeResult:
        yield Label(self._label_text(StageStatus.PENDING), id=f"pill-label-{self.index}")

    @staticmethod
    def _fmt(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f}s"
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"

    def update_status(self, status: StageStatus, elapsed: float = 0.0):
        try:
            label = self.query_one(f"#pill-label-{self.index}", Label)
        except NoMatches:
            return
        label.update(self._label_text(status, elapsed))
        self.remove_class("pill-running", "pill-done", "pill-failed")
        if status == StageStatus.RUNNING:
            self.add_class("pill-running")
        elif status == StageStatus.COMPLETED:
            self.add_class("pill-done")
        elif status == StageStatus.FAILED:
            self.add_class("pill-failed")


class PipelineApp(App):
    """Multi-agent Dev Pipeline TUI."""

    def __init__(self, working_dir: str = "", prompt_file: str = "", **kwargs):
        import os
        self.working_dir = working_dir or os.getcwd()
        self.prompt_file = prompt_file
        super().__init__(**kwargs)

    TITLE = "Dev Pipeline — Multi-Agent"
    CSS = """
    Screen {
        background: $surface;
    }

    /* ══ Stage pill bar ══ */
    #stage-bar {
        height: 5;
        padding: 1 2;
        background: $surface;
        align: left middle;
    }

    /* Each stage card: rounded border, fixed height 3 */
    .pill {
        height: 3;
        width: auto;
        min-width: 18;
        padding: 0 2;
        background: $panel;
        border: round $primary-background;
        content-align: left middle;
    }

    /* Running — highlight border + slightly lighter bg */
    .pill.pill-running {
        border: round $warning;
        background: $boost;
    }

    /* Completed — subtle green border */
    .pill.pill-done {
        border: round $success-darken-2;
        background: $panel;
    }

    /* Failed — red border */
    .pill.pill-failed {
        border: round $error-darken-2;
        background: $panel;
    }

    /* Connector between pills: ──●── centered on the middle row */
    .pill-sep {
        height: 3;
        width: 7;
        content-align: center middle;
        color: $text-muted;
    }

    /* ══ Stream pane ══ */
    #stream-pane {
        height: 10;
        margin: 0 2;
        border: round $primary-background;
        background: $panel;
    }

    #stream-header {
        height: 1;
        padding: 0 1;
        background: $primary-background 30%;
        color: $text-muted;
    }

    #stream-log {
        height: 1fr;
        padding: 0 1;
    }

    /* ══ Input ══ */
    #prompt-input {
        margin: 0 2 0 2;
        height: 5;
        border: round $primary-background;
    }

    #prompt-hint {
        margin: 0 2;
        height: 1;
        color: $text-muted;
    }

    /* ══ Activity log ══ */
    #log-container {
        margin: 0 2 0 2;
        height: 1fr;
        border: round $primary-background;
    }

    /* ══ Stats bar ══ */
    #stats-bar {
        dock: bottom;
        height: 1;
        padding: 0 2;
        background: $panel;
        color: $text-muted;
    }

    #stats-bar.working {
        background: $warning 20%;
        color: $warning;
    }

    #stats-bar.success {
        background: $success 20%;
        color: $success;
    }

    #stats-bar.error {
        background: $error 20%;
        color: $error;
    }

    /* ══ Repo label ══ */
    #repo-label {
        padding: 0 2;
        color: $text-muted;
        height: 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear Log"),
        ("ctrl+enter", "submit_prompt", "Run"),
    ]

    running = var(False)

    def compose(self) -> ComposeResult:
        yield Header()
        stages = create_stages()
        with HorizontalScroll(id="stage-bar"):
            for i, stage in enumerate(stages):
                yield StagePill(stage.name, i, is_parallel=stage.parallel, classes="pill")
                if i < len(stages) - 1:
                    yield Label("──●──", classes="pill-sep")
        yield Label(f"  {self.working_dir}", id="repo-label")
        yield TextArea(
            id="prompt-input",
            soft_wrap=True,
        )
        yield Label("  Ctrl+Enter to run  |  paste markdown/code freely", id="prompt-hint")
        with Vertical(id="stream-pane"):
            yield Label("● Waiting for pipeline…", id="stream-header")
            yield RichLog(id="stream-log", highlight=True, markup=True, wrap=True)
        yield RichLog(id="log-container", highlight=True, markup=True)
        yield Label("Calls: 0 | Cost: $0.000 | Time: 0s", id="stats-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.0, self._refresh_stats)
        if self.prompt_file:
            import os
            try:
                text = open(self.prompt_file).read().strip()
                ta = self.query_one("#prompt-input", TextArea)
                ta.load_text(text)
                self.set_timer(0.3, lambda: self.run_pipeline(text))
            except OSError as e:
                self.query_one("#log-container", RichLog).write(
                    f"[red]Cannot read prompt file:[/red] {e}"
                )

    def _refresh_stats(self) -> None:
        if not self.running:
            return
        stats_bar = self.query_one("#stats-bar", Label)
        stats = pipeline_stats
        cost = stats.total_cost_usd
        calls = stats.total_calls
        elapsed = stats.format_elapsed()
        stats_bar.update(
            f"Calls: {calls} | Cost: ${cost:.4f} | Time: {elapsed}"
        )

    def _set_stream_header(self, text: str) -> None:
        try:
            self.query_one("#stream-header", Label).update(f"● {text}")
        except NoMatches:
            pass

    def _append_stream(self, chunk: str, worker_id: int | None = None) -> None:
        try:
            log = self.query_one("#stream-log", RichLog)
            if worker_id is not None:
                log.write(f"[dim]W{worker_id}:[/dim] {chunk}")
            else:
                log.write(chunk)
        except NoMatches:
            pass

    def _clear_stream(self) -> None:
        try:
            self.query_one("#stream-log", RichLog).clear()
        except NoMatches:
            pass

    def action_submit_prompt(self) -> None:
        if self.running:
            return
        ta = self.query_one("#prompt-input", TextArea)
        text = ta.text.strip()
        if text:
            self.run_pipeline(text)

    @work(exclusive=True)
    async def run_pipeline(self, prompt: str):
        self.running = True
        log = self.query_one("#log-container", RichLog)
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

        log.clear()
        self._clear_stream()
        self._set_stream_header("Pipeline started…")
        log.write(f"[bold]Pipeline started:[/bold] {prompt}\n")

        prev_output = ""
        iteration = 0
        failed = False
        decomposed_tasks: list[Task] = []

        stage_map = {s.name: (i, s) for i, s in enumerate(stages)}

        iterable_stages = [(i, s) for i, s in enumerate(stages) if s.iterable]
        post_stages = [(i, s) for i, s in enumerate(stages) if not s.iterable and s.name != "Decomposition"]

        while iteration < MAX_ITERATIONS:
            iteration += 1
            iteration_context = ""
            if iteration > 1:
                log.write(f"\n[bold cyan]━━━ Iteration {iteration}/{MAX_ITERATIONS} ━━━[/bold cyan]")
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
                    log.write(
                        f"\n[bold yellow]▶ {stage.name}[/bold yellow] "
                        f"[dim]({len(decomposed_tasks)} parallel workers)[/dim]"
                    )

                    def on_worker_start(task, _pill=pill):
                        pass

                    def on_worker_complete(task, result, _pill=pill, _log=log):
                        status_str = "completed" if result.success else "failed"
                        color = "green" if result.success else "red"
                        _log.write(
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
                        on_worker_start=on_worker_start,
                        on_worker_complete=on_worker_complete,
                        on_stream=on_parallel_stream,
                    )

                    pill.update_status(stage.status, stage.elapsed)

                    if stage.status == StageStatus.COMPLETED:
                        log.write(
                            f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)} "
                            f"[dim]({len(decomposed_tasks)} workers)[/dim]"
                        )
                        prev_output = output
                        iteration_context = ""
                    else:
                        log.write(f"[red]✗ {stage.name} failed:[/red] {stage.error}")
                        stats_bar.remove_class("working")
                        stats_bar.update(f"Failed at: {stage.name}")
                        failed = True
                        break
                else:
                    pill.update_status(StageStatus.RUNNING)
                    self._clear_stream()
                    self._set_stream_header(f"{stage.name} (iter {iteration}/{MAX_ITERATIONS})")
                    log.write(f"\n[bold yellow]▶ {stage.name}[/bold yellow]")

                    def on_single_stream(chunk, _self=self):
                        _self._append_stream(chunk)

                    output = await run_stage(
                        stage, prompt, prev_output, self.working_dir,
                        iteration_context,
                        on_stream=on_single_stream,
                    )

                    pill.update_status(stage.status, stage.elapsed)

                    if stage.status == StageStatus.COMPLETED:
                        log.write(f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)}")
                        preview = output[:300].strip()
                        if preview:
                            log.write(f"[dim]{preview}[/dim]\n")
                        prev_output = output
                        iteration_context = ""

                        if stage.name == "Planning":
                            decomp_idx, decomp_stage = stage_map["Decomposition"]
                            decomp_pill = pills[decomp_idx]
                            decomp_pill.update_status(StageStatus.RUNNING)
                            self._clear_stream()
                            self._set_stream_header("Decomposition — splitting tasks…")
                            log.write(f"\n[bold yellow]▶ Decomposition[/bold yellow] [dim](manager splitting tasks)[/dim]")

                            decomp_stage.start()
                            decomposed_tasks = await decompose_task(prompt, prev_output, self.working_dir)
                            decomp_stage.complete(f"Decomposed into {len(decomposed_tasks)} subtasks")

                            decomp_pill.update_status(StageStatus.COMPLETED, decomp_stage.elapsed)
                            log.write(
                                f"[green]✓ Decomposition[/green] — {StagePill._fmt(decomp_stage.elapsed)} "
                                f"→ [bold]{len(decomposed_tasks)} subtask(s)[/bold]"
                            )
                            for t in decomposed_tasks:
                                files = ", ".join(t.files) if t.files else "—"
                                log.write(f"  [dim]#{t.id}: {t.description[:80]}  ({files})[/dim]")
                    else:
                        log.write(f"[red]✗ {stage.name} failed:[/red] {stage.error}")
                        stats_bar.remove_class("working")
                        stats_bar.update(f"Failed at: {stage.name}")
                        failed = True
                        break

            if failed:
                break

            if not has_issues(prev_output):
                log.write(f"\n[bold green]No issues found — exiting loop after {iteration} iteration(s)[/bold green]")
                break
            elif iteration < MAX_ITERATIONS:
                log.write("\n[bold yellow]Issues detected — looping back for refinement…[/bold yellow]")

        if not failed:
            for i, stage in post_stages:
                pill = pills[i]
                pill.update_status(StageStatus.RUNNING)
                self._clear_stream()
                self._set_stream_header(stage.name)
                log.write(f"\n[bold yellow]▶ {stage.name}[/bold yellow]")

                if stage.name == "Commit & PR":
                    def on_pr_stream(chunk, _self=self):
                        _self._append_stream(chunk)

                    def on_pr_log(msg, _log=log):
                        _log.write(f"  [dim]{msg}[/dim]")

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
                    log.write(f"[green]✓ {stage.name}[/green] — {StagePill._fmt(stage.elapsed)}")
                    if stage.name != "Commit & PR":
                        preview = output[:300].strip()
                        if preview:
                            log.write(f"[dim]{preview}[/dim]\n")
                    prev_output = output
                else:
                    log.write(f"[red]✗ {stage.name} failed:[/red] {stage.error}")
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
            log.write(f"\n[bold green]All stages completed![/bold green]")
            self._set_stream_header(f"Done — {final_stats}")
        else:
            stats_bar.add_class("error")
            stats_bar.update(f"✗ Failed — {final_stats}")

        prompt_input.disabled = False
        self.running = False

    def action_clear_log(self):
        self.query_one("#log-container", RichLog).clear()


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Dev Pipeline — Multi-agent LLM-powered development stages")
    parser.add_argument("repo", nargs="?", default=os.getcwd(), help="Path to the target repository (default: current directory)")
    parser.add_argument("-f", "--prompt-file", default="", metavar="FILE", help="Read prompt from FILE and start pipeline immediately")
    args = parser.parse_args()

    repo = os.path.abspath(os.path.expanduser(args.repo))
    if not os.path.isdir(repo):
        print(f"Error: '{repo}' is not a directory")
        raise SystemExit(1)

    prompt_file = ""
    if args.prompt_file:
        prompt_file = os.path.abspath(os.path.expanduser(args.prompt_file))
        if not os.path.isfile(prompt_file):
            print(f"Error: prompt file '{prompt_file}' not found")
            raise SystemExit(1)

    app = PipelineApp(working_dir=repo, prompt_file=prompt_file)
    app.run()


if __name__ == "__main__":
    main()
