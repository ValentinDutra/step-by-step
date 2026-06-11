import pytest

from app.models import PipelineStats


def test_add_call_accumulates_known_cost_and_counts_none():
    stats = PipelineStats()
    stats.add_call(0.30)
    stats.add_call(None)
    stats.add_call(0.12)
    stats.add_call(None)
    assert stats.total_calls == 4
    assert stats.total_cost_usd == pytest.approx(0.42)
    assert stats.calls_without_cost == 2


def test_format_cost_marks_unknown_calls():
    stats = PipelineStats()
    stats.add_call(0.42)
    assert stats.format_cost() == "$0.4200"
    stats.add_call(None)
    stats.add_call(None)
    assert stats.format_cost() == "$0.4200 (+2 n/a)"


def test_reset_clears_calls_without_cost():
    stats = PipelineStats()
    stats.add_call(None)
    stats.reset()
    assert stats.calls_without_cost == 0
    assert stats.format_cost() == "$0.0000"
