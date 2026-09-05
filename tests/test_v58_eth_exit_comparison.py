"""Normalized post-close comparison for the first V58 ETH lifecycle."""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec

import pytest


def test_compares_live_close_with_frozen_duration_controls() -> None:
    """Live and observer outcomes must be compared only in normalized bps."""
    module_name = "hypervector.research.v58_eth_exit_comparison"
    assert find_spec(module_name) is not None, "V58 ETH exit comparison is missing"
    builder = import_module(module_name).build_v58_eth_exit_comparison

    report = builder(_close_report(), _duration_report())

    assert report["mode"] == "v58_eth_first_live_exit_comparison_v1"
    assert report["contract"] == _report_only_contract()
    comparison = report["duration_comparison"]
    assert comparison["actual_live_native"]["net_return_bps"] == 260.0
    assert "actual_live_720m" not in comparison
    assert comparison["observer_240m"]["net_return_bps"] == 307.0
    assert comparison["observer_480m"]["net_return_bps"] == 234.0
    assert comparison["observer_720m"]["net_return_bps"] == 250.0
    assert isinstance(comparison["observer_720m"]["entry_time_ms"], int)
    assert isinstance(comparison["observer_720m"]["exit_time_ms"], int)
    assert comparison["actual_minus_observer_240m_bps"] == -47.0
    assert comparison["actual_minus_observer_480m_bps"] == 26.0
    assert comparison["actual_minus_observer_720m_bps"] == 10.0
    assert comparison["cross_notional_dollar_deltas_withheld"] is True
    assert report["profit_protection_alternatives"]["direct_ranking_withheld"] is True
    assert report["strategy_change_supported"] is False


def test_rejects_observer_control_with_wrong_duration() -> None:
    """A maximum-hold label cannot alias a non-720-minute observer path."""
    builder = import_module(
        "hypervector.research.v58_eth_exit_comparison"
    ).build_v58_eth_exit_comparison
    close = _close_report()
    observer = close["observer_comparison"]
    assert isinstance(observer, dict)
    observer["exit_time_ms"] = observer["entry_time_ms"] + 719 * 60_000

    with pytest.raises(ValueError, match="observer 720m control differs"):
        builder(close, _duration_report())


def test_accepts_first_causal_observation_after_frozen_720m_deadline() -> None:
    """A bounded post-deadline sample must retain its exact resolution delay."""
    builder = import_module(
        "hypervector.research.v58_eth_exit_comparison"
    ).build_v58_eth_exit_comparison
    close = _close_report()
    observer = close["observer_comparison"]
    assert isinstance(observer, dict)
    observer["exit_time_ms"] += 14_185

    report = builder(close, _duration_report())

    control = report["duration_comparison"]["observer_720m"]
    assert control["deadline_time_ms"] == 1787216124861
    assert control["resolution_delay_ms"] == 14_185


def _close_report() -> dict[str, object]:
    """Return one reconciled live-close fixture."""
    return {
        "schema_version": 1,
        "mode": "v58_eth_first_live_close_reconciliation_v1",
        "status": "reconciled",
        "frozen_identity": {
            "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
            "profile_fingerprint": "a" * 64,
            "run_id": "bidirectional-live-1787166474078",
            "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
            "route": "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
            "symbol": "ETH",
            "side": "long",
            "lifecycle_id": "ETH:520161109446",
        },
        "actual_live_close": {
            "exit_reason": "maximum_hold",
            "holding_time_ms": 43_205_000,
            "entry_notional_usd": 729.37513,
            "net_pnl_usd": 18.96375338,
            "net_return_on_entry_notional_bps": 260.0,
        },
        "observer_comparison": {
            "source_run_id": "bidirectional-observe-1787127644202",
            "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
            "symbol": "ETH",
            "side": "long",
            "decision_time_ms": 1787172900000,
            "notional_usd": 750.0,
            "entry_time_ms": 1787172924861,
            "exit_time_ms": 1787216124861,
            "exit_reason": "maximum_hold",
            "net_return_bps": 250.0,
            "simulated_net_pnl_usd": 18.75,
            "net_return_scope": "exact_depth_fee_and_funding",
            "actual_orders_or_fills_claimed": False,
        },
        "frozen_counterfactuals": {
            "r2_floor1_trail1": {"status": "triggered_before_current_boundary"},
            "r5_floor2_trail2": {"status": "triggered_before_current_boundary"},
        },
        "strategy_change_supported": False,
        "contract": _report_only_contract(),
    }


def _duration_report() -> dict[str, object]:
    """Return the frozen pre-close duration fixture."""
    return {
        "schema_version": 1,
        "mode": "v58_eth_fixed_entry_duration_checkpoint_v1",
        "execution_authority": "none",
        "strategy_change_supported": False,
        "source_lifecycle": {
            "source_run_id": "bidirectional-observe-1787127644202",
            "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
            "symbol": "ETH",
            "side": "long",
            "decision_time_ms": 1787172900000,
        },
        "duration_checkpoints": {
            "fixed_240m": _duration_row(240, 307.0),
            "fixed_480m": _duration_row(480, 234.0),
        },
        "retained_control": {
            "maximum_hold_minutes": 720,
            "deadline_time_ms": 1787216124861,
            "state": "awaiting_resolution",
        },
    }


def _duration_row(minutes: int, net_return_bps: float) -> dict[str, object]:
    """Return one resolved observer duration row."""
    return {
        "status": "resolved",
        "source_run_id": "bidirectional-observe-1787127644202",
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "side": "long",
        "maximum_hold_minutes": minutes,
        "entry_notional_usd": 750.0,
        "net_return_bps": net_return_bps,
        "simulated_net_pnl_usd": net_return_bps / 10_000.0 * 750.0,
        "net_return_scope": "exact_depth_fee_and_funding",
    }


def _report_only_contract() -> dict[str, object]:
    """Return the frozen report-only contract."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
        "approval_requested": False,
    }
