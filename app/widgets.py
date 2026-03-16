"""TUI widgets and stage display constants."""

from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Label, Static

from app.stages import StageStatus

STAGE_SHORT_NAMES = {
    "Planning": "Plan",
    "Decomposition": "Decomp",
    "Implementation": "Impl",
    "Tests & Validation": "Tests",
    "Code Quality": "Quality",
    "Documentation": "Docs",
    "Commit & PR": "PR",
}

# Execution order of stages as they appear visually (pill index = list index).
RERUN_ORDER = [
    "Planning",
    "Decomposition",
    "Implementation",
    "Tests & Validation",
    "Code Quality",
    "Documentation",
    "Commit & PR",
]

# Which stage's output is used as prev_output when entering each stage.
STAGE_PREV: dict[str, str | None] = {
    "Planning": None,
    "Decomposition": "Planning",
    "Implementation": "Planning",
    "Tests & Validation": "Implementation",
    "Code Quality": "Tests & Validation",
    "Documentation": "Code Quality",
    "Commit & PR": "Documentation",
}


class StagePill(Static):
    """Rounded-box stage card for the horizontal pipeline bar."""

    class Clicked(Message):
        def __init__(self, stage_name: str, index: int) -> None:
            super().__init__()
            self.stage_name = stage_name
            self.index = index

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.stage_name, self.index))

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
