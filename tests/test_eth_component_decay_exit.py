"""Causal contract tests for the report-only ETH component-decay exit."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research import eth_component_decay_exit as candidate
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits


def test_component_decay_requires_activation_and_five_completed_bars(
    monkeypatch: object,
) -> None:
    """The fixed trigger must be causal and execute only at the next open."""
    market = _market()
    control = _control(market)
    monkeypatch.setattr(
        candidate,
        "build_regime_component_frame",
        lambda bars: _components(bars.index, opposed=range(1, 6)),
    )

    result = candidate.replay_eth_component_decay_exit(market, control.trades)

    assert result.technical_status == "resolved"
    assert result.execution_authority == "none"
    assert len(result.triggers) == 1
    assert result.triggers[0].decision_time_utc == market.index[5].isoformat()
    trade = result.report.trades[0]
    assert trade.signal_time_utc == control.trades[0].signal_time_utc
    assert trade.entry_time_utc == control.trades[0].entry_time_utc
    assert trade.exit_time_utc == market.index[6].isoformat()
    assert trade.exit_reason == "structural_reversal"


def test_component_decay_does_not_trigger_without_r5_or_full_persistence(
    monkeypatch: object,
) -> None:
    """Four opposed bars or less than 300-bps MFE cannot activate the exit."""
    market = _market(maximum_high=102.9)
    control = _control(market)
    monkeypatch.setattr(
        candidate,
        "build_regime_component_frame",
        lambda bars: _components(bars.index, opposed=range(1, 8)),
    )
    below_r5 = candidate.replay_eth_component_decay_exit(market, control.trades)
    market = _market()
    control = _control(market)
    monkeypatch.setattr(
        candidate,
        "build_regime_component_frame",
        lambda bars: _components(bars.index, opposed=range(1, 5)),
    )
    only_four = candidate.replay_eth_component_decay_exit(market, control.trades)

    assert below_r5.triggers == ()
    assert only_four.triggers == ()
    assert below_r5.report.trades[0].exit_reason == "end_of_data"
    assert only_four.report.trades[0].exit_reason == "end_of_data"


def test_protective_stop_precedes_scheduled_component_exit(
    monkeypatch: object,
) -> None:
    """A gap through the venue stop wins over a pending next-open exit."""
    market = _market(gap_after_trigger=True)
    control = _control(market)
    monkeypatch.setattr(
        candidate,
        "build_regime_component_frame",
        lambda bars: _components(bars.index, opposed=range(1, 6)),
    )

    result = candidate.replay_eth_component_decay_exit(market, control.trades)

    trade = result.report.trades[0]
    assert len(result.triggers) == 1
    assert trade.exit_time_utc == market.index[6].isoformat()
    assert trade.exit_reason == "protective_stop"
    assert trade.exit_price < trade.stop_price


def test_incomplete_component_path_is_reported_unresolved(
    monkeypatch: object,
) -> None:
    """Missing component evidence cannot produce a success-shaped result."""
    market = _market()
    control = _control(market)
    components = _components(market.index, opposed=range(1, 6))
    components.loc[market.index[3], "harsi_direction"] = np.nan
    monkeypatch.setattr(
        candidate,
        "build_regime_component_frame",
        lambda bars: components,
    )

    result = candidate.replay_eth_component_decay_exit(market, control.trades)

    assert result.technical_status == "unresolved_component_path"
    assert result.unavailable_component_rows == (market.index[3].isoformat(),)
    assert result.triggers == ()


def test_entry_bar_protective_stop_needs_no_component_decision(
    monkeypatch: object,
) -> None:
    """A zero-minute venue stop is resolved without an invented exit signal."""
    market = _market()
    market.loc[market.index[1], "low"] = 98.0
    control = _control(market)
    monkeypatch.setattr(
        candidate,
        "build_regime_component_frame",
        lambda bars: _components(bars.index, opposed=range(1, 8)),
    )

    result = candidate.replay_eth_component_decay_exit(market, control.trades)

    assert control.trades[0].entry_time_utc == control.trades[0].exit_time_utc
    assert result.technical_status == "resolved"
    assert result.triggers == ()
    assert result.report.trades[0].exit_reason == "protective_stop"


def test_native_structural_reversal_is_not_a_component_trigger(
    monkeypatch: object,
) -> None:
    """The replay adapter cannot inherit unrelated structural exit authority."""
    market = _market(maximum_high=102.0)
    market.loc[market.index[2], "structural_direction"] = "short"
    control = _control(market)
    monkeypatch.setattr(
        candidate,
        "build_regime_component_frame",
        lambda bars: _components(bars.index, opposed=range(0)),
    )

    result = candidate.replay_eth_component_decay_exit(market, control.trades)

    assert result.triggers == ()
    assert result.report.trades[0].exit_reason == "end_of_data"


def _market(
    *,
    maximum_high: float = 104.0,
    gap_after_trigger: bool = False,
) -> pd.DataFrame:
    """Build one exact-minute ETH path with a single native long entry."""
    index = pd.date_range("2026-01-01", periods=9, freq="1min", tz="UTC")
    opening = np.full(len(index), 100.0)
    if gap_after_trigger:
        opening[6:] = 98.0
    frame = pd.DataFrame(
        {
            "open": opening,
            "high": np.maximum(opening, maximum_high),
            "low": np.minimum(opening, 99.9),
            "close": opening,
            "volume": 100.0,
            "entry_side": ["long", *([None] * 8)],
            "state_5m": "BREAKOUT",
            "state_1m": "TREND_UP",
            "context_15m": "TREND_UP",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    return frame


def _control(market: pd.DataFrame) -> object:
    """Replay the exact 60-bps/12-hour native control entry."""
    return replay_hype_breakout_exits(
        market,
        HypeExitPolicy("native_12h_control"),
        HypeExitReplayConfig(
            stop_bps=60.0,
            maximum_hold_minutes=720,
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
        ),
    )


def _components(index: pd.DatetimeIndex, *, opposed: range) -> pd.DataFrame:
    """Build complete deterministic component directions for a long trade."""
    values = np.ones(len(index))
    values[list(opposed)] = -1.0
    return pd.DataFrame(
        {
            "ema_21_55_direction": values,
            "sma_100_200_direction": values,
            "cipher_a_direction": values,
            "harsi_direction": values,
            "mtf_5m_bias": values,
            "mtf_15m_bias": values,
            "trend_slope_bps": values,
        },
        index=index,
    )
