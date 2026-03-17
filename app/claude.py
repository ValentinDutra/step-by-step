"""Claude CLI invocation and iteration evaluation."""

import asyncio
import json

_CLAUDE_TIMEOUT = 600  # seconds per subprocess call


async def call_claude(
    prompt: str,
    working_dir: str,
    on_stream=None,
) -> tuple[bool, str, float]:
    """Call Claude CLI and return (success, output, cost_usd).

    Streams output chunks to on_stream(chunk: str) if provided.
    Drains stderr concurrently to prevent pipe deadlock.
    Always cleans up the subprocess on exit.
    """
    proc = None
    stderr_task: asyncio.Task | None = None

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            "--output-format",
            "stream-json",
            "--verbose",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        proc.stdin.write(prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()

        final_output = ""
        cost_usd = 0.0
        early_result: tuple[bool, str, float] | None = None

        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    break
                stderr_chunks.append(chunk)

        stderr_task = asyncio.create_task(_drain_stderr())

        buf = b""
        try:
            async with asyncio.timeout(_CLAUDE_TIMEOUT):
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
                        try:
                            event = json.loads(line)
                            etype = event.get("type")
                            if etype == "assistant" and on_stream:
                                for block in event.get("message", {}).get("content", []):
                                    if block.get("type") == "text":
                                        chunk = block["text"]
                                        if asyncio.iscoroutinefunction(on_stream):
                                            await on_stream(chunk)
                                        else:
                                            on_stream(chunk)
                            elif etype == "result":
                                final_output = event.get("result", "")
                                cost_usd = float(event.get("total_cost_usd") or 0.0)
                                if event.get("subtype") == "error" or event.get("is_error"):
                                    early_result = (
                                        False,
                                        final_output or "Claude returned an error",
                                        cost_usd,
                                    )
                        except (json.JSONDecodeError, KeyError, TypeError):
                            pass
                    if early_result:
                        break
        except asyncio.TimeoutError:
            return False, f"Timeout after {_CLAUDE_TIMEOUT}s", 0.0

        await stderr_task
        stderr_task = None
        await proc.wait()

        if early_result:
            from app.models import pipeline_stats
            pipeline_stats.add_call(early_result[2])
            return early_result

        if proc.returncode != 0 and not final_output:
            stderr_data = b"".join(stderr_chunks)
            err = stderr_data.decode().strip() or f"Exit code {proc.returncode}"
            return False, err, 0.0

        from app.models import pipeline_stats
        pipeline_stats.add_call(cost_usd)
        return True, final_output, cost_usd

    except FileNotFoundError:
        return (
            False,
            "'claude' CLI not found. Install: npm install -g @anthropic-ai/claude-code",
            0.0,
        )
    except Exception as e:
        return False, str(e), 0.0
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


async def evaluate_should_iterate(stage_output: str, working_dir: str) -> bool:
    """Ask Claude whether the stage output has issues that require another iteration."""
    prompt = (
        "You are a quality gate agent. Review the following stage output and decide "
        "whether it contains genuine issues that require another implementation iteration.\n\n"
        "Answer ONLY with 'yes' if there are real issues that need fixing, "
        "or 'no' if the output is satisfactory and the pipeline can proceed.\n\n"
        f"STAGE OUTPUT:\n{stage_output[:4000]}"
    )
    success, response, _ = await call_claude(prompt, working_dir)
    if not success:
        return False
    return response.strip().lower().startswith("yes")
