"""Tests for the complete BTC spot-lead result matrix."""

from __future__ import annotations

import importlib
import importlib.util

import pytest

from btc_spot_lead_catchup_fixtures import spot_lead_signal_bars


def test_btc_spot_lead_catchup_experiment_module_exists() -> None:
    """The preregistered matrix needs a fail-closed report builder."""
    assert (
        importlib.util.find_spec(
            "hypervector.research.btc_spot_lead_catchup_experiment"
        )
        is not None
    )


def test_report_publishes_all_arms_and_rejects_sparse_results() -> None:
    """Retain losing or sparse results without hiding any control."""
    module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_experiment"
    )
    replay_module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_replay"
    )
    assert hasattr(module, "BtcSpotLeadCatchupCell")
    assert hasattr(module, "build_btc_spot_lead_catchup_report")
    perpetual, spot, _, _, _ = spot_lead_signal_bars()
    cells = []
    scenarios = {
        "nominal": (2.0, 0),
        "stress": (5.0, 0),
        "one_minute_entry_delay": (2.0, 1),
    }
    for partition in ("development", "validation", "pseudo_holdout"):
        for scenario, (slippage, delay) in scenarios.items():
            replay = replay_module.evaluate_btc_spot_lead_catchup(
                perpetual,
                spot,
                slippage,
                entry_delay_minutes=delay,
            )
            cells.append(
                module.BtcSpotLeadCatchupCell(partition, scenario, 90.0, replay)
            )

    result = module.build_btc_spot_lead_catchup_report(cells)

    assert len(result.report["summary_rows"]) == 36
    assert len(result.report["comparisons"]) == 9
    assert not result.report["acceptance"]["candidate_supported"]
    assert (
        "validation_minimum_thirteen_trades"
        in result.report["acceptance"]["failed_checks"]
    )
    assert not result.report["acceptance"]["live_promotion_authorized"]
    assert result.report["authority"]["execution_authority"] == "none"
    assert result.trade_rows


def test_report_rejects_an_incomplete_matrix() -> None:
    """Missing partitions or scenarios must fail instead of disappearing."""
    module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_experiment"
    )
    replay_module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_replay"
    )
    assert hasattr(module, "BtcSpotLeadCatchupCell")
    assert hasattr(module, "build_btc_spot_lead_catchup_report")
    perpetual, spot, _, _, _ = spot_lead_signal_bars()
    replay = replay_module.evaluate_btc_spot_lead_catchup(perpetual, spot, 2.0)
    cell = module.BtcSpotLeadCatchupCell("development", "nominal", 90.0, replay)

    with pytest.raises(ValueError, match="incomplete"):
        module.build_btc_spot_lead_catchup_report([cell])
