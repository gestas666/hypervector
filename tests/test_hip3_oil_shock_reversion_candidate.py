"""Tests for exact HIP-3 oil shock-reversion portfolio evaluation."""

from __future__ import annotations

from importlib import import_module, util

import pandas as pd

from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_candidate import MuChronologicalWindows


_MODULE = "hypervector.research.hip3_oil_shock_reversion_candidate"


def _development_bars() -> tuple[pd.DataFrame, MuChronologicalWindows]:
    index = pd.date_range("2026-06-01", periods=18, freq="5min", tz="UTC")
    signal_close = [100.0] * 6 + [90.0, 90.0, 110.0] + [110.0] * 9
    bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.2,
            "low": 99.8,
            "close": 100.0,
            "signal_open": signal_close,
            "signal_high": signal_close,
            "signal_low": signal_close,
            "signal_close": signal_close,
            "signal_gap_before_bars": 0,
            "signal_ohlc_source": "0xarchive_public_trade_ohlc_v1",
            "signal_ohlc_synthetic_no_trade": False,
            "entry_bid": 99.99,
            "entry_ask": 100.01,
            "decision_bid": 99.99,
            "decision_ask": 100.01,
            "decision_imbalance_10": 0.0,
            "first_boundary_delay_ms": 100.0,
            "end_boundary_age_ms": 100.0,
            "maximum_snapshot_interval_ms": 100.0,
            "source_snapshot_count": 10,
            "gap_before_bars": 0,
            "funding_rate": 0.0,
            "risk_high": 100.5,
            "risk_low": 99.5,
            "entry_risk_high": 100.5,
            "entry_risk_low": 99.5,
            "risk_path_source": ("0xarchive_mark_price_with_public_trade_context_v1"),
            "mark_path_complete": True,
            "maximum_mark_interval_ms": 100.0,
            "trade_bundle_complete": True,
            "entry_mark_path_complete": True,
            "entry_maximum_mark_interval_ms": 100.0,
        },
        index=index,
    )
    development_end = index[12]
    windows = MuChronologicalWindows(
        index[0],
        development_end,
        index[15],
        index[-1] + pd.Timedelta(minutes=5),
        (
            (index[0], index[4]),
            (index[4], index[8]),
            (index[8], development_end),
        ),
    )
    return bars, windows


def _execution() -> MuArchiveExecution:
    return MuArchiveExecution(
        effective_taker_fee_rate=0.0000864,
        notional_usd=75.0,
        venue_max_leverage=20.0,
        nominal_latency_bps_per_side=1.0,
        stress_latency_bps_per_side=2.0,
        stress_visible_tail_bps_per_side=4.0,
        maximum_hold_bars=288,
        risk_high_column="risk_high",
        risk_low_column="risk_low",
        entry_risk_high_column="entry_risk_high",
        entry_risk_low_column="entry_risk_low",
        symbol="xyz:BRENTOIL",
    )


def test_portfolio_contract_uses_frozen_barriers_and_one_hour_fallback() -> None:
    """Underlying target/stop distances map correctly through five-times leverage."""
    spec = util.find_spec(_MODULE)
    assert spec is not None, "oil shock-reversion candidate module is missing"
    module = import_module(_MODULE)
    execution = MuArchiveExecution(
        effective_taker_fee_rate=0.0000864,
        notional_usd=75.0,
        venue_max_leverage=20.0,
        nominal_latency_bps_per_side=1.0,
        stress_latency_bps_per_side=2.0,
        stress_visible_tail_bps_per_side=4.0,
        symbol="xyz:BRENTOIL",
    )

    portfolio = module.hip3_oil_reversion_portfolio_config(
        execution,
        Hip3OilShockReversionConfig(),
        stress=False,
    )

    assert portfolio.target_margin_pct == 2.0
    assert portfolio.stop_margin_pct == 1.5
    assert portfolio.maximum_stop_distance_bps == 30.0
    assert portfolio.max_hold_bars == 12
    assert portfolio.max_hold_seconds == 3_600
    assert portfolio.margin_fraction == 0.03


