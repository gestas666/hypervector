"""Acceptance metrics for Hypervelocity-specific regime evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.cli import main
from hypervector.regime.hypervelocity_eval import (
    evaluate_breakout_quality,
    evaluate_entry_alignment,
    evaluate_hypervelocity_regimes,
)


def _decisions() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=6, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "primary_regime": [
                "TREND_UP",
                "TREND_UP",
                "TREND_DOWN",
                "RANGE",
                "BREAKOUT",
                "BREAKOUT",
            ],
            "breakout_direction": [None, None, None, None, "BK_UPWARD", "BK_DOWNWARD"],
            "state_1m": ["TREND_UP"] * 6,
            "state_5m": ["TREND_UP"] * 6,
            "context_15m": ["TREND_UP"] * 6,
            "confidence": [1.0] * 6,
            "reason": ["fixture"] * 6,
        },
        index=index,
    )


def _positions(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time_utc": [index[0], index[2], index[3]],
            "side": ["long", "short", "long"],
            "symbol": ["BTC", "BTC", "BTC"],
        }
    )


def test_entry_alignment_reports_false_range_without_aborting() -> None:
    decisions = _decisions()

    result = evaluate_entry_alignment(decisions, _positions(decisions.index))

    assert result.total_entries == 3
    assert result.direction_matches == 2
    assert result.direction_recall_pct == 200.0 / 3.0
    assert result.false_range_at_entries == 1
    assert result.no_entry_state_at_entries == 1


def test_breakout_quality_reports_target_misses() -> None:
    decisions = _decisions()
    decisions["primary_regime"] = "RANGE"
    decisions["breakout_direction"] = None
    decisions.loc[decisions.index[1], ["primary_regime", "breakout_direction"]] = [
        "BREAKOUT",
        "BK_UPWARD",
    ]
    decisions.loc[decisions.index[3], ["primary_regime", "breakout_direction"]] = [
        "BREAKOUT",
        "BK_DOWNWARD",
    ]
    close = np.full(6, 100.0)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": [100.0, 100.0, 100.25, 100.0, 100.05, 100.05],
            "low": [100.0, 100.0, 99.95, 100.0, 99.95, 99.95],
            "close": close,
            "volume": 100.0,
        },
        index=decisions.index,
    )

    result = evaluate_breakout_quality(
        bars,
        decisions,
        target_price_fraction=0.002,
        forward_horizon=2,
    )

    assert result.breakout_events == 2
    assert result.false_breakouts == 1
    assert result.false_breakout_pct == 50.0


def test_full_report_records_source_limitations() -> None:
    n = 240
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = np.linspace(100.0, 110.0, n)
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "source": "binance",
        },
        index=index,
    )
    positions = pd.DataFrame(
        {"open_time_utc": [index[-1]], "side": ["long"], "symbol": ["BTC"]}
    )

    result = evaluate_hypervelocity_regimes(bars, positions)

    assert result.total_bars == n
    assert result.bar_sources == ("binance",)
    assert result.source_limited is True
    assert sum(result.state_distribution.values()) == n
    assert result.label_churn >= 0
    assert result.mean_transition_latency_bars >= 0.0
    assert set(result.context_direction_recall_pct) == {
        "canonical_5m_primary",
        "hard_5m",
        "hard_15m",
        "hard_30m",
    }


def test_cli_hypervelocity_regime_eval_is_report_only(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    n = 240
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    close = np.linspace(100.0, 110.0, n)
    bars = pd.DataFrame(
        {
            "timestamp": index,
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 100.0,
            "source": "binance",
        }
    )
    monkeypatch.setattr(
        "hypervector.cli._load_bars",
        lambda _args: (bars, {"source": "fixture"}),
    )
    positions_path = tmp_path / "positions.csv"
    pd.DataFrame(
        {"open_time_utc": [index[-1]], "side": ["long"], "symbol": ["BTC"]}
    ).to_csv(positions_path, index=False)

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "hypervelocity-regime-eval",
            "--symbol",
            "BTC",
            "--timeframe",
            "1m",
            "--lookback",
            "30",
            "--positions",
            str(positions_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert output["ok"] is True
    assert output["report_only"] is True
    assert output["entry_alignment"]["total_entries"] == 1
