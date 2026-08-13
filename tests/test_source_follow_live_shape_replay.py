"""Causal replay tests for the deployed BTC source-follow execution shape."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from hypervector.regime.source_follow_runtime import (
    FiveMinuteBar,
    SourceFollowRuntime,
    SourceRegimeLabel,
)
from hypervector.regime.source_follow_session import SourceFollowSessionSignal
from hypervector.research.source_follow_live_shape_replay import (
    SourceLiveShapeConfig,
    SourceLiveShapeSignal,
    collect_source_live_shape_signals,
    replay_source_live_shape,
)


class _Classifier:
    def __init__(self, labels: tuple[tuple[str, str | None, float], ...]) -> None:
        self._labels = iter(labels)

    def classify(self, bar: FiveMinuteBar) -> SourceRegimeLabel:
        primary, secondary, confidence = next(self._labels)
        return SourceRegimeLabel(
            label_time_utc=bar.timestamp_utc,
            primary=primary,
            secondary=secondary,
            confidence=confidence,
        )


def _bars(
    rows: tuple[tuple[float, float, float, float], ...],
    *,
    start: str = "2026-01-01T00:00:00Z",
) -> pd.DataFrame:
    index = pd.date_range(start, periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
            "volume": 1.0,
            "source": "hl",
        }
    )


def _config(**overrides: object) -> SourceLiveShapeConfig:
    values: dict[str, object] = {
        "initial_equity": 500.0,
        "margin_fraction": 0.03,
        "leverage": 5.0,
        "maximum_notional_usd": 25.0,
        "stop_bps": 80.0,
        "target_bps": 100.0,
        "maximum_hold_minutes": 60,
        "entry_slippage_bps": 0.0,
        "market_exit_slippage_bps": 0.0,
        "size_decimals": 5,
    }
    values.update(overrides)
    return SourceLiveShapeConfig(**values)


def test_long_target_uses_taker_entry_and_maker_exit_fees() -> None:
    """A strict-through target is credited at its resting limit price."""
    bars = _bars(
        (
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 101.1, 99.9, 101.0),
            (101.0, 101.0, 101.0, 101.0),
        )
    )
    signal = SourceLiveShapeSignal(bars.iloc[0].timestamp, "long", 100.0)

    report = replay_source_live_shape(bars, (), (signal,), _config())

    trade = report.trades[0]
    assert trade.exit_reason == "target"
    assert trade.entry_price == 100.0
    assert trade.exit_price == 101.0
    assert trade.quantity == 0.25
    assert trade.entry_fee_usd == pytest.approx(0.25 * 100.0 * 0.00045)
    assert trade.exit_fee_usd == pytest.approx(0.25 * 101.0 * 0.00015)
    assert trade.net_pnl_usd > 0.0
    assert report.completed_trades == 1
    assert report.profit_factor is None


def test_stop_wins_when_stop_and_target_share_an_ambiguous_bar() -> None:
    """Unknown intrabar ordering must resolve against the strategy."""
    bars = _bars(
        (
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 102.0, 98.0, 100.0),
            (100.0, 100.0, 100.0, 100.0),
        )
    )
    signal = SourceLiveShapeSignal(bars.iloc[0].timestamp, "long", 100.0)

    report = replay_source_live_shape(bars, (), (signal,), _config())

    assert report.trades[0].exit_reason == "stop"
    assert report.trades[0].exit_price == pytest.approx(99.2)
    assert report.ambiguous_bar_exits == 1


def test_open_position_occupies_later_signals_until_maximum_hold() -> None:
    """One BTC position serializes overlapping long and short onsets."""
    bars = _bars(tuple((100.0, 100.1, 99.9, 100.0) for _ in range(5)))
    signals = (
        SourceLiveShapeSignal(bars.iloc[0].timestamp, "long", 100.0),
        SourceLiveShapeSignal(bars.iloc[1].timestamp, "short", 100.0),
    )

    report = replay_source_live_shape(
        bars,
        (),
        signals,
        _config(target_bps=500.0, maximum_hold_minutes=2),
    )

    assert report.completed_trades == 1
    assert report.occupied_signals == 1
    assert report.trades[0].exit_reason == "maximum_hold"
    assert report.trades[0].exit_time_utc == bars.iloc[2].timestamp.isoformat()


def test_signal_collection_reconstructs_current_bidirectional_onsets() -> None:
    """Current source labels emit one causal long and one causal short onset."""
    bars = _bars(tuple((100.0, 100.2, 99.8, 100.0) for _ in range(15)))
    runtime = SourceFollowRuntime(
        _Classifier(
            (
                ("TREND_UP", None, 0.9),
                ("TREND_UP", None, 0.9),
                ("TREND_DOWN", None, 0.9),
            )
        ),
        minimum_confidence=0.7,
        minimum_range_bps=12.0,
        maximum_range_bps=100.0,
        direction_mode="trend_bidirectional",
    )
    session = SourceFollowSessionSignal(runtime)

    signals = collect_source_live_shape_signals(bars, session)

    assert [(signal.side, signal.decision_time_utc) for signal in signals] == [
        ("long", datetime(2026, 1, 1, 0, 5, tzinfo=UTC).isoformat()),
        ("short", datetime(2026, 1, 1, 0, 15, tzinfo=UTC).isoformat()),
    ]
