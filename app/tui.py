"""Terminal UI for the development pipeline."""

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import var
from textual.widgets import Footer, Header, Input, Label, RichLog, Static

from app.pipeline import StageStatus, create_stages, run_stage


class StageCard(Static):
    """A single pipeline stage card."""

    def __init__(self, stage_name: str, index: int) -> None:
        super().__init__()
        self.stage_name = stage_name
        self.index = index

    def compose(self) -> ComposeResult:
        with Horizontal(classes="stage-row"):
            yield Label("○", id=f"icon-{self.index}", classes="stage-icon pending")
            yield Label(self.stage_name, classes="stage-name")
            yield Label("", id=f"time-{self.index}", classes="stage-time")

    def update_status(self, status: StageStatus, elapsed: float = 0.0):
        try:
            icon = self.query_one(f"#icon-{self.index}", Label)
            time_label = self.query_one(f"#time-{self.index}", Label)
        except NoMatches:
            return

        icon.remove_class("pending", "running", "completed", "failed")

        if status == StageStatus.PENDING:
            icon.update("○")
            icon.add_class("pending")
            time_label.update("")
        elif status == StageStatus.RUNNING:
            icon.update("◉")
            icon.add_class("running")
            time_label.update("running...")
        elif status == StageStatus.COMPLETED:
            icon.update("✓")
            icon.add_class("completed")
            time_label.update(self._format_time(elapsed))
        elif status == StageStatus.FAILED:
            icon.update("✗")
            icon.add_class("failed")
            time_label.update(self._format_time(elapsed))

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.0f}s"
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"


class PipelineApp(App):
    """Dev Pipeline TUI."""

    TITLE = "Dev Pipeline"
    CSS = """
    Screen {
        background: $surface;
    }

    #pipeline-container {
        height: auto;
        max-height: 14;
        padding: 1 2;
    }

    .stage-card {
        background: $panel;
        border: solid $primary-background;
        padding: 0 1;
        margin: 0 0 0 0;
        height: 3;
    }

    .stage-row {
        height: 3;
        align: left middle;
    }

    .stage-icon {
        width: 3;
        content-align: center middle;
    }

    .stage-icon.pending {
        color: $text-muted;
    }

    .stage-icon.running {
        color: $warning;
    }

    .stage-icon.completed {
        color: $success;
    }

    .stage-icon.failed {
        color: $error;
    }

    .stage-name {
        width: 1fr;
        content-align: left middle;
    }

    .stage-time {
        width: 12;
        content-align: right middle;
        color: $text-muted;
    }

    #prompt-input {
        margin: 1 2;
    }

    #log-container {
        margin: 0 2 1 2;
        height: 1fr;
        border: solid $primary-background;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        padding: 0 2;
        background: $panel;
        color: $text-muted;
    }

    .connector {
        height: 1;
        padding: 0 3;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear Log"),
    ]

    running = var(False)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(
            placeholder="Enter your task... (e.g. 'Add user authentication with JWT')",
            id="prompt-input",
        )
        with Vertical(id="pipeline-container"):
            stages = create_stages()
            for i, stage in enumerate(stages):
                yield StageCard(stage.name, i, classes="stage-card")
                if i < len(stages) - 1:
                    yield Label("  │", classes="connector")
        yield RichLog(id="log-container", highlight=True, markup=True)
        yield Label("Ready — enter a prompt and press Enter to start", id="status-bar")
        yield Footer()

    @on(Input.Submitted, "#prompt-input")
    def on_submit(self, event: Input.Submitted):
        if self.running or not event.value.strip():
            return
        self.run_pipeline(event.value.strip())

    @work(exclusive=True)
    async def run_pipeline(self, prompt: str):
        self.running = True
        log = self.query_one("#log-container", RichLog)
        status_bar = self.query_one("#status-bar", Label)
        prompt_input = self.query_one("#prompt-input", Input)
        prompt_input.disabled = True

        stages = create_stages()
        cards = self.query(StageCard)

        # Reset all cards
        for card in cards:
            card.update_status(StageStatus.PENDING)

        log.clear()
        log.write(f"[bold]Pipeline started:[/bold] {prompt}\n")

        import os
        working_dir = os.getcwd()
        prev_output = ""

        for i, stage in enumerate(stages):
            card = list(cards)[i]
            card.update_status(StageStatus.RUNNING)
            status_bar.update(f"Running: {stage.name}...")
            log.write(f"\n[bold yellow]▶ {stage.name}[/bold yellow]")

            output = await run_stage(stage, prompt, prev_output, working_dir)

            card.update_status(stage.status, stage.elapsed)

            if stage.status == StageStatus.COMPLETED:
                log.write(f"[green]✓ {stage.name}[/green] — {card._format_time(stage.elapsed)}")
                # Show first few lines of output
                preview = output[:500].strip()
                if preview:
                    log.write(f"[dim]{preview}[/dim]\n")
                prev_output = output
            else:
                log.write(f"[red]✗ {stage.name} failed:[/red] {stage.error}")
                status_bar.update(f"Failed at: {stage.name}")
                break
        else:
            status_bar.update("Pipeline completed successfully!")
            log.write("\n[bold green]All stages completed![/bold green]")

        prompt_input.disabled = False
        self.running = False

    def action_clear_log(self):
        self.query_one("#log-container", RichLog).clear()


def main():
    app = PipelineApp()
    app.run()


if __name__ == "__main__":
    main()
