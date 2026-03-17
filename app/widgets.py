"""TUI widgets and stage display constants."""

from collections import deque

import psutil
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Label, Sparkline, Static

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


class SystemMonitor(Static):
    """Real-time system resource monitor with sparkline charts."""

    HISTORY = 60

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cpu: deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self._ram: deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self._net_out: deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self._net_in: deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self._net_prev = psutil.net_io_counters()
        psutil.cpu_percent(interval=None)  # prime the counter

    def compose(self) -> ComposeResult:
        with Horizontal(classes="monitor-row"):
            yield Label("CPU ", classes="monitor-label")
            yield Sparkline(list(self._cpu), id="cpu-spark", summary_function=max, classes="monitor-spark")
            yield Label("0%", id="cpu-val", classes="monitor-val")
        with Horizontal(classes="monitor-row"):
            yield Label("RAM ", classes="monitor-label")
            yield Sparkline(list(self._ram), id="ram-spark", summary_function=max, classes="monitor-spark")
            yield Label("0%", id="ram-val", classes="monitor-val")
        with Horizontal(classes="monitor-row"):
            yield Label("↑   ", classes="monitor-label")
            yield Sparkline(list(self._net_out), id="net-out-spark", summary_function=max, classes="monitor-spark monitor-spark-net")
            yield Label("0 B/s", id="net-out-val", classes="monitor-val")
        with Horizontal(classes="monitor-row"):
            yield Label("↓   ", classes="monitor-label")
            yield Sparkline(list(self._net_in), id="net-in-spark", summary_function=max, classes="monitor-spark monitor-spark-net")
            yield Label("0 B/s", id="net-in-val", classes="monitor-val")

    def refresh_data(self) -> None:
        cpu = psutil.cpu_percent(interval=None)
        self._cpu.append(cpu)

        mem = psutil.virtual_memory()
        self._ram.append(mem.percent)

        net = psutil.net_io_counters()
        self._net_out.append(float(net.bytes_sent - self._net_prev.bytes_sent))
        self._net_in.append(float(net.bytes_recv - self._net_prev.bytes_recv))
        self._net_prev = net

        try:
            self.query_one("#cpu-spark", Sparkline).data = list(self._cpu)
            self.query_one("#cpu-val", Label).update(f"{cpu:.0f}%")
            self.query_one("#ram-spark", Sparkline).data = list(self._ram)
            self.query_one("#ram-val", Label).update(f"{mem.percent:.0f}%")
            self.query_one("#net-out-spark", Sparkline).data = list(self._net_out)
            self.query_one("#net-out-val", Label).update(self._fmt_bytes(self._net_out[-1]))
            self.query_one("#net-in-spark", Sparkline).data = list(self._net_in)
            self.query_one("#net-in-val", Label).update(self._fmt_bytes(self._net_in[-1]))
        except NoMatches:
            pass

    @staticmethod
    def _fmt_bytes(b: float) -> str:
        if b < 1024:
            return f"{b:.0f} B/s"
        if b < 1024 * 1024:
            return f"{b / 1024:.1f} KB/s"
        return f"{b / 1024 / 1024:.1f} MB/s"
