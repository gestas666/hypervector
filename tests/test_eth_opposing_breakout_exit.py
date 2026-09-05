"""Causal contract tests for the report-only ETH opposing-breakout exit."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.eth_opposing_breakout_exit import (
    EthOpposingBreakoutSpec,
    replay_eth_opposing_breakout_exit,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
)
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)


def test_fresh_opposing_breakout_exits_at_next_open() -> None:
    """A completed adverse onset must not use its own bar's open as a fill."""
    market = _market()
    control = _control(market)

    result = replay_eth_opposing_breakout_exit(market, control.trades)

    assert result.technical_status == "resolved"
    assert result.execution_authority == "none"
    assert len(result.triggers) == 1
    assert result.triggers[0].decision_time_utc == market.index[4].isoformat()
    trade = result.report.trades[0]
    assert trade.signal_time_utc == control.trades[0].signal_time_utc
    assert trade.entry_time_utc == control.trades[0].entry_time_utc
    assert trade.exit_time_utc == market.index[5].isoformat()
    assert trade.exit_reason == "structural_reversal"


def test_aligned_breakout_onset_does_not_exit() -> None:
    """A fresh breakout in the position direction is not adverse evidence."""
    market = _market(breakout_side="long")
    control = _control(market)

    result = replay_eth_opposing_breakout_exit(market, control.trades)

    assert result.triggers == ()
    assert result.report.trades[0].exit_reason == "end_of_data"


def test_persistent_breakout_is_not_reinterpreted_as_fresh() -> None:
    """A projected BREAKOUT state already active before entry cannot trigger."""
    market = _market(fresh_onset=False)
    control = _control(market)

    result = replay_eth_opposing_breakout_exit(market, control.trades)

    assert result.triggers == ()
    assert result.report.trades[0].exit_reason == "end_of_data"


def test_one_bar_delay_stress_exits_at_second_open() -> None:
    """The declared delay stress waits one additional complete minute."""
    market = _market()
    control = _control(market)
    spec = EthOpposingBreakoutSpec(additional_decision_delay_minutes=1)

    result = replay_eth_opposing_breakout_exit(market, control.trades, spec)

    assert result.triggers[0].applied_time_utc == market.index[5].isoformat()
    assert result.report.trades[0].exit_time_utc == market.index[6].isoformat()


def test_protective_stop_precedes_scheduled_breakout_exit() -> None:
    """A gap through the venue stop wins over a pending next-open exit."""
    market = _market(gap_after_trigger=True)
    control = _control(market)

    result = replay_eth_opposing_breakout_exit(market, control.trades)

    assert len(result.triggers) == 1
    trade = result.report.trades[0]
    assert trade.exit_time_utc == market.index[5].isoformat()
    assert trade.exit_reason == "protective_stop"
    assert trade.exit_price < trade.stop_price


def test_missing_direction_on_fresh_onset_is_unresolved() -> None:
    """Missing adverse-direction evidence cannot become a neutral success."""
    market = _market(breakout_side=None)
    control = _control(market)

    result = replay_eth_opposing_breakout_exit(market, control.trades)

    assert result.technical_status == "unresolved_breakout_direction"
    assert result.unavailable_direction_rows == (market.index[4].isoformat(),)
    assert result.triggers == ()
    assert result.report.trades[0].exit_reason == "end_of_data"


def test_native_structural_reversal_has_no_candidate_authority() -> None:
    """Only the frozen breakout trigger may use the replay adapter."""
    market = _market(breakout_side="long")
    market.loc[market.index[2], "structural_direction"] = "short"
    control = _control(market)

    result = replay_eth_opposing_breakout_exit(market, control.trades)

    assert result.triggers == ()
    assert result.report.trades[0].exit_reason == "end_of_data"


def _market(
    *,
    breakout_side: str | None = "short",
    fresh_onset: bool = True,
    gap_after_trigger: bool = False,
) -> pd.DataFrame:
    """Build one exact-minute ETH long path and five-minute onset projection."""
    index = pd.date_range("2026-01-01", periods=9, freq="1min", tz="UTC")
    opening = np.full(len(index), 100.0)
    if gap_after_trigger:
        opening[5:] = 98.0
    states = ["RANGE"] * 4 + ["BREAKOUT"] * 5
    if not fresh_onset:
        states = ["BREAKOUT"] * len(index)
    sides: list[str | None] = [None] * 4 + [breakout_side] * 5
    if not fresh_onset:
        sides = [breakout_side] * len(index)
    return pd.DataFrame(
        {
            "open": opening,
            "high": np.maximum(opening, 100.2),
            "low": np.minimum(opening, 99.9),
            "close": opening,
            "volume": 100.0,
            "entry_side": ["long", *([None] * 8)],
            "state_5m": states,
            "structural_direction": "long",
            "breakout_side": sides,
            "funding_rate": 0.0,
        },
        index=index,
    )


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
