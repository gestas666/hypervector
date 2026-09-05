"""Tests for frozen BTC spot-lead catch-up economics."""

from __future__ import annotations

import importlib
import importlib.util

import pandas as pd
import pytest

from btc_spot_lead_catchup_fixtures import spot_lead_signal_bars


def test_btc_spot_lead_catchup_replay_module_exists() -> None:
    """The primary and controls require one shared economic replay."""
    assert (
        importlib.util.find_spec("hypervector.research.btc_spot_lead_catchup_replay")
        is not None
    )


def test_replay_preserves_all_three_signal_identities() -> None:
    """Use one economic contract without merging the primary or controls."""
    module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_replay"
    )
    assert hasattr(module, "evaluate_btc_spot_lead_catchup")
    perpetual, spot, _, _, _ = spot_lead_signal_bars()

    result = module.evaluate_btc_spot_lead_catchup(perpetual, spot, 2.0)

    assert result.candidate_signal_count == 1
    assert result.native_control_signal_count == 1
    assert result.placebo_signal_count == 1
    for report in (
        result.candidate_report,
        result.native_control_report,
        result.placebo_report,
    ):
        assert {trade.direction for trade in report.trades} <= {"long"}
    assert result.execution_authority == "none"


def test_delay_stress_moves_every_signal_one_complete_minute() -> None:
    """Delay execution without changing any underlying event identity."""
    module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_replay"
    )
    assert hasattr(module, "evaluate_btc_spot_lead_catchup")
    perpetual, spot, candidate, placebo, native = spot_lead_signal_bars()

    result = module.evaluate_btc_spot_lead_catchup(
        perpetual,
        spot,
        2.0,
        entry_delay_minutes=1,
    )

    minute = pd.Timedelta(minutes=1)
    assert result.candidate_signal_times_utc == ((candidate + minute).isoformat(),)
    assert result.placebo_signal_times_utc == ((placebo + minute).isoformat(),)
    assert result.native_control_signal_times_utc == ((native + minute).isoformat(),)


def test_replay_rejects_unregistered_cost_or_delay_values() -> None:
    """Prevent outcome-driven friction and entry-timing changes."""
    module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_replay"
    )
    assert hasattr(module, "evaluate_btc_spot_lead_catchup")
    perpetual, spot, _, _, _ = spot_lead_signal_bars()
    with pytest.raises(ValueError, match="slippage"):
        module.evaluate_btc_spot_lead_catchup(perpetual, spot, -1.0)
    with pytest.raises(ValueError, match="delay"):
        module.evaluate_btc_spot_lead_catchup(
            perpetual,
            spot,
            2.0,
            entry_delay_minutes=2,
        )
