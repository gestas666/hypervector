"""Causal lifecycle tests for HYPE breakout-specific exit challengers."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hype_breakout_exit_replay import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    replay_hype_breakout_exits,
)


def _market(
    rows: list[tuple[float, float, float, float]],
    *,
    entries: dict[int, str] | None = None,
    states: dict[int, str] | None = None,
    structural: dict[int, str] | None = None,
    funding: dict[int, float] | None = None,
) -> pd.DataFrame:
    """Build one deterministic minute path with close-known entry metadata."""
    index = pd.date_range("2026-01-01", periods=len(rows), freq="1min", tz="UTC")
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=index)
    frame["entry_side"] = None
    frame["state_5m"] = "BREAKOUT"
    frame["state_1m"] = "TREND_UP"
    frame["context_15m"] = "TREND_UP"
    frame["structural_direction"] = "long"
    frame["funding_rate"] = 0.0
    for position, value in (entries or {}).items():
        frame.iloc[position, frame.columns.get_loc("entry_side")] = value
    for position, value in (states or {}).items():
        frame.iloc[position, frame.columns.get_loc("state_5m")] = value
    for position, value in (structural or {}).items():
        frame.iloc[position, frame.columns.get_loc("structural_direction")] = value
    for position, value in (funding or {}).items():
        frame.iloc[position, frame.columns.get_loc("funding_rate")] = value
    return frame


def _config(**overrides: object) -> HypeExitReplayConfig:
    values: dict[str, object] = {
        "stop_bps": 100.0,
        "maximum_hold_minutes": 10,
        "fee_bps_per_side": 0.0,
        "slippage_bps_per_side": 0.0,
    }
    values.update(overrides)
    return HypeExitReplayConfig(**values)


def test_entry_uses_next_open_and_invalidation_exits_at_following_open() -> None:
    """Neither entry nor structure exit may fill on its decision close."""
    market = _market(
        [(100.0, 100.0, 100.0, 100.0)] * 6,
        entries={0: "long"},
        states={2: "RANGE"},
    )

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("breakout_invalidation", exit_on_invalidation=True),
        _config(),
    )

    trade = report.trades[0]
    assert trade.signal_time_utc == market.index[0].isoformat()
    assert trade.entry_time_utc == market.index[1].isoformat()
    assert trade.exit_time_utc == market.index[3].isoformat()
    assert trade.exit_reason == "breakout_invalidation"


def test_structural_reversal_ignores_neutral_then_exits_opposite() -> None:
    """A temporary neutral direction is not an invented opposite signal."""
    market = _market(
        [(100.0, 100.1, 99.9, 100.0)] * 7,
        entries={0: "long"},
        structural={2: "neutral", 4: "short"},
    )

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("structural_reversal", exit_on_reversal=True),
        _config(),
    )

    trade = report.trades[0]
    assert trade.exit_time_utc == market.index[5].isoformat()
    assert trade.exit_reason == "structural_reversal"


@pytest.mark.parametrize(
    ("side", "prior_rsi", "prior_signal", "current_rsi", "current_signal"),
    [
        ("long", 55.0, 50.0, 48.0, 50.0),
        ("short", 45.0, 50.0, 52.0, 50.0),
    ],
)
def test_five_minute_momentum_reversal_is_fresh_and_next_open_causal(
    side: str,
    prior_rsi: float,
    prior_signal: float,
    current_rsi: float,
    current_signal: float,
) -> None:
    """Only a fresh completed-5m cross may schedule the following-open exit."""
    market = _market(
        [(100.0, 100.1, 99.9, 100.0)] * 7,
        entries={0: side},
    )
    market["regime_5m_rsi"] = [prior_rsi] * 3 + [current_rsi] * 4
    market["regime_5m_rsi_ema"] = [prior_signal] * 3 + [current_signal] * 4

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy(
            "five_minute_momentum_reversal",
            exit_on_5m_rsi_reversal=True,
        ),
        _config(),
    )

    trade = report.trades[0]
    assert trade.exit_time_utc == market.index[4].isoformat()
    assert trade.exit_reason == "momentum_reversal_5m"


def test_five_minute_momentum_exit_ignores_preexisting_opposition() -> None:
    """A stale RSI/EMA relationship cannot masquerade as a reversal event."""
    market = _market(
        [(100.0, 100.1, 99.9, 100.0)] * 7,
        entries={0: "long"},
    )
    market["regime_5m_rsi"] = [48.0] * 7
    market["regime_5m_rsi_ema"] = [50.0] * 7

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy(
            "five_minute_momentum_reversal",
            exit_on_5m_rsi_reversal=True,
        ),
        _config(maximum_hold_minutes=4),
    )

    assert report.trades[0].exit_reason == "maximum_hold"


def test_protective_stop_precedes_a_pending_signal_exit_after_gap() -> None:
    """The venue stop remains authoritative when the next open gaps through it."""
    market = _market(
        [
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 100.2, 99.9, 100.1),
            (100.1, 100.2, 100.0, 100.1),
            (98.0, 98.2, 97.8, 98.0),
            (98.0, 98.0, 98.0, 98.0),
        ],
        entries={0: "long"},
        states={2: "RANGE"},
    )

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("breakout_invalidation", exit_on_invalidation=True),
        _config(),
    )

    trade = report.trades[0]
    assert trade.exit_reason == "protective_stop"
    assert trade.exit_price == pytest.approx(98.0)


@pytest.mark.parametrize(
    ("side", "entry_open", "anchor", "minimum", "maximum", "expected_stop"),
    [
        ("long", 102.0, 98.0, 60.0, 150.0, 102.0 * (1.0 - 0.015)),
        ("long", 102.0, 101.5, 60.0, 150.0, 102.0 * (1.0 - 0.006)),
        ("long", 98.0, 99.0, 60.0, 150.0, 98.0 * (1.0 - 0.006)),
        ("short", 98.0, 102.0, 60.0, 150.0, 98.0 * (1.0 + 0.015)),
        ("short", 98.0, 98.4, 60.0, 150.0, 98.0 * (1.0 + 0.006)),
        ("short", 102.0, 101.0, 60.0, 150.0, 102.0 * (1.0 + 0.006)),
    ],
)
def test_structural_stop_anchor_uses_actual_fill_and_clamps_distance(
    side: str,
    entry_open: float,
    anchor: float,
    minimum: float,
    maximum: float,
    expected_stop: float,
) -> None:
    """A causal signal anchor must bind from the next-open fill like live."""
    market = _market(
        [
            (100.0, 100.2, 99.8, 100.0),
            (entry_open, entry_open, entry_open, entry_open),
            (entry_open, entry_open, entry_open, entry_open),
        ],
        entries={0: side},
    )
    market["candidate_stop_anchor"] = [anchor, float("nan"), float("nan")]
    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("structural_stop"),
        _config(
            stop_anchor_column="candidate_stop_anchor",
            minimum_stop_bps=minimum,
            maximum_stop_bps=maximum,
        ),
    )
    assert report.trades[0].stop_price == pytest.approx(expected_stop)


def test_structural_stop_contract_rejects_missing_anchor_column() -> None:
    """A configured structural replay cannot silently fall back to fixed bps."""
    market = _market(
        [(100.0, 100.0, 100.0, 100.0)] * 3,
        entries={0: "long"},
    )

    with pytest.raises(ValueError, match="stop anchor column"):
        replay_hype_breakout_exits(
            market,
            HypeExitPolicy("structural_stop"),
            _config(
                stop_anchor_column="candidate_stop_anchor",
                minimum_stop_bps=60.0,
                maximum_stop_bps=120.0,
            ),
        )


def test_funding_at_entry_boundary_belongs_only_to_preexisting_position() -> None:
    """A position opened after an hourly settlement does not inherit that charge."""
    market = _market(
        [(100.0, 100.0, 100.0, 100.0)] * 5,
        entries={0: "long"},
        funding={1: 0.01, 2: 0.001},
    )

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("control"),
        _config(maximum_hold_minutes=2),
    )

    trade = report.trades[0]
    assert trade.funding_bps == pytest.approx(-10.0)
    assert trade.exit_reason == "maximum_hold"


def test_replay_serializes_overlapping_onsets_and_reports_costs() -> None:
    """Only one HYPE lifecycle may own capital while fees remain explicit."""
    market = _market(
        [(100.0, 100.1, 99.9, 100.0)] * 8,
        entries={0: "long", 2: "short", 5: "short"},
        structural={5: "short"},
    )

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("control"),
        _config(maximum_hold_minutes=3, fee_bps_per_side=4.5),
    )

    assert report.completed_trades == 2
    assert [trade.side for trade in report.trades] == ["long", "short"]
    assert report.occupied_signals == 1
    assert report.total_fee_bps == pytest.approx(18.0)
    assert report.execution_authority == "none"


def test_opposite_entry_signal_closes_without_same_cycle_reversal() -> None:
    """Live-parity opposite intent closes next open without reversing immediately."""
    market = _market(
        [
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 100.0, 100.0, 100.0),
            (102.0, 102.0, 102.0, 102.0),
            (103.0, 103.0, 103.0, 103.0),
            (104.0, 104.0, 104.0, 104.0),
        ],
        entries={0: "long", 2: "short"},
    )

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("live_router_parity"),
        _config(
            stop_bps=500.0,
            maximum_hold_minutes=10,
            exit_on_opposite_signal=True,
        ),
    )

    assert report.completed_trades == 1
    assert report.occupied_signals == 1
    assert report.trades[0].exit_time_utc == market.index[3].isoformat()
    assert report.trades[0].exit_reason == "opposite_strategy_intent"
    assert report.trades[0].gross_return_bps == pytest.approx(300.0)


def test_long_only_authority_keeps_short_onset_as_exit_only() -> None:
    """A disabled short side may close a long but cannot open short exposure."""
    market = _market(
        [(100.0, 100.0, 100.0, 100.0)] * 7,
        entries={0: "long", 2: "short", 4: "short"},
    )

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("long_only"),
        _config(exit_on_opposite_signal=True),
        entry_sides=("long",),
    )

    assert report.completed_trades == 1
    assert report.trades[0].side == "long"
    assert report.trades[0].exit_reason == "opposite_strategy_intent"


@pytest.mark.parametrize("entry_sides", [(), ("long", "long"), ("flat",)])
def test_entry_authority_requires_unique_supported_sides(
    entry_sides: tuple[str, ...],
) -> None:
    """Directional research authority must be explicit and unambiguous."""
    with pytest.raises(ValueError, match="entry_sides"):
        replay_hype_breakout_exits(
            _market([(100.0, 100.0, 100.0, 100.0)] * 2),
            HypeExitPolicy("invalid_sides"),
            _config(),
            entry_sides=entry_sides,
        )


def test_trade_records_conservative_favorable_and_adverse_excursion() -> None:
    """MFE and MAE use only bars survived before the lifecycle exit."""
    market = _market(
        [
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 102.0, 99.5, 101.0),
            (101.0, 103.0, 100.0, 102.0),
            (102.0, 102.0, 102.0, 102.0),
        ],
        entries={0: "long"},
    )

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("control"),
        _config(stop_bps=200.0, maximum_hold_minutes=2),
    )

    trade = report.trades[0]
    assert trade.maximum_favorable_excursion_bps == pytest.approx(300.0)
    assert trade.maximum_adverse_excursion_bps == pytest.approx(50.0)


def test_supported_soft_deadline_extends_until_the_hard_deadline() -> None:
    """Live-parity structure support may extend, but never beyond its hard cap."""
    market = _market(
        [(100.0, 100.1, 99.9, 100.0)] * 7,
        entries={0: "long"},
    )
    config = _config(
        maximum_hold_minutes=2,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=4,
    )

    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy("live_extension"),
        config,
    )

    trade = report.trades[0]
    assert trade.exit_time_utc == market.index[5].isoformat()
    assert trade.exit_reason == "hard_maximum_hold"


def test_extension_rejects_missing_causal_regime_context() -> None:
    """An extension replay must not silently invent missing 1m or 15m state."""
    market = _market(
        [(100.0, 100.1, 99.9, 100.0)] * 5,
        entries={0: "long"},
    ).drop(columns="context_15m")
    config = _config(
        maximum_hold_minutes=2,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=4,
    )

    with pytest.raises(ValueError, match="extension market missing columns"):
        replay_hype_breakout_exits(market, HypeExitPolicy("extension"), config)


def test_profit_protection_arms_after_activation_bar_then_trails() -> None:
    """The activation bar cannot use its own unknown intrabar retracement."""
    market = _market(
        [
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 100.30, 100.15, 100.20),
            (100.25, 100.25, 100.15, 100.20),
            (100.20, 100.20, 100.20, 100.20),
        ],
        entries={0: "long"},
    )
    policy = HypeExitPolicy(
        "profit_protection",
        profit_activation_bps=20.0,
        profit_floor_bps=10.0,
        trailing_giveback_bps=10.0,
    )

    report = replay_hype_breakout_exits(market, policy, _config())

    trade = report.trades[0]
    assert trade.exit_time_utc == market.index[2].isoformat()
    assert trade.exit_reason == "profit_protection"
    assert trade.gross_return_bps == pytest.approx(20.0)


def test_short_profit_protection_is_directionally_symmetric() -> None:
    """A short trails the completed low and buys back above that trough."""
    market = _market(
        [
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 99.85, 99.70, 99.80),
            (99.75, 99.85, 99.75, 99.80),
            (99.80, 99.80, 99.80, 99.80),
        ],
        entries={0: "short"},
        structural={0: "short", 1: "short", 2: "short", 3: "short"},
    )
    policy = HypeExitPolicy(
        "profit_protection",
        profit_activation_bps=20.0,
        profit_floor_bps=10.0,
        trailing_giveback_bps=10.0,
    )

    report = replay_hype_breakout_exits(market, policy, _config())

    trade = report.trades[0]
    assert trade.exit_reason == "profit_protection"
    assert trade.gross_return_bps == pytest.approx(20.0)


def test_profit_exit_blocks_same_side_reentry_until_structural_reset() -> None:
    """A protected exit must not churn the same unresolved structural episode."""
    market = _market(
        [
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 100.30, 100.15, 100.20),
            (100.25, 100.25, 100.15, 100.20),
            (100.20, 100.20, 100.20, 100.20),
            (100.20, 100.20, 100.20, 100.20),
            (100.20, 100.20, 100.20, 100.20),
            (100.20, 100.20, 100.20, 100.20),
            (100.20, 100.20, 100.20, 100.20),
        ],
        entries={0: "long", 2: "long", 3: "long", 5: "long"},
        structural={4: "neutral"},
    )
    policy = HypeExitPolicy(
        "profit_protection_with_reset",
        profit_activation_bps=20.0,
        profit_floor_bps=10.0,
        trailing_giveback_bps=10.0,
        reentry_requires_structural_reset=True,
    )

    report = replay_hype_breakout_exits(market, policy, _config())

    assert report.completed_trades == 2
    assert report.trades[1].signal_time_utc == market.index[5].isoformat()
    assert report.reset_blocked_signals == 2


@pytest.mark.parametrize(
    "values",
    [
        {"profit_activation_bps": 20.0},
        {
            "profit_activation_bps": 10.0,
            "profit_floor_bps": 20.0,
            "trailing_giveback_bps": 5.0,
        },
    ],
)
def test_profit_protection_policy_requires_a_coherent_complete_triplet(
    values: dict[str, float],
) -> None:
    """Partial or economically inverted profit protection is rejected."""
    with pytest.raises(ValueError, match="profit protection"):
        HypeExitPolicy("invalid", **values)
