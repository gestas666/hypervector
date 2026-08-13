"""Tests for the report-only ETH pullback metalabel challenger."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.ml.eth_pullback_challenger import (
    ETH_PULLBACK_MODEL_CANDIDATES,
    ETH_PULLBACK_MODEL_FEATURES,
    build_eth_pullback_model_rows,
    evaluate_eth_pullback_metalabel,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade


def _market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=100, freq="1min", tz="UTC")
    close = pd.Series(100.0 + np.arange(100) / 100.0, index=index)
    frame = pd.DataFrame(index=index)
    frame["open"] = close - 0.01
    frame["high"] = close + 0.02
    frame["low"] = close - 0.02
    frame["close"] = close
    frame["volume"] = 10.0 + np.arange(100)
    frame["entry_side"] = None
    frame.loc[index[80], "entry_side"] = "long"
    frame["breakout_side"] = None
    frame.loc[index[80], "breakout_side"] = "long"
    frame["state_1m"] = "TREND_UP"
    frame["context_15m"] = "TREND_UP"
    frame["sma_gap_bps"] = 5.0
    frame["regime_strength_score"] = 0.75
    frame["bbwp_percentile"] = 20.0
    frame["ema_gap_bps_signed"] = 4.0
    frame["rsi"] = 58.0
    frame["breakout_volume_ratio"] = 1.4
    frame["regime_5m_strength_percentile"] = 70.0
    frame["regime_5m_bbwp_percentile"] = 30.0
    frame["regime_5m_ema_gap_bps"] = 6.0
    frame["regime_5m_breakout_volume_ratio"] = 1.6
    return frame


def _trade(market: pd.DataFrame) -> HypeExitTrade:
    signal = market.index[80]
    entry = market.index[81]
    exit_time = market.index[90]
    return HypeExitTrade(
        side="long",
        signal_time_utc=signal.isoformat(),
        entry_time_utc=entry.isoformat(),
        exit_time_utc=exit_time.isoformat(),
        entry_price=100.81,
        exit_price=101.0,
        stop_price=100.2,
        gross_return_bps=18.8,
        fee_bps=9.0,
        funding_bps=0.2,
        net_return_bps=5.6,
        hold_minutes=9,
        maximum_favorable_excursion_bps=25.0,
        maximum_adverse_excursion_bps=4.0,
        exit_reason="maximum_hold",
    )


def _model_rows(samples: int = 260) -> pd.DataFrame:
    times = pd.date_range("2025-01-01", periods=samples, freq="12h", tz="UTC")
    latent = np.sin(np.arange(samples, dtype=float) / 9.0)
    rows: list[dict[str, object]] = []
    for index, stamp in enumerate(times):
        side = "long" if index % 2 == 0 else "short"
        aligned = float(index % 3 != 0)
        row: dict[str, object] = {
            "entry_side": side,
            "signal_time_utc": stamp,
            "entry_time_utc": stamp + pd.Timedelta(minutes=1),
            "exit_time_utc": stamp + pd.Timedelta(minutes=90),
            "gross_return_bps": 60.0 * latent[index] + 8.0 * aligned,
            "net_return_bps": 60.0 * latent[index] + 8.0 * aligned - 13.0,
            "exit_reason": "maximum_hold",
            "side_sign": 1.0 if side == "long" else -1.0,
            "breakout_relation_aligned": aligned,
        }
        for feature_index, name in enumerate(ETH_PULLBACK_MODEL_FEATURES[:-2]):
            row[name] = latent[index] + feature_index / 100.0
        rows.append(row)
    return pd.DataFrame(rows)


def test_model_rows_are_point_in_time_and_preserve_mechanism_identity() -> None:
    """Future prices cannot alter signal-time side or breakout attribution."""
    market = _market()
    original = build_eth_pullback_model_rows(market, (_trade(market),))
    changed = market.copy()
    changed.loc[changed.index[81] :, ["open", "high", "low", "close"]] *= 3.0

    revised = build_eth_pullback_model_rows(changed, (_trade(market),))

    assert original.loc[0, "side_sign"] == 1.0
    assert original.loc[0, "breakout_relation_aligned"] == 1.0
    pd.testing.assert_series_equal(
        original.loc[0, list(ETH_PULLBACK_MODEL_FEATURES)],
        revised.loc[0, list(ETH_PULLBACK_MODEL_FEATURES)],
    )


def test_metalabel_uses_purged_development_and_opened_final_confirmation() -> None:
    """The opened confirmation block must never enter model fitting or selection."""
    rows = _model_rows()
    development_end = rows.iloc[190]["signal_time_utc"]
    final_start = rows.iloc[200]["signal_time_utc"]
    final_end = rows.iloc[-1]["exit_time_utc"] + pd.Timedelta(minutes=1)

    result = evaluate_eth_pullback_metalabel(
        rows,
        development_end_utc=development_end.isoformat(),
        opened_final_start_utc=final_start.isoformat(),
        opened_final_end_utc=final_end.isoformat(),
        n_splits=3,
        embargo_minutes=120,
    )

    assert result.report["contract"]["execution_authority"] == "none"
    assert result.report["contract"]["automatic_promotion"] is False
    assert result.report["trial_accounting"]["model_candidates"] == 2
    assert result.report["model_protocol"] == {
        "modeled_round_trip_bps": 13.0,
        "training_target": "gross_return_bps",
        "economic_evaluation": "actual_net_return_bps",
    }
    assert set(result.final_predictions["candidate"]) == set(
        ETH_PULLBACK_MODEL_CANDIDATES
    )
    assert len(result.final_predictions) == 2 * 60
    assert result.report["opened_final_confirmation"]["rows"] == 60
    assert result.report["opened_final_confirmation"]["used_for_selection"] is False
    assert set(result.report["opened_final_confirmation"]["by_candidate"]) == set(
        ETH_PULLBACK_MODEL_CANDIDATES
    )
    development_attribution = result.report["development_oos_attribution"]
    assert development_attribution["used_for_selection"] is True
    assert development_attribution["rows"] * 2 == len(result.development.predictions)
    assert set(development_attribution["by_candidate"]) == set(
        ETH_PULLBACK_MODEL_CANDIDATES
    )
    assert result.development.predictions["breakout_relation"].notna().all()
    for fold in result.development.folds:
        train_outcome = result.development.rows.iloc[fold.train_indices][
            "outcome_ts_ms"
        ].max()
        test_signal = result.development.rows.iloc[fold.test_indices][
            "signal_ts_ms"
        ].min()
        assert train_outcome < test_signal - 120 * 60_000


def test_metalabel_rejects_overlapping_or_unresolved_boundaries() -> None:
    """Confirmation cannot overlap development or contain unresolved outcomes."""
    rows = _model_rows()
    boundary = rows.iloc[190]["signal_time_utc"]
    final_end = rows.iloc[-1]["exit_time_utc"] + pd.Timedelta(minutes=1)

    with pytest.raises(ValueError, match="strictly ordered"):
        evaluate_eth_pullback_metalabel(
            rows,
            development_end_utc=boundary.isoformat(),
            opened_final_start_utc=boundary.isoformat(),
            opened_final_end_utc=final_end.isoformat(),
        )

    censored = rows.copy()
    censored.loc[censored.index[-1], "exit_time_utc"] = final_end + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="resolved inside"):
        evaluate_eth_pullback_metalabel(
            censored,
            development_end_utc=boundary.isoformat(),
            opened_final_start_utc=rows.iloc[200]["signal_time_utc"].isoformat(),
            opened_final_end_utc=final_end.isoformat(),
        )
