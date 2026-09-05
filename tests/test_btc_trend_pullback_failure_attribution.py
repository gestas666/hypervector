"""Post-hoc BTC trend-pullback failure attribution tests."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_trend_pullback_failure_attribution import (
    BtcTrendPullbackFailureObservation,
    attribute_btc_trend_pullback_failures,
    build_btc_trend_pullback_failure_report,
)


def test_failure_report_separates_entry_edge_from_cost_drag() -> None:
    """Gross loss, cost drag, and realized payoff geometry remain distinct."""
    report = build_btc_trend_pullback_failure_report(
        (
            _observation("target", 30.0, 3.0, -1.0, 26.0),
            _observation("stop", -31.0, 4.0, -1.0, -36.0),
        )
    )

    economics = report["economics"]
    assert economics["completed_trades"] == 2
    assert economics["wins"] == 1
    assert economics["losses"] == 1
    assert economics["gross_pnl_usd"] == -1.0
    assert economics["fees_usd"] == 7.0
    assert economics["funding_cashflow_usd"] == -2.0
    assert economics["net_pnl_usd"] == -10.0
    assert economics["actual_win_rate"] == 0.5
    assert economics["after_cost_break_even_win_rate"] == pytest.approx(36.0 / 62.0)
    assert report["diagnosis"]["costs_only_diagnosis_falsified"] is True
    assert report["authority"]["execution_authority"] == "none"


def test_failure_report_attributes_early_path_and_stop_excursions() -> None:
    """Stopped-path momentum and recoverable excursion counts are explicit."""
    target = _observation("target", 30.0, 3.0, -1.0, 26.0)
    stopped = _observation("stop", -31.0, 4.0, -1.0, -36.0)

    report = build_btc_trend_pullback_failure_report((target, stopped))

    stop_path = report["stop_path"]
    assert stop_path["stops"] == 1
    assert stop_path["reached_20bps_mfe_before_exit"] == 1
    assert stop_path["reached_40bps_mfe_before_exit"] == 0
    stopped_summary = report["by_outcome"]["stop"]
    assert stopped_summary["mean_forward_return_15m_bps"] == -18.0
    assert stopped_summary["mean_forward_return_60m_bps"] == -37.0
    assert stopped_summary["mean_ema_gap_bps"] == 57.0


def test_trade_attribution_uses_causal_signal_bar_and_exact_horizons() -> None:
    """Signal features, actual-exit path, and fixed horizons stay distinct."""
    bars, diagnostics, trades = _path_fixture()

    rows = attribute_btc_trend_pullback_failures(bars, diagnostics, trades)

    assert len(rows) == 1
    row = rows[0]
    assert row.partition == "validation"
    assert row.outcome == "stop"
    assert row.pullback_age_bars == 1
    assert row.pullback_depth_bps == pytest.approx(-13.0)
    assert row.ema_gap_bps == pytest.approx(57.0)
    assert row.forward_return_15m_bps == pytest.approx(-18.0)
    assert row.forward_return_60m_bps == pytest.approx(-37.0)
    assert row.forward_return_240m_bps == pytest.approx(-52.0)
    assert row.maximum_favorable_excursion_bps == pytest.approx(25.0)
    assert row.maximum_adverse_excursion_bps == pytest.approx(660.0)


def _observation(
    outcome: str,
    gross_pnl_usd: float,
    fees_usd: float,
    funding_cashflow_usd: float,
    net_pnl_usd: float,
) -> BtcTrendPullbackFailureObservation:
    return BtcTrendPullbackFailureObservation(
        partition="validation",
        outcome=outcome,
        gross_pnl_usd=gross_pnl_usd,
        fees_usd=fees_usd,
        funding_cashflow_usd=funding_cashflow_usd,
        net_pnl_usd=net_pnl_usd,
        holding_hours=3.0,
        ema_gap_bps=57.0,
        close_above_ema21_bps=51.0,
        breakout_excess_bps=17.0,
        pullback_age_bars=3,
        pullback_depth_bps=-13.0,
        maximum_favorable_excursion_bps=25.0 if outcome == "stop" else 68.0,
        maximum_adverse_excursion_bps=66.0 if outcome == "stop" else 27.0,
        forward_return_15m_bps=-18.0 if outcome == "stop" else 2.0,
        forward_return_60m_bps=-37.0 if outcome == "stop" else 15.0,
        forward_return_240m_bps=-52.0 if outcome == "stop" else 45.0,
    )


def _path_fixture() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2026-02-01T12:00:00Z", periods=256, freq="1min")
    bars = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        index=index,
    )
    entry = pd.Timestamp("2026-02-01T12:15:00Z")
    exit_time = pd.Timestamp("2026-02-01T13:15:00Z")
    bars.loc[entry:exit_time, "high"] = 100.25
    bars.loc[entry:exit_time, "low"] = 93.4
    bars.loc[entry + pd.Timedelta(minutes=15), "close"] = 99.82
    bars.loc[entry + pd.Timedelta(minutes=60), "close"] = 99.63
    bars.loc[entry + pd.Timedelta(minutes=240), "close"] = 99.48
    diagnostics = _diagnostics_fixture()
    trades = pd.DataFrame([_trade_fixture(entry, exit_time)])
    return bars, diagnostics, trades


def _diagnostics_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pullback_armed": [True, False],
            "long_entry": [False, True],
            "low": [99.87, 100.0],
            "close": [100.0, 100.51],
            "ema21": [100.0, 100.0],
            "ema55": [100.0, 100.0 / 1.0057],
            "prior_local_high": [100.0, 100.34],
        },
        index=pd.DatetimeIndex(["2026-02-01T11:45:00Z", "2026-02-01T12:00:00Z"]),
    )


def _trade_fixture(entry: pd.Timestamp, exit_time: pd.Timestamp) -> dict[str, object]:
    return {
        "partition": "validation",
        "scenario": "nominal",
        "arm": "candidate",
        "signal_name": "btc_trend_pullback_reacceleration_long_v1",
        "scope": None,
        "direction": "long",
        "signal_time_utc": "2026-02-01T12:14:00Z",
        "entry_time_utc": entry.isoformat(),
        "exit_time_utc": exit_time.isoformat(),
        "entry_price": 100.0,
        "gross_pnl_usd": -31.0,
        "fees_usd": 4.0,
        "funding_cashflow_usd": -1.0,
        "net_pnl_usd": -36.0,
        "exit_reason": "stop",
    }
