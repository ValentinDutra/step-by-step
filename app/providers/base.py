"""The uniform contract every LLM CLI backend implements."""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ProviderResult:
    """Outcome of a single provider invocation.

    ``cost_usd`` is ``None`` when the underlying CLI does not report a dollar
    cost (Codex, Gemini); only Claude returns a real figure.
    """

    success: bool
    output: str
    error: str = ""
    cost_usd: float | None = None


class LLMProvider(Protocol):
    """A backend that runs a prompt through one LLM CLI.

    Implementations stream text chunks to ``on_stream(chunk: str)`` when given
    (the callback may be sync or async) and return a :class:`ProviderResult`.
    """

    name: str

    async def run(
        self, prompt: str, working_dir: str, on_stream=None
    ) -> ProviderResult: ...
