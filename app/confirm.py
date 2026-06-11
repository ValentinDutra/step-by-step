"""Modal confirmation screens for pipeline checkpoints."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Label, Static

from app.models import Task


class ConfirmScreen(ModalScreen[bool]):
    """Scrollable confirmation dialog resolving to True (continue) or False (cancel)."""

    BINDINGS = [
        Binding("enter", "confirm", "Continue"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-panel"):
            yield Label(self._title, id="confirm-title")
            with VerticalScroll(id="confirm-body-scroll"):
                yield Static(self._body, id="confirm-body")
            with Horizontal(id="confirm-buttons"):
                yield Button("Continue", variant="primary", id="confirm-continue")
                yield Button("Cancel", variant="error", id="confirm-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-continue")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class TaskReviewScreen(ModalScreen[list[int] | None]):
    """Checkbox review of decomposed subtasks.

    Resolves to the selected task ids (Continue) or ``None`` (Cancel).
    """

    BINDINGS = [
        Binding("enter", "confirm", "Continue"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, tasks: list[Task]) -> None:
        super().__init__()
        self._tasks = tasks

    def compose(self) -> ComposeResult:
        with Vertical(id="task-review-panel"):
            yield Label(
                "Review subtasks before the parallel fan-out", id="task-review-title"
            )
            with VerticalScroll(id="task-review-scroll"):
                for task in self._tasks:
                    files = ", ".join(task.files) if task.files else "—"
                    yield Checkbox(
                        f"#{task.id} {task.description} ({files})",
                        value=True,
                        id=f"task-checkbox-{task.id}",
                    )
            with Horizontal(id="task-review-buttons"):
                yield Button("Continue", variant="primary", id="task-review-continue")
                yield Button("Cancel", variant="error", id="task-review-cancel")

    def _selected_ids(self) -> list[int]:
        return [
            task.id
            for task in self._tasks
            if self.query_one(f"#task-checkbox-{task.id}", Checkbox).value
        ]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "task-review-continue":
            self.dismiss(self._selected_ids())
        else:
            self.dismiss(None)

    def action_confirm(self) -> None:
        self.dismiss(self._selected_ids())

    def action_cancel(self) -> None:
        self.dismiss(None)
