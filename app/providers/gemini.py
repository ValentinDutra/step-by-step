"""Google Gemini CLI provider."""

import asyncio
import json
import os

from app.models import pipeline_stats
from app.providers.base import ProviderResult


def parse_gemini_json(text: str) -> ProviderResult:
    """Parse the single buffered JSON object ``gemini --output-format json`` emits.

    Shape: ``{"session_id": ..., "response": "...", "stats": {...}}``. An
    ``error`` object marks failure. Gemini reports token stats, not dollars, so
    ``cost_usd`` is always ``None``.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ProviderResult(False, "", error="Gemini returned malformed JSON", cost_usd=None)
    if not isinstance(data, dict):
        return ProviderResult(False, "", error="Gemini returned unexpected JSON", cost_usd=None)
    error = data.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else str(error)
        return ProviderResult(
            False, data.get("response", "") or "", error=message or "Gemini error", cost_usd=None
        )
    return ProviderResult(True, data.get("response", ""), cost_usd=None)


def parse_gemini_text(text: str) -> ProviderResult:
    """Fallback parser: treat raw stdout as the output (``--output-format text``)."""
    output = text.strip()
    if not output:
        return ProviderResult(False, "", error="Gemini produced no output", cost_usd=None)
    return ProviderResult(True, output, cost_usd=None)


async def _emit(on_stream, chunk: str) -> None:
    if not on_stream or not chunk:
        return
    if asyncio.iscoroutinefunction(on_stream):
        await on_stream(chunk)
    else:
        on_stream(chunk)


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


class GeminiProvider:
    """Runs a prompt through the ``gemini`` CLI in headless mode.

    ``--output-format json`` is buffered (one object), so there is no
    incremental streaming; the full response is emitted once at completion.
    """

    name = "gemini"

    def __init__(self, model: str = "", timeout_seconds: int = 600) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def _spawn(
        self, args: list[str], working_dir: str
    ) -> tuple[int | None, str, str]:
        """Run ``gemini`` once. Returns (returncode, stdout, stderr).

        ``returncode is None`` signals a spawn-level failure (binary missing,
        timeout) with the message in the stderr slot.
        """
        env = {**os.environ, "GEMINI_CLI_TRUST_WORKSPACE": "true"}
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                env=env,
            )
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    stdout, stderr = await proc.communicate()
            except asyncio.TimeoutError:
                return None, "", f"Timeout after {self.timeout_seconds}s"
            return (
                proc.returncode,
                stdout.decode(errors="replace"),
                stderr.decode(errors="replace"),
            )
        except FileNotFoundError:
            return None, "", "'gemini' CLI not found. Install: npm install -g @google/gemini-cli"
        except Exception as exc:  # noqa: BLE001 — surface any spawn failure
            return None, "", str(exc)
        finally:
            if proc is not None and proc.returncode is None:
                proc.kill()
                try:
                    await proc.wait()
                except Exception:
                    pass

    async def run(
        self, prompt: str, working_dir: str, on_stream=None
    ) -> ProviderResult:
        base = ["gemini", "-p", prompt, "--yolo"]
        if self.model:
            base += ["-m", self.model]

        rc, out, err = await self._spawn(base + ["--output-format", "json"], working_dir)
        if rc is None:
            return ProviderResult(False, "", error=err, cost_usd=None)

        if _is_json(out.strip()):
            result = parse_gemini_json(out)
        else:
            # Buffered JSON came back malformed/empty (gemini-cli#9009): retry text.
            rc2, out2, err2 = await self._spawn(
                base + ["--output-format", "text"], working_dir
            )
            if rc2 is None:
                return ProviderResult(False, "", error=err2, cost_usd=None)
            result = parse_gemini_text(out2)
            if not result.output and rc2 != 0:
                return ProviderResult(
                    False, "", error=err2.strip() or f"Exit code {rc2}", cost_usd=None
                )

        await _emit(on_stream, result.output)
        pipeline_stats.add_call(None)
        return result
