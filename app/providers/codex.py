"""OpenAI Codex CLI provider (``codex exec``)."""

import asyncio
import json

from app.models import pipeline_stats
from app.providers.base import ProviderResult


def _extract_codex_error(message: str) -> str:
    """Codex wraps API errors as a JSON string inside ``message``; unwrap it."""
    if not message:
        return ""
    try:
        inner = json.loads(message)
    except (json.JSONDecodeError, TypeError):
        return message
    if isinstance(inner, dict):
        err = inner.get("error")
        if isinstance(err, dict) and err.get("message"):
            return err["message"]
        if inner.get("message"):
            return inner["message"]
    return message


def parse_codex_jsonl(lines: list[str]) -> ProviderResult:
    """Parse ``codex exec --json`` thread events into a :class:`ProviderResult`.

    The final answer is the text of ``item.completed`` events whose item type is
    ``agent_message``. ``error``/``turn.failed`` events mark failure. Codex
    reports token usage, not dollars, so ``cost_usd`` is always ``None``.
    """
    output_parts: list[str] = []
    error_message = ""
    failed = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        etype = event.get("type")
        if etype == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                text = item.get("text", "")
                if text:
                    output_parts.append(text)
        elif etype == "error":
            failed = True
            error_message = _extract_codex_error(event.get("message", "")) or error_message
        elif etype == "turn.failed":
            failed = True
            err = event.get("error", {}) or {}
            error_message = _extract_codex_error(err.get("message", "")) or error_message

    output = "\n".join(output_parts).strip()
    if failed:
        return ProviderResult(
            False, output, error=error_message or "Codex turn failed", cost_usd=None
        )
    return ProviderResult(True, output, cost_usd=None)


async def _emit(on_stream, chunk: str) -> None:
    if not on_stream:
        return
    if asyncio.iscoroutinefunction(on_stream):
        await on_stream(chunk)
    else:
        on_stream(chunk)


class CodexProvider:
    """Runs a prompt through ``codex exec`` in JSONL streaming mode."""

    name = "codex"

    def __init__(
        self,
        model: str = "",
        timeout_seconds: int = 600,
        skip_permissions: bool = True,
        extra_args: tuple[str, ...] = (),
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.skip_permissions = skip_permissions
        self.extra_args = tuple(extra_args)

    def _build_cmd(self) -> list[str]:
        cmd = ["codex", "exec", "-", "--json"]
        if self.skip_permissions:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        if self.model:
            cmd += ["-m", self.model]
        cmd += list(self.extra_args)
        return cmd

    async def run(
        self, prompt: str, working_dir: str, on_stream=None
    ) -> ProviderResult:
        cmd = self._build_cmd()

        proc = None
        stderr_task: asyncio.Task | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )

            proc.stdin.write(prompt.encode())
            await proc.stdin.drain()
            proc.stdin.close()

            stderr_chunks: list[bytes] = []

            async def _drain_stderr() -> None:
                while True:
                    chunk = await proc.stderr.read(4096)
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)

            stderr_task = asyncio.create_task(_drain_stderr())

            lines: list[str] = []
            buf = b""
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    while True:
                        raw_chunk = await proc.stdout.read(65536)
                        if not raw_chunk:
                            break
                        buf += raw_chunk
                        while b"\n" in buf:
                            raw_line, buf = buf.split(b"\n", 1)
                            line = raw_line.decode(errors="replace").strip()
                            if not line:
                                continue
                            lines.append(line)
                            try:
                                event = json.loads(line)
                            except (json.JSONDecodeError, TypeError):
                                continue
                            if event.get("type") == "item.completed":
                                item = event.get("item", {})
                                if item.get("type") == "agent_message":
                                    await _emit(on_stream, item.get("text", ""))
            except asyncio.TimeoutError:
                return ProviderResult(
                    False, "", error=f"Timeout after {self.timeout_seconds}s", cost_usd=None
                )

            await stderr_task
            stderr_task = None
            await proc.wait()

            result = parse_codex_jsonl(lines)

            if not result.success:
                # The turn ran but the model/turn failed; count it like Claude
                # counts result-errors. Spawn/crash failures (below) are not counted.
                pipeline_stats.add_call(None)
                return result
            if proc.returncode != 0 and not result.output:
                stderr_data = b"".join(stderr_chunks).decode().strip()
                error = stderr_data or f"Exit code {proc.returncode}"
                return ProviderResult(False, "", error=error, cost_usd=None)

            pipeline_stats.add_call(None)
            return result

        except FileNotFoundError:
            return ProviderResult(
                False,
                "",
                error="'codex' CLI not found. Install: npm install -g @openai/codex",
                cost_usd=None,
            )
        except Exception as exc:  # noqa: BLE001 — surface any spawn failure as a result
            return ProviderResult(False, "", error=str(exc), cost_usd=None)
        finally:
            if stderr_task is not None and not stderr_task.done():
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass
            if proc is not None and proc.returncode is None:
                proc.kill()
                try:
                    await proc.wait()
                except Exception:
                    pass
