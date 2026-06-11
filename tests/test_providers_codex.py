from pathlib import Path

from app.providers.codex import parse_codex_jsonl

FIXTURES = Path(__file__).parent / "fixtures"


def _lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text().splitlines()


def test_parse_success_extracts_agent_message_and_no_cost():
    # codex.jsonl is derived from OpenAI's documented exec --json schema
    # (success path not capturable on a ChatGPT-account Codex — see learnings.txt).
    result = parse_codex_jsonl(_lines("codex.jsonl"))
    assert result.success is True
    assert result.output == "ok"
    assert result.cost_usd is None


def test_parse_real_error_capture_marks_failure_with_readable_message():
    # codex_error.jsonl is a REAL captured failure from `codex exec --json`.
    result = parse_codex_jsonl(_lines("codex_error.jsonl"))
    assert result.success is False
    assert "not supported" in result.error
    assert result.cost_usd is None
