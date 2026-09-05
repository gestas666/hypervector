"""Historical input and continuous-beta baseline tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hypervector.research.crypto_bull_participation_historical import (
    build_completed_hour_bars,
    evaluate_continuous_long_baseline,
    load_verified_crypto_minutes,
)
from hypervector.research.crypto_bull_participation_models import (
    CryptoBullParticipationConfig,
)


def test_minute_loader_requires_exact_hyperliquid_grid(tmp_path: Path) -> None:
    """Missing venue minutes fail rather than being forward-filled."""
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-01T02:00:00Z")
    frame = _minutes(start, 120).drop(index=17).reset_index(drop=True)
    path = tmp_path / "BTC.parquet"
    frame.to_parquet(path, index=False)

    with pytest.raises(ValueError, match="minute grid differs"):
        load_verified_crypto_minutes(path, start, end)


def test_hourly_aggregation_uses_complete_left_labeled_hours(tmp_path: Path) -> None:
    """Each decision bar contains exactly sixty causal source minutes."""
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-01T02:00:00Z")
    path = tmp_path / "BTC.parquet"
    frame = _minutes(start, 120)
    frame.loc[59, "high"] = 110.0
    frame.loc[119, "close"] = 105.0
    frame.to_parquet(path, index=False)

    minutes = load_verified_crypto_minutes(path, start, end)
    hourly = build_completed_hour_bars(minutes)

    assert hourly.index.tolist() == [start, start + pd.Timedelta(hours=1)]
    assert hourly.iloc[0].to_dict() == {
        "open": 100.0,
        "high": 110.0,
        "low": 99.0,
        "close": 100.0,
    }
    assert hourly.iloc[1, 3] == 105.0


def test_minute_loader_discloses_bounded_venue_continuity_rows(
    tmp_path: Path,
) -> None:
    """Explicit Hyperliquid gap fills are accepted and counted, never relabeled."""
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-01T02:00:00Z")
    frame = _minutes(start, 120)
    frame.loc[17:18, "source"] = "hl_gap_fill"
    path = tmp_path / "BTC.parquet"
    frame.to_parquet(path, index=False)

    minutes = load_verified_crypto_minutes(path, start, end)

    assert minutes.attrs["source_counts"] == {"hl": 118, "hl_gap_fill": 2}
    assert minutes.attrs["maximum_gap_fill_run"] == 2


def test_minute_loader_rejects_nonvenue_source(tmp_path: Path) -> None:
    """An unsupported external or unlabeled price source remains fatal."""
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-01T02:00:00Z")
    frame = _minutes(start, 120)
    frame.loc[17, "source"] = "external"
    path = tmp_path / "BTC.parquet"
    frame.to_parquet(path, index=False)

    with pytest.raises(ValueError, match="unsupported source"):
        load_verified_crypto_minutes(path, start, end)


def test_minute_loader_rejects_gap_fill_run_over_amended_bound(
    tmp_path: Path,
) -> None:
    """Continuity repair beyond thirty minutes remains a technical failure."""
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-01T02:00:00Z")
    frame = _minutes(start, 120)
    frame.loc[17:47, "source"] = "hl_gap_fill"
    path = tmp_path / "BTC.parquet"
    frame.to_parquet(path, index=False)

    with pytest.raises(ValueError, match="gap-fill run exceeds thirty minutes"):
        load_verified_crypto_minutes(path, start, end)


def test_continuous_long_baseline_reconciles_fees_slippage_and_funding() -> None:
    """The nonselectable beta control uses the registered shared sizing and costs."""
    index = pd.date_range("2026-01-01", periods=61, freq="min", tz="UTC")
    frame = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        index=index,
    )
    funding = pd.Series(0.0, index=index, name="funding_rate")
    funding.loc[index[-1]] = 0.001
    config = CryptoBullParticipationConfig(
        symbols=("BTC",),
        fast_ema_hours=2,
        slow_ema_hours=3,
        minimum_ema_hours=3,
        entry_breadth=1,
        exit_breadth=1,
        initial_equity_usd=1_000.0,
        margin_fraction_per_position=0.1,
        leverage=2.0,
        maximum_positions=1,
        maximum_total_margin_fraction=0.1,
        entry_fee_bps=4.0,
        exit_fee_bps=4.0,
        adverse_slippage_bps_per_side=10.0,
    )

    report = evaluate_continuous_long_baseline({"BTC": frame}, {"BTC": funding}, config)

    trade = report.trades[0]
    assert trade.entry_price == pytest.approx(100.1)
    assert trade.exit_price == pytest.approx(99.9)
    assert trade.funding_cashflow_usd == pytest.approx(-0.1998001998)
    assert trade.fees_usd == pytest.approx(0.1598401598)
    assert trade.slippage_cost_usd == pytest.approx(0.3996003996)
    assert trade.net_pnl_usd == pytest.approx(-0.7592407592)
    assert report.net_pnl_usd == pytest.approx(trade.net_pnl_usd)


def _minutes(start: pd.Timestamp, periods: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=periods, freq="min"),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl",
        }
    )
