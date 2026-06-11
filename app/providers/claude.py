"""Claude Code CLI provider."""

import asyncio
import json

from app.models import pipeline_stats
from app.providers.base import ProviderResult


def parse_claude_stream_json(lines: list[str]) -> ProviderResult:
    """Parse Claude Code ``stream-json`` lines into a :class:`ProviderResult`.

    Only the terminal ``result`` event matters here — it carries the final
    output, the dollar cost, and the error state. Streamed ``assistant`` events
    are surfaced live by the caller and ignored here.
    """
    final_output = ""
    cost_usd = 0.0
    is_error = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if event.get("type") == "result":
            final_output = event.get("result", "") or final_output
            cost_usd = float(event.get("total_cost_usd") or 0.0)
            if event.get("subtype") == "error" or event.get("is_error"):
                is_error = True
    if is_error:
        message = final_output or "Claude returned an error"
        return ProviderResult(False, message, error=message, cost_usd=cost_usd)
    return ProviderResult(True, final_output, cost_usd=cost_usd)


async def _emit(on_stream, chunk: str) -> None:
    if not on_stream:
        return
    if asyncio.iscoroutinefunction(on_stream):
        await on_stream(chunk)
    else:
        on_stream(chunk)


class ClaudeProvider:
    """Runs a prompt through the ``claude`` CLI in stream-json mode."""

    name = "claude"

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
        cmd = ["claude", "--print"]
        if self.skip_permissions:
            cmd.append("--dangerously-skip-permissions")
        cmd += ["--output-format", "stream-json", "--verbose"]
        if self.model:
            cmd += ["--model", self.model]
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
                            if event.get("type") == "assistant":
                                for block in event.get("message", {}).get("content", []):
                                    if block.get("type") == "text":
                                        await _emit(on_stream, block["text"])
            except asyncio.TimeoutError:
                return ProviderResult(
                    False, "", error=f"Timeout after {self.timeout_seconds}s", cost_usd=None
                )

            await stderr_task
            stderr_task = None
            await proc.wait()

            result = parse_claude_stream_json(lines)

            if proc.returncode != 0 and not result.output:
                stderr_data = b"".join(stderr_chunks).decode().strip()
                error = stderr_data or f"Exit code {proc.returncode}"
                return ProviderResult(False, "", error=error, cost_usd=None)

            pipeline_stats.add_call(result.cost_usd)
            return result

        except FileNotFoundError:
            return ProviderResult(
                False,
                "",
                error="'claude' CLI not found. Install: npm install -g @anthropic-ai/claude-code",
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
