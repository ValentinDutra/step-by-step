"""Modal confirmation screens for pipeline checkpoints."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


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
