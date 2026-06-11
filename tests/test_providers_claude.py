from pathlib import Path

import pytest

from app.providers.claude import parse_claude_stream_json

FIXTURES = Path(__file__).parent / "fixtures"


def _lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text().splitlines()


def test_parse_success_extracts_output_and_cost():
    result = parse_claude_stream_json(_lines("claude_stream.jsonl"))
    assert result.success is True
    assert result.output == "Done: created foo.py"
    assert result.cost_usd == pytest.approx(0.0123)


def test_parse_error_event_marks_failure():
    result = parse_claude_stream_json(_lines("claude_error.jsonl"))
    assert result.success is False
    assert "Something failed" in result.output
    assert result.cost_usd == pytest.approx(0.004)