def test_development_replay_uses_trade_ohlc_and_withholds_oos() -> None:
    """Exact public-trade shocks drive only development and its three folds."""
    module = import_module(_MODULE)
    bars, windows = _development_bars()
    signal = Hip3OilShockReversionConfig(
        return_lookback_bars=2,
        threshold_lookback_bars=4,
        minimum_history_bars=4,
        shock_quantile=0.75,
    )

    result = module.evaluate_hip3_oil_shock_reversion_development(
        bars,
        _execution(),
        windows=windows,
        signal=signal,
    )

    assert result.symbol == "xyz:BRENTOIL"
    assert result.execution == _execution()
    assert result.development.nominal.completed_trades > 0
    assert len(result.folds) == 3
    assert all(fold.name.startswith("development_fold_") for fold in result.folds)
    assert result.out_of_sample_economics == "WITHHELD_NOT_EVALUATED"
    assert result.execution_authority == "none"


def test_oil_path_contract_does_not_invent_pressure_dependency() -> None:
    """Trade-OHLC decisions need exact fills and marks, not L2 pressure age."""
    candidate = import_module(_MODULE)
    path = import_module("hypervector.research.hip3_oil_shock_reversion_path")
    bars, windows = _development_bars()
    bars.loc[bars.index[6], "end_boundary_age_ms"] = 20_000.0
    result = candidate.evaluate_hip3_oil_shock_reversion_development(
        bars,
        _execution(),
        windows=windows,
        signal=Hip3OilShockReversionConfig(
            return_lookback_bars=2,
            threshold_lookback_bars=4,
            minimum_history_bars=4,
            shock_quantile=0.75,
        ),
    )

    quality = path.oil_partition_trade_path_quality(
        bars.loc[bars.index < windows.development_end_utc],
        result.development,
    )

    assert quality["decision_l2_required"] is False
    assert quality["nominal"]["stale_l2_decision_trades"] == 0
    assert quality["status"] == "resolved"


def test_report_retains_folds_scaled_costs_and_no_live_authority() -> None:
    """The durable payload exposes robustness without opening OOS or execution."""
    candidate = import_module(_MODULE)
    friction_module = import_module(
        "hypervector.research.hip3_oil_shock_reversion_friction"
    )
    reporting = import_module("hypervector.research.hip3_oil_shock_reversion_reporting")
    bars, windows = _development_bars()
    result = candidate.evaluate_hip3_oil_shock_reversion_development(
        bars,
        _execution(),
        windows=windows,
        signal=Hip3OilShockReversionConfig(
            return_lookback_bars=2,
            threshold_lookback_bars=4,
            minimum_history_bars=4,
            shock_quantile=0.75,
        ),
    )
    friction = friction_module.Hip3OilFrictionContract(
        _execution(),
        500.0,
        5_000.0,
        750.0,
        3.0,
        5.0,
        4.0,
        7.0,
        0.5,
        1.0,
        8.46,
        6,
    )

    report = reporting.build_hip3_oil_development_report(
        result,
        bars.loc[bars.index < windows.development_end_utc],
        friction,
    )

    assert report["schema_version"] == "hip3_oil_shock_reversion_development_v1"
    assert len(report["development_folds"]) == 3
    assert report["scaled_account_hypothesis"]["notional_usd"] == 750.0
    applied = report["friction_contract"]["applied_strategy_execution"]
    assert applied["target_distance_bps"] == 40.0
    assert applied["stop_distance_bps"] == 30.0
    assert applied["maximum_hold_bars"] == 12
    assert applied["maximum_hold_seconds"] == 3_600
    assert applied["risk_high_column"] == "risk_high"
    assert applied["entry_risk_low_column"] == "entry_risk_low"
    assert "execution" not in report["friction_contract"]
    assert report["out_of_sample_economics"] == "WITHHELD_NOT_EVALUATED"
    assert report["validation_accessed"] is False
    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert any("6 sparse mixed-strategy" in item for item in report["limitations"])
