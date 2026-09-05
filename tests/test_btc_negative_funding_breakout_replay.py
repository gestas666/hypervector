from __future__ import annotations

import importlib

import pandas as pd
import pytest

from btc_negative_funding_breakout_fixtures import (
    negative_funding_breakout_bars,
)


def test_replay_preserves_candidate_and_control_signal_identity() -> None:
    """Replay the filtered and unfiltered arms under one economic contract."""
    module = importlib.import_module(
        "hypervector.research.btc_negative_funding_breakout_replay"
    )
    bars, funding, _, _ = negative_funding_breakout_bars()
    bars["funding_rate"] = 0.0
    result = module.evaluate_btc_negative_funding_breakout(bars, funding, 2.0)
    assert result.candidate_signal_count == 1
    assert result.control_signal_count == 2
    assert {trade.direction for trade in result.candidate_report.trades} <= {"long"}
    assert {trade.direction for trade in result.control_report.trades} <= {"long"}
    assert result.execution_authority == "none"


def test_delay_stress_moves_signal_one_complete_minute() -> None:
    """Apply the preregistered delay without changing the underlying event set."""
    module = importlib.import_module(
        "hypervector.research.btc_negative_funding_breakout_replay"
    )
    bars, funding, _, negative_time = negative_funding_breakout_bars()
    bars["funding_rate"] = 0.0
    result = module.evaluate_btc_negative_funding_breakout(
        bars,
        funding,
        2.0,
        entry_delay_minutes=1,
    )
    assert result.candidate_signal_times_utc == (
        (negative_time + pd.Timedelta(minutes=1)).isoformat(),
    )


def test_replay_rejects_unregistered_cost_or_delay_values() -> None:
    """Prevent outcome-driven cost and entry-timing changes."""
    module = importlib.import_module(
        "hypervector.research.btc_negative_funding_breakout_replay"
    )
    bars, funding, _, _ = negative_funding_breakout_bars()
    bars["funding_rate"] = 0.0
    with pytest.raises(ValueError, match="slippage"):
        module.evaluate_btc_negative_funding_breakout(bars, funding, -1.0)
    with pytest.raises(ValueError, match="delay"):
        module.evaluate_btc_negative_funding_breakout(
            bars,
            funding,
            2.0,
            entry_delay_minutes=2,
        )
