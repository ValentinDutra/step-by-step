"""Pure helpers derived from a resolved pipeline (a list of ``Stage``)."""

from app.stages import Stage


def rerun_order(stages: list[Stage]) -> list[str]:
    """The phase names in pipeline order."""
    return [stage.name for stage in stages]


def stage_prev(stages: list[Stage]) -> dict[str, str | None]:
    """Map each phase name to the name of the phase before it (``None`` for the
    first phase)."""
    previous_name: str | None = None
    mapping: dict[str, str | None] = {}
    for stage in stages:
        mapping[stage.name] = previous_name
        previous_name = stage.name
    return mapping


def gate_loopback_target(stages: list[Stage], gate_index: int) -> int | None:
    """Index of the nearest ``decompose`` stage before ``gate_index``, or
    ``None`` when no decompose precedes the gate (the gate then runs once)."""
    for index in range(gate_index - 1, -1, -1):
        if stages[index].kind == "decompose":
            return index
    return None
