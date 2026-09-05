"""Development-only replay tests for the frozen BRENTOIL Krown challenger."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.hip3_krown_trend_resumption_candidate import (
    evaluate_hip3_krown_trend_resumption_development,
    hip3_krown_trend_resumption_portfolio_config,
)
from hypervector.research.hip3_krown_trend_resumption_reporting import (
    build_hip3_krown_development_report,
)
from hypervector.research.hip3_krown_trend_resumption_signals import (
    Hip3KrownTrendResumptionConfig,
)
from hypervector.research.hip3_oil_shock_reversion_friction import (
    Hip3OilFrictionContract,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution
from hypervector.research.mu_hip3_candidate import MuChronologicalWindows


def _signal_close() -> np.ndarray:
    """Return a warm trend, shallow pullback, and resumption path."""
    return np.concatenate(
        [
            np.linspace(100.0, 116.0, 80),
            np.linspace(116.0, 114.0, 12),
            np.linspace(114.0, 121.0, 28),
            np.linspace(121.0, 117.0, 40),
        ]
    )


def _bars() -> tuple[pd.DataFrame, MuChronologicalWindows]:
    """Return exact-shape archive rows and canonical synthetic windows."""
    close = _signal_close()
    index = pd.date_range("2026-06-01", periods=len(close), freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "signal_open": close,
            "signal_high": close + 0.1,
            "signal_low": close - 0.1,
            "signal_close": close,
            "signal_gap_before_bars": 0,
            "signal_ohlc_source": "0xarchive_public_trade_ohlc_v1",
            "signal_ohlc_synthetic_no_trade": False,
            "entry_bid": close - 0.01,
            "entry_ask": close + 0.01,
            "decision_bid": close - 0.01,
            "decision_ask": close + 0.01,
            "decision_imbalance_10": 0.0,
            "first_boundary_delay_ms": 100.0,
            "end_boundary_age_ms": 100.0,
            "maximum_snapshot_interval_ms": 100.0,
            "source_snapshot_count": 10,
            "gap_before_bars": 0,
            "funding_rate": 0.0,
            "risk_high": close + 0.2,
            "risk_low": close - 0.2,
            "entry_risk_high": close + 0.2,
            "entry_risk_low": close - 0.2,
            "risk_path_source": "0xarchive_mark_price_with_public_trade_context_v1",
            "mark_path_complete": True,
            "maximum_mark_interval_ms": 100.0,
            "trade_bundle_complete": True,
            "entry_mark_path_complete": True,
            "entry_maximum_mark_interval_ms": 100.0,
        },
        index=index,
    )
    windows = MuChronologicalWindows(
        index[0],
        index[120],
        index[140],
        index[-1] + pd.Timedelta(minutes=15),
        (
            (index[0], index[40]),
            (index[40], index[80]),
            (index[80], index[120]),
        ),
    )
    return bars, windows


def _execution() -> MuArchiveExecution:
    """Return the frozen normalized exact-venue execution contract."""
    return MuArchiveExecution(
        effective_taker_fee_rate=0.0000864,
        notional_usd=75.0,
        venue_max_leverage=20.0,
        nominal_latency_bps_per_side=1.2230537631076595,
        stress_latency_bps_per_side=1.2230537631076595,
        stress_visible_tail_bps_per_side=7.2415300230974085,
        fixed_stop_bps=80.0,
        maximum_hold_bars=96,
        risk_high_column="risk_high",
        risk_low_column="risk_low",
        entry_risk_high_column="entry_risk_high",
        entry_risk_low_column="entry_risk_low",
        symbol="xyz:BRENTOIL",
    )


def _friction() -> Hip3OilFrictionContract:
    """Return scaled reporting inputs bound to the execution object."""
    return Hip3OilFrictionContract(
        _execution(),
        500.0,
        5_000.0,
        750.0,
        3.0,
        5.0,
        1.728,
        4.174107526215319,
        0.864,
        1.2230537631076595,
        8.464583786205068,
        6,
    )


def test_portfolio_contract_has_no_target_and_uses_24_hour_safety() -> None:
    """The primary exit stays signal-driven under the frozen stop/time fallback."""
    portfolio = hip3_krown_trend_resumption_portfolio_config(
        _execution(), Hip3KrownTrendResumptionConfig(), stress=False
    )

    assert portfolio.target_margin_pct is None
    assert portfolio.stop_margin_pct == 4.0
    assert portfolio.maximum_stop_distance_bps == 80.0
    assert portfolio.max_hold_bars == 96
    assert portfolio.max_hold_seconds == 86_400
    assert portfolio.margin_fraction == 0.03
    assert portfolio.close_on_opposite_signal is True


def test_development_replay_withholds_oos_and_is_future_invariant() -> None:
    """Only the frozen development interval may affect its economics or identity."""
    bars, windows = _bars()
    result = evaluate_hip3_krown_trend_resumption_development(
        bars, _execution(), windows=windows
    )
    changed = bars.copy()
    changed.loc[changed.index >= windows.development_end_utc, "signal_close"] *= 2.0
    comparison = evaluate_hip3_krown_trend_resumption_development(
        changed, _execution(), windows=windows
    )

    assert result.development.nominal.completed_trades > 0
    assert result.development == comparison.development
    assert result.folds == comparison.folds
    assert result.out_of_sample_economics == "WITHHELD_NOT_EVALUATED"
    assert result.execution_authority == "none"
    assert len(result.folds) == 3


def test_report_exposes_exact_identity_costs_and_technical_path() -> None:
    """The durable result must remain diagnostic and reconcile its frozen contract."""
    bars, windows = _bars()
    result = evaluate_hip3_krown_trend_resumption_development(
        bars, _execution(), windows=windows
    )
    report = build_hip3_krown_development_report(
        result,
        bars.loc[bars.index < windows.development_end_utc],
        _friction(),
    )

    assert report["schema_version"] == "hip3_krown_trend_resumption_development_v1"
    assert report["strategy_identity"]["timeframe"] == "15m"
    assert report["strategy_identity"]["config"]["rsi_ema_length"] == 12
    assert report["scaled_account_hypothesis"]["notional_usd"] == 750.0
    applied = report["friction_contract"]["applied_strategy_execution"]
    assert applied["fixed_take_profit"] is False
    assert applied["stop_distance_bps"] == 80.0
    assert applied["maximum_hold_seconds"] == 86_400
    assert report["technical_path_evidence"]["decision_l2_required"] is False
    assert report["out_of_sample_economics"] == "WITHHELD_NOT_EVALUATED"
    assert report["validation_accessed"] is False
    assert report["holdout_accessed"] is False
    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
