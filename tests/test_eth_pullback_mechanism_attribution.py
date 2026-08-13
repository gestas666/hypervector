"""Tests for causal ETH pullback side and breakout-relation attribution."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.eth_pullback_mechanism_attribution import (
    build_eth_pullback_mechanism_attribution,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade, HypeSide


def test_attribution_separates_side_and_breakout_relation_by_segment() -> None:
    """Purge trades stay excluded and exact signal-time relations stay separate."""
    market = _market(
        (
            ("2026-01-01T00:00:00Z", "long", "long"),
            ("2026-01-02T00:00:00Z", "short", "long"),
            ("2026-05-28T18:00:00Z", "long", "short"),
            ("2026-06-01T00:00:00Z", "long", "short"),
            ("2026-06-02T00:00:00Z", "short", "short"),
        )
    )
    trades = (
        _trade("2026-01-01T00:00:00Z", "long", 20.0),
        _trade("2026-01-02T00:00:00Z", "short", -10.0),
        _trade("2026-05-28T18:00:00Z", "long", 100.0),
        _trade("2026-06-01T00:00:00Z", "long", 30.0),
        _trade("2026-06-02T00:00:00Z", "short", 40.0),
    )

    report = build_eth_pullback_mechanism_attribution(
        market,
        trades,
        development_end_utc="2026-05-28T12:00:00Z",
        opened_final_start_utc="2026-05-29T00:00:00Z",
        opened_final_end_utc="2026-07-28T00:00:00Z",
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["coverage"] == {
        "input_trades": 5,
        "development_trades": 2,
        "opened_final_trades": 2,
        "purge_or_out_of_window_trades": 1,
    }
    development = report["segments"]["development"]
    assert development["all"]["net_return_bps"] == pytest.approx(10.0)
    assert development["all"]["profit_factor"] == pytest.approx(2.0)
    assert development["by_relation"]["aligned"]["trades"] == 1
    assert development["by_relation"]["opposed"]["trades"] == 1
    final = report["segments"]["opened_final_60d"]
    assert final["by_side_relation"]["long|opposed"]["net_return_bps"] == 30.0
    assert final["by_side_relation"]["short|aligned"]["net_return_bps"] == 40.0
    combined = report["segments"]["all_available"]
    assert combined["all"]["trades"] == 4
    assert combined["all"]["net_return_bps"] == pytest.approx(80.0)
    assert combined["all"]["net_excluding_largest_winner_bps"] == 40.0


def test_attribution_rejects_signal_side_mismatch() -> None:
    """A replay trade cannot borrow another side's breakout relation."""
    market = _market((("2026-01-01T00:00:00Z", "long", "short"),))
    trades = (_trade("2026-01-01T00:00:00Z", "short", 10.0),)

    with pytest.raises(ValueError, match="side does not match"):
        build_eth_pullback_mechanism_attribution(
            market,
            trades,
            development_end_utc="2026-05-28T12:00:00Z",
            opened_final_start_utc="2026-05-29T00:00:00Z",
            opened_final_end_utc="2026-07-28T00:00:00Z",
        )


def _market(rows: tuple[tuple[str, str, str], ...]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(row[0]) for row in rows])
    return pd.DataFrame(
        {
            "entry_side": [row[1] for row in rows],
            "breakout_side": [row[2] for row in rows],
        },
        index=index,
    )


def _trade(timestamp: str, side: HypeSide, net_bps: float) -> HypeExitTrade:
    signal = pd.Timestamp(timestamp)
    entry = signal + pd.Timedelta(minutes=1)
    exit_time = entry + pd.Timedelta(minutes=10)
    gross = net_bps + 9.0
    return HypeExitTrade(
        side=side,
        signal_time_utc=signal.isoformat(),
        entry_time_utc=entry.isoformat(),
        exit_time_utc=exit_time.isoformat(),
        entry_price=100.0,
        exit_price=100.0 + gross / 100.0,
        stop_price=99.0,
        gross_return_bps=gross,
        fee_bps=9.0,
        funding_bps=0.0,
        net_return_bps=net_bps,
        hold_minutes=10,
        maximum_favorable_excursion_bps=max(net_bps, 0.0) + 5.0,
        maximum_adverse_excursion_bps=max(-net_bps, 0.0) + 2.0,
        exit_reason="maximum_hold",
    )
