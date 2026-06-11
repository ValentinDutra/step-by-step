from pathlib import Path

from app.providers.gemini import parse_gemini_json, parse_gemini_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_json_extracts_response_no_cost():
    # gemini.json is a REAL capture from `gemini --output-format json`.
    text = (FIXTURES / "gemini.json").read_text()
    result = parse_gemini_json(text)
    assert result.success is True
    assert result.output == "ok"
    assert result.cost_usd is None


def test_malformed_json_fails_and_text_fallback_recovers():
    text = (FIXTURES / "gemini_malformed.txt").read_text()
    # The JSON parser rejects non-JSON output...
    assert parse_gemini_json(text).success is False
    # ...and the text fallback recovers the raw stdout.
    fallback = parse_gemini_text(text)
    assert fallback.success is True
    assert "oops" in fallback.output
    assert fallback.cost_usd is None
