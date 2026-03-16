"""Terminal UI for the multi-agent development pipeline."""

import re
from datetime import datetime

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import HorizontalScroll, Vertical
from textual.css.query import NoMatches
from textual.reactive import var
from textual.widgets import Footer, Header, Label, RichLog, TextArea

from app.models import pipeline_stats
from app.runner import PipelineRunnerMixin
from app.stages import StageStatus, create_stages
from app.widgets import StagePill


class PipelineApp(PipelineRunnerMixin, App):
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

    /* Clickable hover — signals re-run affordance */
    .pill.pill-rerunnable:hover {
        border: round $accent;
        background: $boost;
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
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_log", "Clear Log"),
        Binding("ctrl+enter", "submit_prompt", "Run", key_display="ctrl+↵"),
        Binding("ctrl+e", "export_log", "Export Log"),
    ]

    _log_buffer: list[str] = []
    _stage_outputs: dict[str, str] = {}
    _last_prompt: str = ""
    _last_decomposed_tasks: list = []

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
        yield TextArea(id="prompt-input", soft_wrap=True)
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
                self._write_log(f"[red]Cannot read prompt file:[/red] {e}")

    def _refresh_stats(self) -> None:
        if not self.running:
            return
        stats_bar = self.query_one("#stats-bar", Label)
        stats = pipeline_stats
        stats_bar.update(
            f"Calls: {stats.total_calls} | Cost: ${stats.total_cost_usd:.4f} | Time: {stats.format_elapsed()}"
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

    def _write_log(self, text: str) -> None:
        self.query_one("#log-container", RichLog).write(text)
        self._log_buffer.append(text)

    def action_clear_log(self):
        self.query_one("#log-container", RichLog).clear()
        self._log_buffer.clear()

    def action_export_log(self) -> None:
        path = f"pipeline_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        plain = "\n".join(re.sub(r"\[/?[^\]]*\]", "", line) for line in self._log_buffer)
        with open(path, "w") as f:
            f.write(plain)
        self._write_log(f"[green]Log exported →[/green] {path}")

    def on_stage_pill_clicked(self, event: StagePill.Clicked) -> None:
        if self.running or not self._last_prompt:
            return
        self.rerun_from_stage(event.stage_name)


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
