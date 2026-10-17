"""Causal post-only maker replay for backend Hypervelocity decisions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

import hypervector.research.maker_replay_stream as maker_replay_stream
from hypervector.cli import main
from hypervector.data.oxa_archive_audit import OxaArchiveBundle
from hypervector.research.maker_replay import MakerReplayConfig, replay_maker_orders
from hypervector.research.maker_replay_models import (
    MakerReplayLifecycle,
    OpenPosition,
    ReplayState,
)
from hypervector.research.maker_replay_stream import (
    MakerReplayEvidenceChunk,
    replay_maker_order_chunks,
)
from hypervector.research.maker_replay_validation import validate_book, validate_trades


def _decisions(states: list[str]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(states), freq="1min", tz="UTC")
    return pd.DataFrame(
        {"primary_regime": states, "breakout_direction": [None] * len(states)},
        index=index,
    )


def _entry_decisions(
    entries: list[str | None],
    structural: list[str | None],
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(entries), freq="1min", tz="UTC")
    return pd.DataFrame(
        {"entry_direction": entries, "structural_direction": structural},
        index=index,
    )


def _book(
    seconds: list[int],
    bids: list[float],
    asks: list[float],
) -> pd.DataFrame:
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    times = [origin + pd.Timedelta(seconds=value) for value in seconds]
    return pd.DataFrame(
        {
            "ts_ms": [int(value.timestamp() * 1000) for value in times],
            "best_bid": bids,
            "best_ask": asks,
        }
    )


def _trades(
    seconds: list[int],
    sides: list[str],
    prices: list[float],
    sizes: list[float] | None = None,
) -> pd.DataFrame:
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    times = [origin + pd.Timedelta(seconds=value) for value in seconds]
    return pd.DataFrame(
        {
            "ts_ms": [int(value.timestamp() * 1000) for value in times],
            "trade_id": list(range(1, len(times) + 1)),
            "aggressor_side": sides,
            "price": prices,
            "size": sizes or [1.0] * len(times),
        }
    )


@pytest.mark.parametrize("field", ["maker_fee_rate", "taker_fee_rate"])
def test_replay_config_rejects_invalid_fee_rates(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        MakerReplayConfig(**{field: -0.0001})
    with pytest.raises(ValueError, match=field):
        MakerReplayConfig(**{field: 1.0})


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan"), True])
def test_replay_config_rejects_invalid_entry_spread_cap(value: object) -> None:
    with pytest.raises(ValueError, match="maximum_entry_spread_bps"):
        MakerReplayConfig(maximum_entry_spread_bps=value)


def test_entry_spread_cap_consumes_dislocated_signal_once() -> None:
    report = replay_maker_orders(
        _book(
            [60, 61, 70],
            [100.0, 100.0, 100.0],
            [100.04, 100.001, 100.001],
        ),
        _entry_decisions(["short"] * 3, ["short"] * 3),
        MakerReplayConfig(
            fill_rule="touch",
            maximum_entry_spread_bps=1.0,
        ),
    )

    assert report.spread_rejected_entries == 1
    assert report.submitted_entries == 0
    assert report.entry_fills == 0
    assert report.lifecycles == ()


@pytest.mark.parametrize("depth", [-1, 1.5, True])
def test_replay_config_rejects_invalid_entry_depth_ticks(depth: object) -> None:
    with pytest.raises(ValueError, match="entry_depth_ticks"):
        MakerReplayConfig(entry_depth_ticks=depth)


@pytest.mark.parametrize(
    ("state", "bids", "asks", "expected_entry"),
    [
        ("TREND_UP", [100.0, 98.0, 99.2], [101.0, 99.0, 99.3], 99.0),
        ("TREND_DOWN", [100.0, 102.0, 101.6], [101.0, 103.0, 101.7], 102.0),
    ],
)
def test_one_tick_entry_depth_moves_limit_in_passive_direction(
    state: str,
    bids: list[float],
    asks: list[float],
    expected_entry: float,
) -> None:
    report = replay_maker_orders(
        _book([60, 70, 80], bids, asks),
        _decisions([state] * 3),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            tick_size=1.0,
            entry_depth_ticks=1,
        ),
    )

    assert report.completed_trades == 1
    assert report.trades[0].entry_price == pytest.approx(expected_entry)


def test_touch_replay_compounds_70pct_margin_at_40x() -> None:
    decisions = _decisions(["TREND_UP", "TREND_UP", "TREND_UP"])
    book = _book(
        [60, 70, 80],
        [100.0, 99.0, 100.2],
        [101.0, 100.0, 100.3],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
        ),
    )

    assert report.completed_trades == 1
    trade = report.trades[0]
    assert trade.margin == pytest.approx(70.0)
    assert trade.notional == pytest.approx(2_800.0)
    assert trade.quantity == pytest.approx(28.0)
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(100.2)
    assert report.final_equity == pytest.approx(105.6)
    assert len(report.lifecycles) == 1
    assert report.lifecycles[0].status == "target_completed"
    assert report.lifecycles[0].entry_time_utc == "2026-01-01T00:01:10+00:00"
    assert report.lifecycles[0].outcome_time_utc == "2026-01-01T00:01:20+00:00"


def test_replay_liquidates_at_isolated_boundary_and_marks_drawdown() -> None:
    decisions = _decisions(["TREND_UP"] * 3)
    book = _book(
        [60, 70, 80],
        [100.0, 99.0, 98.0],
        [101.0, 100.0, 98.1],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.00045,
            fill_rule="touch",
        ),
    )

    assert report.liquidations == 1
    assert report.completed_trades == 1
    assert report.open_positions == 0
    assert report.trades[0].status == "liquidated"
    assert report.lifecycles[0].status == "liquidated"
    assert report.final_equity == pytest.approx(42.7652)
    assert report.maximum_drawdown_pct == pytest.approx(-57.2348)


@pytest.mark.parametrize(
    ("states", "expected_exits"),
    [
        (["TREND_UP", "TREND_UP", "RANGE", "RANGE"], 0),
        (["TREND_UP", "TREND_UP", "TREND_UP", "TREND_UP"], 0),
        (["TREND_UP", "TREND_UP", "TREND_DOWN", "TREND_DOWN"], 1),
    ],
)
def test_opposite_regime_exit_ignores_range_and_same_side_structure(
    states: list[str],
    expected_exits: int,
) -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 120, 180],
            [100.0, 99.0, 99.5, 99.5],
            [101.0, 100.0, 100.5, 100.5],
        ),
        _decisions(states),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.001,
            fill_rule="touch",
            opposite_regime_exit=True,
        ),
    )

    assert report.regime_exits == expected_exits
    assert report.open_positions == 1 - expected_exits


@pytest.mark.parametrize(
    ("states", "bids", "asks", "expected_exit", "expected_equity"),
    [
        (
            ["TREND_UP", "TREND_UP", "TREND_DOWN", "TREND_DOWN"],
            [100.0, 99.0, 99.5, 99.5],
            [101.0, 100.0, 100.5, 100.5],
            99.5,
            83.214,
        ),
        (
            ["TREND_DOWN", "TREND_DOWN", "TREND_UP", "TREND_UP"],
            [99.0, 100.0, 99.5, 99.5],
            [100.0, 101.0, 100.5, 100.5],
            100.5,
            83.186,
        ),
    ],
)
def test_opposite_regime_exit_uses_adverse_bbo_and_taker_fee(
    states: list[str],
    bids: list[float],
    asks: list[float],
    expected_exit: float,
    expected_equity: float,
) -> None:
    report = replay_maker_orders(
        _book([60, 70, 120, 180], bids, asks),
        _decisions(states),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.001,
            fill_rule="touch",
            opposite_regime_exit=True,
        ),
    )

    assert report.regime_exits == 1
    assert report.completed_trades == 1
    assert report.trades[0].status == "regime_exited"
    assert report.trades[0].exit_price == pytest.approx(expected_exit)
    assert report.lifecycles[0].status == "regime_exited"
    assert report.final_equity == pytest.approx(expected_equity)


def test_liquidation_precedes_opposite_regime_exit_on_same_snapshot() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 120, 180],
            [100.0, 99.0, 99.0, 98.0],
            [101.0, 100.0, 100.0, 98.1],
        ),
        _decisions(["TREND_UP", "TREND_UP", "TREND_DOWN", "TREND_DOWN"]),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.001,
            fill_rule="touch",
            opposite_regime_exit=True,
        ),
    )

    assert report.liquidations == 1
    assert report.regime_exits == 0
    assert report.trades[0].status == "liquidated"


def test_replay_config_rejects_non_boolean_opposite_entry_close_reverse() -> None:
    with pytest.raises(ValueError, match="opposite_entry_close_reverse"):
        MakerReplayConfig(opposite_entry_close_reverse=1)


@pytest.mark.parametrize(
    ("entries", "structural"),
    [
        (["long", "long", None, None], ["long", "long", None, None]),
        (["long", "long", None, None], ["long", "long", "short", "short"]),
        (["long", "long", "long", "long"], ["long"] * 4),
        (["long", "long", "short", "short"], ["long", "long", "short", "short"]),
    ],
)
def test_opposite_entry_close_reverse_is_disabled_by_default(
    entries: list[str | None],
    structural: list[str | None],
) -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 180, 181],
            [100.0, 99.0, 99.5, 99.5],
            [101.0, 100.0, 100.5, 100.5],
        ),
        _entry_decisions(entries, structural),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.001,
            fill_rule="touch",
        ),
    )

    assert report.close_reversals == 0
    assert report.open_positions == 1
    assert report.submitted_entries == 1


@pytest.mark.parametrize(
    ("entries", "structural"),
    [
        (["long", "long", None, None], ["long", "long", None, None]),
        (["long", "long", None, None], ["long", "long", "short", "short"]),
        (["long", "long", "long", "long"], ["long"] * 4),
        (["long", "long", "short", "short"], ["long"] * 4),
    ],
)
def test_opposite_entry_close_reverse_requires_entry_and_structure_agreement(
    entries: list[str | None],
    structural: list[str | None],
) -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 180, 181],
            [100.0, 99.0, 99.5, 99.5],
            [101.0, 100.0, 100.5, 100.5],
        ),
        _entry_decisions(entries, structural),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.001,
            fill_rule="touch",
            opposite_entry_close_reverse=True,
        ),
    )

    assert report.close_reversals == 0
    assert report.open_positions == 1
    assert report.submitted_entries == 1


def test_opposite_entry_closes_and_submits_atomic_reverse_without_same_tick_fill() -> (
    None
):
    report = replay_maker_orders(
        _book(
            [60, 70, 180, 181],
            [100.0, 99.0, 99.5, 101.0],
            [101.0, 100.0, 100.5, 101.1],
        ),
        _entry_decisions(
            ["long", "long", "short", "short"],
            ["long", "long", "short", "short"],
        ),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.001,
            fill_rule="touch",
            reentry_cooldown_seconds=60.0,
            opposite_entry_close_reverse=True,
        ),
    )

    assert report.close_reversals == 1
    assert report.completed_trades == 1
    assert report.submitted_entries == 2
    assert report.entry_fills == 2
    assert report.open_positions == 1
    assert report.pending_orders == 0
    assert report.trades[0].status == "reversed"
    assert report.trades[0].exit_price == pytest.approx(99.5)
    assert report.trades[0].fees == pytest.approx(2.786)
    assert report.lifecycles[0].status == "reversed"
    assert report.lifecycles[1].direction == "short"
    assert report.lifecycles[1].submitted_time_utc == "2026-01-01T00:03:00+00:00"
    assert report.lifecycles[1].entry_time_utc == "2026-01-01T00:03:01+00:00"


def test_liquidation_precedes_opposite_entry_close_reverse() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 180, 181],
            [100.0, 99.0, 98.0, 101.0],
            [101.0, 100.0, 98.1, 101.1],
        ),
        _entry_decisions(
            ["long", "long", "short", "short"],
            ["long", "long", "short", "short"],
        ),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.001,
            fill_rule="touch",
            opposite_entry_close_reverse=True,
        ),
    )

    assert report.liquidations == 1
    assert report.close_reversals == 0
    assert report.submitted_entries == 1
    assert report.trades[0].status == "liquidated"


def _open_replay_state() -> ReplayState:
    lifecycle = MakerReplayLifecycle(
        0,
        "long",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:01+00:00",
        "2026-01-01T00:02:00+00:00",
        None,
        "open",
        100.0,
        None,
        28.0,
        None,
        None,
    )
    position = OpenPosition(
        0,
        "long",
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-01T00:00:01Z"),
        pd.Timestamp("2026-01-01T00:02:00Z"),
        100.0,
        28.0,
        70.0,
        2_800.0,
        100.2,
        initial_quantity=28.0,
        funding_cashflow=3.0,
    )
    return ReplayState(
        equity=103.0,
        position=position,
        lifecycles=[lifecycle],
        peak_equity=103.0,
    )


def test_opposite_entry_signal_must_be_newer_than_position_fill() -> None:
    from hypervector.research.maker_replay_risk import (
        apply_book_entry_close_reverse,
    )

    state = _open_replay_state()
    closed = apply_book_entry_close_reverse(
        state,
        pd.Timestamp("2026-01-01T00:03:00Z"),
        99.5,
        100.5,
        "short",
        "short",
        pd.Timestamp("2026-01-01T00:01:00Z"),
        MakerReplayConfig(opposite_entry_close_reverse=True),
    )

    assert closed is False
    assert state.position is not None
    assert state.close_reversals == 0


def test_opposite_entry_close_retains_funding_and_charges_taker_fee() -> None:
    from hypervector.research.maker_replay_risk import (
        apply_book_entry_close_reverse,
    )

    state = _open_replay_state()
    closed = apply_book_entry_close_reverse(
        state,
        pd.Timestamp("2026-01-01T00:03:01Z"),
        99.5,
        100.5,
        "short",
        "short",
        pd.Timestamp("2026-01-01T00:03:00Z"),
        MakerReplayConfig(
            maker_fee_rate=0.0,
            taker_fee_rate=0.001,
            opposite_entry_close_reverse=True,
        ),
    )

    assert closed is True
    assert state.position is None
    assert state.close_reversals == 1
    assert state.equity == pytest.approx(86.214)
    assert state.trades[0].fees == pytest.approx(2.786)
    assert state.trades[0].funding_cashflow == pytest.approx(3.0)
    assert state.trades[0].net_pnl == pytest.approx(-13.786)


def test_large_replay_position_partially_liquidates_then_closes_in_cooldown() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 80, 90],
            [100.0, 99.0, 98.7, 98.7],
            [101.0, 100.0, 98.71, 98.71],
        ),
        _decisions(["TREND_UP"] * 4),
        MakerReplayConfig(
            initial_equity=10_000.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.00045,
            fill_rule="touch",
        ),
    )

    assert report.partial_liquidations == 1
    assert report.liquidations == 1
    assert report.trades[0].quantity == pytest.approx(2_800.0)
    assert report.final_equity == pytest.approx(6_235.638)


def test_partial_liquidation_scales_only_open_cost_basis() -> None:
    """Partial liquidation must not load all historical costs onto residue."""
    from hypervector.research.maker_replay_risk import (
        apply_book_liquidation,
        position_liquidation_price,
    )

    position = OpenPosition(
        lifecycle_id=0,
        direction="long",
        signal_time=pd.Timestamp("2026-01-01T00:00:00Z"),
        submitted_time=pd.Timestamp("2026-01-01T00:00:01Z"),
        entry_time=pd.Timestamp("2026-01-01T00:00:02Z"),
        entry_price=100.0,
        quantity=2_800.0,
        margin=7_000.0,
        notional=280_000.0,
        target_price=100.2,
        initial_quantity=2_800.0,
        entry_fee=42.0,
        funding_cashflow=-28.0,
    )
    state = ReplayState(
        equity=9_930.0,
        position=position,
        peak_equity=10_000.0,
    )
    boundary = position_liquidation_price(position)

    applied = apply_book_liquidation(
        state,
        pd.Timestamp("2026-01-01T00:01:00Z"),
        boundary - 0.01,
        boundary + 0.01,
        MakerReplayConfig(taker_fee_rate=0.00045),
        trigger_mark=boundary,
    )

    assert applied is True
    assert state.partial_liquidations == 1
    assert position.quantity == pytest.approx(2_240.0)
    assert position.funding_cashflow == pytest.approx(-28.0)
    assert position.open_fee_basis == pytest.approx(33.6)
    assert position.open_funding_basis == pytest.approx(-22.4)
    assert position_liquidation_price(position) == pytest.approx(boundary)


def test_replay_does_not_repeat_same_direction_without_regime_reset() -> None:
    decisions = _decisions(
        ["TREND_UP", "TREND_UP", "TREND_UP", "TREND_UP", "RANGE", "TREND_UP"]
    )
    book = _book(
        [60, 70, 80, 90, 120, 300, 360],
        [100.0, 99.0, 100.2, 100.2, 100.2, 100.0, 100.0],
        [101.0, 100.0, 100.3, 100.3, 100.3, 101.0, 101.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(initial_equity=100.0, maker_fee_rate=0.0, fill_rule="touch"),
    )

    assert report.completed_trades == 1
    assert report.submitted_entries == 2
    assert report.submission_times_utc == (
        "2026-01-01T00:01:00+00:00",
        "2026-01-01T00:06:00+00:00",
    )


def test_cooldown_only_reentry_waits_then_reuses_same_direction() -> None:
    decisions = _decisions(["TREND_UP"] * 5)
    book = _book(
        [60, 70, 80, 90, 139, 140],
        [100.0, 99.0, 100.2, 100.0, 100.0, 100.0],
        [101.0, 100.0, 100.3, 101.0, 101.0, 101.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            reentry_cooldown_seconds=60.0,
            same_direction_reentry_policy="cooldown_only",
        ),
    )

    assert report.completed_trades == 1
    assert report.submitted_entries == 2
    assert report.submission_times_utc == (
        "2026-01-01T00:01:00+00:00",
        "2026-01-01T00:02:20+00:00",
    )


def test_cooldown_only_does_not_rearm_expired_entry_in_same_regime() -> None:
    decisions = _decisions(["TREND_DOWN"] * 11)
    seconds = list(range(60, 661, 60))
    bids = [100.0 - float(index) for index in range(len(seconds))]
    asks = [bid + 1.0 for bid in bids]

    report = replay_maker_orders(
        _book(seconds, bids, asks),
        decisions,
        MakerReplayConfig(
            fill_rule="through",
            tick_size=1.0,
            same_direction_reentry_policy="cooldown_only",
        ),
    )

    assert report.expired_entries == 1
    assert report.submitted_entries == 1
    assert [row.status for row in report.lifecycles] == ["expired"]


def test_replay_config_rejects_unknown_same_direction_reentry_policy() -> None:
    with pytest.raises(ValueError, match="same_direction_reentry_policy"):
        MakerReplayConfig(same_direction_reentry_policy="immediate")


def test_target_continuation_requires_cooldown_and_fresh_clearance() -> None:
    decisions = _decisions(["TREND_UP"] * 6)
    book = _book(
        [60, 70, 80, 140, 149, 150],
        [100.0, 99.0, 100.2, 100.22, 100.23, 100.24],
        [101.0, 100.0, 100.3, 101.0, 101.0, 101.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            reentry_cooldown_seconds=60.0,
            same_direction_reentry_policy="target_continuation",
            same_direction_reentry_clearance_bps=3.0,
        ),
    )

    assert report.completed_trades == 1
    assert report.submission_times_utc == (
        "2026-01-01T00:01:00+00:00",
        "2026-01-01T00:02:30+00:00",
    )


def test_target_continuation_does_not_rearm_after_liquidation() -> None:
    decisions = _decisions(["TREND_UP"] * 5)
    book = _book(
        [60, 70, 80, 140, 180],
        [100.0, 99.0, 98.0, 100.0, 101.0],
        [101.0, 100.0, 98.1, 101.0, 102.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            reentry_cooldown_seconds=60.0,
            same_direction_reentry_policy="target_continuation",
        ),
    )

    assert report.liquidations == 1
    assert report.submitted_entries == 1


def test_liquidation_cooldown_consumes_fresh_signal_without_stale_submission() -> None:
    """A signal inside the liquidation cooldown cannot submit after it expires."""
    decisions = _entry_decisions(
        ["long", None, "long"],
        ["long", None, "long"],
    )
    book = _book(
        [60, 70, 80, 120, 180, 330],
        [100.0, 99.0, 98.0, 100.0, 100.0, 100.0],
        [101.0, 100.0, 98.1, 101.0, 101.0, 101.0],
    )

    control = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(initial_equity=100.0, fill_rule="touch"),
    )
    cooled = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            fill_rule="touch",
            liquidation_reentry_cooldown_seconds=240.0,
        ),
    )

    assert control.submitted_entries == 2
    assert cooled.liquidations == 1
    assert cooled.submitted_entries == 1


def test_liquidation_cooldown_allows_fresh_opposite_direction_signal() -> None:
    """A long liquidation cooldown does not suppress a fresh short signal."""
    report = replay_maker_orders(
        _book(
            [60, 70, 80, 120, 180],
            [100.0, 99.0, 98.0, 100.0, 100.0],
            [101.0, 100.0, 98.1, 101.0, 101.0],
        ),
        _entry_decisions(
            ["long", None, "short"],
            ["long", None, "short"],
        ),
        MakerReplayConfig(
            initial_equity=100.0,
            fill_rule="touch",
            liquidation_reentry_cooldown_seconds=240.0,
        ),
    )

    assert report.liquidations == 1
    assert report.submitted_entries == 2


def test_liquidation_cooldown_does_not_block_signal_after_target() -> None:
    """Only liquidation exits activate the extended cooldown."""
    report = replay_maker_orders(
        _book(
            [60, 70, 80, 120, 180],
            [100.0, 99.0, 100.2, 100.0, 100.0],
            [101.0, 100.0, 100.3, 101.0, 101.0],
        ),
        _entry_decisions(
            ["long", None, "long"],
            ["long", None, "long"],
        ),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            liquidation_reentry_cooldown_seconds=240.0,
        ),
    )

    assert report.completed_trades == 1
    assert report.trades[0].status == "target_completed"
    assert report.submitted_entries == 2


@pytest.mark.parametrize("seconds", [-1.0, float("inf"), float("nan"), True])
def test_replay_config_rejects_invalid_liquidation_cooldown(seconds: object) -> None:
    """Liquidation cooldowns must be finite non-negative durations."""
    with pytest.raises(ValueError, match="liquidation_reentry_cooldown_seconds"):
        MakerReplayConfig(liquidation_reentry_cooldown_seconds=seconds)


def test_replay_config_rejects_negative_reentry_clearance() -> None:
    with pytest.raises(ValueError, match="same_direction_reentry_clearance_bps"):
        MakerReplayConfig(same_direction_reentry_clearance_bps=-0.1)


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_replay_config_rejects_invalid_target_continuation_limit(
    limit: object,
) -> None:
    with pytest.raises(ValueError, match="target_continuation_limit_per_episode"):
        MakerReplayConfig(
            same_direction_reentry_policy="target_continuation",
            target_continuation_limit_per_episode=limit,
        )


def test_replay_config_rejects_target_limit_for_other_policy() -> None:
    with pytest.raises(ValueError, match="requires a target re-entry policy"):
        MakerReplayConfig(target_continuation_limit_per_episode=2)


@pytest.mark.parametrize("minimum_seconds", [-1.0, float("nan"), True])
def test_replay_config_rejects_invalid_mature_continuation_duration(
    minimum_seconds: object,
) -> None:
    with pytest.raises(
        ValueError,
        match="target_continuation_minimum_episode_seconds",
    ):
        MakerReplayConfig(
            same_direction_reentry_policy="target_continuation",
            target_continuation_minimum_episode_seconds=minimum_seconds,
        )


def test_replay_config_rejects_mature_duration_for_other_policy() -> None:
    with pytest.raises(ValueError, match="requires a target re-entry policy"):
        MakerReplayConfig(target_continuation_minimum_episode_seconds=1_800.0)


def test_target_continuation_waits_for_mature_structural_episode() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 80, 140, 179, 180],
            [100.0, 99.0, 100.2, 100.2, 100.2, 100.2],
            [101.0, 100.0, 100.3, 101.0, 101.0, 101.0],
        ),
        _decisions(["TREND_UP"] * 5),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            reentry_cooldown_seconds=0.0,
            same_direction_reentry_policy="target_continuation",
            target_continuation_minimum_episode_seconds=120.0,
        ),
    )

    assert report.submission_times_utc == (
        "2026-01-01T00:01:00+00:00",
        "2026-01-01T00:03:00+00:00",
    )


def test_target_ladder_cap_blocks_third_target_in_one_episode() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 80, 140, 150, 160, 220],
            [100.0, 99.0, 100.2, 100.2, 99.2, 100.41, 100.41],
            [101.0, 100.0, 100.3, 101.0, 100.2, 100.5, 101.0],
        ),
        _decisions(["TREND_UP"] * 5),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            same_direction_reentry_policy="target_continuation",
            target_continuation_limit_per_episode=2,
        ),
    )

    assert report.completed_trades == 2
    assert report.submitted_entries == 2


def test_target_ladder_count_resets_on_new_structural_episode() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 80, 140, 150, 160, 180, 240, 250, 260],
            [100.0, 99.0, 100.2, 100.2, 99.2, 100.41, 100.41, 100.4, 99.4, 100.61],
            [101.0, 100.0, 100.3, 101.0, 100.2, 100.5, 101.0, 101.0, 100.4, 100.7],
        ),
        _decisions(["TREND_UP", "TREND_UP", "RANGE", "TREND_UP", "TREND_UP"]),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            same_direction_reentry_policy="target_continuation",
            target_continuation_limit_per_episode=2,
        ),
    )

    assert report.completed_trades == 3
    assert report.submitted_entries == 3


def test_target_ladder_does_not_rearm_after_liquidation() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 80, 140, 180],
            [100.0, 99.0, 98.0, 100.0, 101.0],
            [101.0, 100.0, 98.1, 101.0, 102.0],
        ),
        _decisions(["TREND_UP"] * 5),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
            same_direction_reentry_policy="target_continuation",
            target_continuation_limit_per_episode=2,
        ),
    )

    assert report.liquidations == 1
    assert report.submitted_entries == 1


@pytest.mark.parametrize("fraction", [0.0, 1.0, float("nan")])
def test_replay_config_rejects_invalid_liquidation_stop_fraction(
    fraction: float,
) -> None:
    with pytest.raises(ValueError, match="liquidation_proximity_stop_fraction"):
        MakerReplayConfig(liquidation_proximity_stop_fraction=fraction)


@pytest.mark.parametrize("margin_pct", [0.0, 100.0, float("nan")])
def test_replay_config_rejects_invalid_fixed_margin_stop(
    margin_pct: float,
) -> None:
    with pytest.raises(ValueError, match="fixed_margin_stop_pct"):
        MakerReplayConfig(fixed_margin_stop_pct=margin_pct)


def test_replay_config_rejects_two_stop_models() -> None:
    with pytest.raises(ValueError, match="only one maker-replay stop"):
        MakerReplayConfig(
            liquidation_proximity_stop_fraction=0.75,
            fixed_margin_stop_pct=2.0,
        )


def test_fixed_margin_stop_converts_levered_loss_and_uses_adverse_bbo() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 80],
            [100.0, 99.0, 99.94],
            [101.0, 100.0, 100.04],
        ),
        _decisions(["TREND_UP"] * 3),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
            fixed_margin_stop_pct=2.0,
        ),
    )

    assert report.stops == 1
    assert report.liquidations == 0
    assert report.trades[0].status == "stopped"
    assert report.trades[0].exit_price == pytest.approx(99.94)
    assert report.lifecycles[0].stop_price == pytest.approx(99.95)
    assert report.final_equity == pytest.approx(98.32)


def test_fixed_margin_stop_is_symmetric_for_short_positions() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 80],
            [100.0, 101.0, 100.96],
            [101.0, 102.0, 101.06],
        ),
        _decisions(["TREND_DOWN"] * 3),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
            fixed_margin_stop_pct=2.0,
        ),
    )

    assert report.stops == 1
    assert report.trades[0].direction == "short"
    assert report.trades[0].exit_price == pytest.approx(101.06)
    assert report.lifecycles[0].stop_price == pytest.approx(101.0505)
    assert report.final_equity == pytest.approx(98.3366336634)


def test_decision_stop_freezes_at_submission_and_uses_adverse_bbo() -> None:
    decisions = _decisions(["TREND_UP"] * 3)
    decisions["entry_stop_price"] = 99.5
    report = replay_maker_orders(
        _book(
            [60, 70, 80],
            [100.0, 99.8, 99.4],
            [101.0, 100.0, 99.5],
        ),
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
        ),
    )

    assert report.stops == 1
    assert report.lifecycles[0].stop_price == pytest.approx(99.5)
    assert report.trades[0].exit_price == pytest.approx(99.4)
    assert report.final_equity == pytest.approx(83.2)


def test_decision_stop_outside_entry_and_liquidation_is_ignored() -> None:
    decisions = _decisions(["TREND_UP"] * 3)
    decisions["entry_stop_price"] = 100.5
    report = replay_maker_orders(
        _book(
            [60, 70, 80],
            [100.0, 99.8, 99.6],
            [101.0, 100.0, 99.7],
        ),
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
        ),
    )

    assert report.stops == 0
    assert report.open_positions == 1
    assert report.lifecycles[0].stop_price is None


def test_decision_stop_rejects_static_stop_model_conflict() -> None:
    decisions = _decisions(["TREND_UP"] * 2)
    decisions["entry_stop_price"] = 99.5

    with pytest.raises(ValueError, match="decision stop cannot coexist"):
        replay_maker_orders(
            _book([60, 70], [100.0, 99.8], [101.0, 100.0]),
            decisions,
            MakerReplayConfig(fill_rule="touch", fixed_margin_stop_pct=2.0),
        )


def test_liquidation_proximity_stop_closes_at_adverse_bbo_with_taker_fee() -> None:
    report = replay_maker_orders(
        _book(
            [60, 70, 80],
            [100.0, 99.0, 98.7],
            [101.0, 100.0, 98.8],
        ),
        _decisions(["TREND_UP"] * 3),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.00045,
            fill_rule="touch",
            liquidation_proximity_stop_fraction=0.75,
        ),
    )

    assert report.stops == 1
    assert report.liquidations == 0
    assert report.completed_trades == 1
    assert report.trades[0].status == "stopped"
    assert report.trades[0].exit_price == pytest.approx(98.7)
    assert report.lifecycles[0].status == "stopped"
    assert report.lifecycles[0].stop_price is not None
    assert report.final_equity == pytest.approx(62.35638)


def test_streaming_replay_carries_pending_entry_across_chunks() -> None:
    """An hourly boundary cannot reset a still-live maker entry."""
    chunks = (
        MakerReplayEvidenceChunk(_book([60], [100.0], [101.0])),
        MakerReplayEvidenceChunk(_book([70, 80], [99.0, 100.2], [100.0, 100.3])),
    )

    report = replay_maker_order_chunks(
        chunks,
        _decisions(["TREND_UP", "TREND_UP", "TREND_UP"]),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
        ),
    )

    assert report.submitted_entries == 1
    assert report.entry_fills == 1
    assert report.completed_trades == 1


def test_streaming_replay_carries_open_position_across_chunks() -> None:
    """A position opened before a boundary may close after that boundary."""
    chunks = (
        MakerReplayEvidenceChunk(_book([60, 70], [100.0, 99.0], [101.0, 100.0])),
        MakerReplayEvidenceChunk(_book([80], [100.2], [100.3])),
    )

    report = replay_maker_order_chunks(
        chunks,
        _decisions(["TREND_UP", "TREND_UP", "TREND_UP"]),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
        ),
    )

    assert report.completed_trades == 1
    assert report.open_positions == 0


def test_streaming_grid_matches_independent_candidate_replays() -> None:
    """One validated tape must preserve isolated per-candidate replay results."""
    assert hasattr(maker_replay_stream, "replay_maker_order_grid_chunks")
    replay_grid = maker_replay_stream.replay_maker_order_grid_chunks
    chunks = (
        MakerReplayEvidenceChunk(_book([60, 70], [100.0, 99.0], [101.0, 100.0])),
        MakerReplayEvidenceChunk(_book([80], [99.7], [99.8])),
    )
    decisions = _decisions(["TREND_UP", "TREND_UP", "TREND_UP"])
    configs = {
        "control": MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
        ),
        "stop_10": MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
            fixed_margin_stop_pct=10.0,
        ),
    }
    expected = {
        name: replay_maker_order_chunks(chunks, decisions, config)
        for name, config in configs.items()
    }

    actual = replay_grid(chunks, decisions, configs)

    assert {name: report.to_dict() for name, report in actual.items()} == {
        name: report.to_dict() for name, report in expected.items()
    }


def test_streaming_decision_grid_matches_independent_replays() -> None:
    """Candidate decisions may differ while consuming one physical tape."""
    assert hasattr(maker_replay_stream, "replay_maker_order_decision_grid_chunks")
    replay_grid = maker_replay_stream.replay_maker_order_decision_grid_chunks
    chunks = (
        MakerReplayEvidenceChunk(_book([60, 70], [100.0, 99.0], [101.0, 100.0])),
        MakerReplayEvidenceChunk(_book([80], [102.0], [103.0])),
    )
    decisions = {
        "long": _decisions(["TREND_UP"] * 3),
        "short": _decisions(["TREND_DOWN"] * 3),
    }
    configs = {
        name: MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
        )
        for name in decisions
    }
    expected = {
        name: replay_maker_order_chunks(chunks, decisions[name], configs[name])
        for name in configs
    }

    actual = replay_grid(chunks, decisions, configs)

    assert {name: report.to_dict() for name, report in actual.items()} == {
        name: report.to_dict() for name, report in expected.items()
    }


def test_streaming_decision_grid_rejects_candidate_name_mismatch() -> None:
    replay_grid = maker_replay_stream.replay_maker_order_decision_grid_chunks
    decisions = {"control": _decisions(["TREND_UP"])}
    configs = {"candidate": MakerReplayConfig(fill_rule="touch")}

    with pytest.raises(ValueError, match="decision and config candidate names"):
        replay_grid((), decisions, configs)


@pytest.mark.parametrize("index_kind", ["duplicate", "descending", "naive"])
def test_streaming_decision_grid_rejects_invalid_decision_index(
    index_kind: str,
) -> None:
    replay_grid = maker_replay_stream.replay_maker_order_decision_grid_chunks
    decisions = _decisions(["TREND_UP", "TREND_UP"])
    if index_kind == "duplicate":
        decisions.index = pd.DatetimeIndex([decisions.index[0], decisions.index[0]])
    elif index_kind == "descending":
        decisions = decisions.sort_index(ascending=False)
    else:
        decisions.index = decisions.index.tz_localize(None)

    with pytest.raises(ValueError, match="unique, chronological, and timezone-aware"):
        replay_grid(
            (),
            {"candidate": decisions},
            {"candidate": MakerReplayConfig(fill_rule="touch")},
        )


def test_streaming_replay_deduplicates_exact_book_boundary() -> None:
    """An inclusive hourly boundary contributes one identical book event."""
    boundary = _book([70], [99.0], [100.0])
    chunks = (
        MakerReplayEvidenceChunk(
            pd.concat((_book([60], [100.0], [101.0]), boundary), ignore_index=True)
        ),
        MakerReplayEvidenceChunk(
            pd.concat((boundary, _book([80], [100.2], [100.3])), ignore_index=True)
        ),
    )

    report = replay_maker_order_chunks(
        chunks,
        _decisions(["TREND_UP", "TREND_UP", "TREND_UP"]),
        MakerReplayConfig(initial_equity=100.0, fill_rule="touch"),
    )

    assert report.snapshots == 3


def test_streaming_replay_rejects_conflicting_book_boundary() -> None:
    """A repeated boundary timestamp with changed prices is corrupt evidence."""
    chunks = (
        MakerReplayEvidenceChunk(_book([60, 70], [100.0, 99.0], [101.0, 100.0])),
        MakerReplayEvidenceChunk(_book([70, 80], [98.0, 100.2], [99.0, 100.3])),
    )

    with pytest.raises(ValueError, match="conflicting book chunk boundary"):
        replay_maker_order_chunks(
            chunks,
            _decisions(["TREND_UP", "TREND_UP", "TREND_UP"]),
            MakerReplayConfig(initial_equity=100.0, fill_rule="touch"),
        )


def test_streaming_replay_deduplicates_exact_trade_boundary() -> None:
    """An inclusive hourly boundary contributes one identical public print."""
    first = _trades([61], ["sell"], [99.0], [10.0])
    second = _trades([62], ["sell"], [99.0], [18.0])
    second["trade_id"] = 2
    chunks = (
        MakerReplayEvidenceChunk(_book([60], [100.0], [101.0]), first),
        MakerReplayEvidenceChunk(None, pd.concat((first, second), ignore_index=True)),
    )

    report = replay_maker_order_chunks(
        chunks,
        _decisions(["TREND_UP", "TREND_UP"]),
        MakerReplayConfig(initial_equity=100.0, fill_rule="trade-through"),
    )

    assert report.market_trade_prints == 2
    assert report.entry_fills == 1


def test_streaming_replay_rejects_conflicting_trade_boundary() -> None:
    """A repeated boundary trade ID with changed fields is corrupt evidence."""
    first = _trades([61], ["sell"], [99.0], [10.0])
    changed = first.copy()
    changed.loc[0, "price"] = 98.0
    chunks = (
        MakerReplayEvidenceChunk(_book([60], [100.0], [101.0]), first),
        MakerReplayEvidenceChunk(None, changed),
    )

    with pytest.raises(ValueError, match="conflicting trade chunk boundary"):
        replay_maker_order_chunks(
            chunks,
            _decisions(["TREND_UP", "TREND_UP"]),
            MakerReplayConfig(initial_equity=100.0, fill_rule="trade-through"),
        )


def test_through_rule_does_not_claim_touch_only_fill() -> None:
    decisions = _decisions(["TREND_UP", "TREND_UP"])
    book = _book([60, 70], [100.0, 99.0], [101.0, 100.0])

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="through",
            tick_size=1.0,
        ),
    )

    assert report.entry_fills == 0
    assert report.pending_orders == 1


def test_trade_through_fills_long_entry_and_exit_only_from_later_prints() -> None:
    """Opposite aggressors beyond resting limits provide conservative evidence."""
    decisions = _decisions(["TREND_UP", "TREND_UP"])
    book = _book([60], [100.0], [101.0])
    trades = _trades(
        [61, 62],
        ["sell", "buy"],
        [99.0, 100.3],
        [30.0, 30.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            fill_rule="trade-through",
        ),
        trades=trades,
    )

    assert report.market_trade_prints == 2
    assert report.entry_fills == 1
    assert report.completed_trades == 1
    assert report.trades[0].entry_time_utc == "2026-01-01T00:01:01+00:00"
    assert report.trades[0].exit_time_utc == "2026-01-01T00:01:02+00:00"


def test_trade_through_fills_short_from_buy_print_beyond_resting_ask() -> None:
    """A buy aggressor above a resting sell proves a short maker entry crossed."""
    decisions = _decisions(["TREND_DOWN", "TREND_DOWN"])
    book = _book([60], [100.0], [101.0])
    trades = _trades([61], ["buy"], [102.0], [30.0])

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(initial_equity=100.0, fill_rule="trade-through"),
        trades=trades,
    )

    assert report.entry_fills == 1
    assert report.open_positions == 1
    assert report.trades == ()


def test_trade_through_does_not_claim_same_price_or_pre_submission_print() -> None:
    """Queue completion stays unresolved at the limit and before submission."""
    decisions = _decisions(["TREND_UP", "TREND_UP"])
    book = _book([60], [100.0], [101.0])
    trades = _trades(
        [59, 61],
        ["sell", "sell"],
        [99.0, 100.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(fill_rule="trade-through"),
        trades=trades,
    )

    assert report.entry_fills == 0
    assert report.pending_orders == 1


def test_trade_through_requires_cumulative_volume_to_cover_order() -> None:
    """A price-through print smaller than our order cannot imply a full fill."""
    trades = _trades([61, 62], ["sell", "sell"], [99.0, 99.0], [10.0, 18.0])
    config = MakerReplayConfig(initial_equity=100.0, fill_rule="trade-through")
    book = _book([60], [100.0], [101.0])
    decisions = _decisions(["TREND_UP", "TREND_UP"])

    partial = replay_maker_orders(
        book,
        decisions,
        config,
        trades=trades.iloc[:1],
    )

    report = replay_maker_orders(
        book,
        decisions,
        config,
        trades=trades,
    )

    assert partial.entry_fills == 0
    assert report.entry_fills == 1
    assert report.open_positions == 1
    assert report.trades == ()


def test_trade_through_deduplicates_exact_chunk_boundary_prints() -> None:
    """Inclusive adjacent windows may repeat one identical public trade."""
    trade = _trades([61], ["sell"], [99.0], [30.0])
    duplicated = pd.concat((trade, trade), ignore_index=True)

    report = replay_maker_orders(
        _book([60], [100.0], [101.0]),
        _decisions(["TREND_UP", "TREND_UP"]),
        MakerReplayConfig(initial_equity=100.0, fill_rule="trade-through"),
        trades=duplicated,
    )

    assert report.market_trade_prints == 1
    assert report.entry_fills == 1


def test_trade_through_rejects_conflicting_duplicate_trade_ids() -> None:
    """A repeated identifier with different market fields is corrupt evidence."""
    trades = _trades([61, 62], ["sell", "sell"], [99.0, 98.0])
    trades.loc[1, "trade_id"] = trades.loc[0, "trade_id"]

    with pytest.raises(ValueError, match="conflicting duplicate trade_id"):
        replay_maker_orders(
            _book([60], [100.0], [101.0]),
            _decisions(["TREND_UP", "TREND_UP"]),
            MakerReplayConfig(fill_rule="trade-through"),
            trades=trades,
        )


@pytest.mark.parametrize(
    ("book", "message"),
    [
        (pd.DataFrame({"ts_ms": [1]}), "missing columns"),
        (pd.DataFrame(columns=["ts_ms", "best_bid", "best_ask"]), "at least one"),
        (
            pd.DataFrame({"ts_ms": [1], "best_bid": [0.0], "best_ask": [1.0]}),
            "positive",
        ),
        (
            pd.DataFrame({"ts_ms": [1], "best_bid": [2.0], "best_ask": [1.0]}),
            "best_bid",
        ),
    ],
)
def test_book_validation_rejects_invalid_replay_evidence(
    book: pd.DataFrame, message: str
) -> None:
    """Malformed or crossed top-of-book evidence must fail closed."""
    with pytest.raises(ValueError, match=message):
        validate_book(book)


def test_book_validation_deduplicates_only_exact_boundary_snapshots() -> None:
    """Repeated chunk boundaries must agree before one snapshot is retained."""
    exact = pd.DataFrame(
        {
            "ts_ms": [1, 1],
            "best_bid": [100.0, 100.0],
            "best_ask": [101.0, 101.0],
        }
    )
    conflicting = exact.copy()
    conflicting.loc[1, "best_bid"] = 99.0

    assert len(validate_book(exact)) == 1
    with pytest.raises(ValueError, match="conflicting duplicate book timestamp"):
        validate_book(conflicting)


@pytest.mark.parametrize(
    ("trades", "message"),
    [
        (None, "requires public"),
        (pd.DataFrame({"ts_ms": [1]}), "missing columns"),
        (
            pd.DataFrame(
                columns=["ts_ms", "trade_id", "aggressor_side", "price", "size"]
            ),
            "requires public",
        ),
        (_trades([1], ["unknown"], [100.0]), "buy\\|sell"),
        (_trades([1], ["buy"], [0.0]), "positive"),
    ],
)
def test_trade_validation_rejects_invalid_replay_evidence(
    trades: pd.DataFrame | None, message: str
) -> None:
    """Trade-through accepts only complete positive public-print evidence."""
    with pytest.raises(ValueError, match=message):
        validate_trades(trades)


def test_replay_does_not_use_open_candle_or_trade_range() -> None:
    decisions = _decisions(["TREND_UP", "RANGE", "TREND_DOWN"])
    book = _book(
        [30, 120, 180],
        [100.0, 100.0, 100.0],
        [101.0, 101.0, 101.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(fill_rule="touch"),
    )

    assert report.submitted_entries == 1
    assert report.submission_times_utc == ("2026-01-01T00:03:00+00:00",)


def test_pending_entry_cancels_when_backend_moves_to_range() -> None:
    decisions = _decisions(["TREND_UP", "RANGE", "RANGE"])
    book = _book(
        [60, 120],
        [100.0, 100.0],
        [101.0, 101.0],
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(fill_rule="through", tick_size=1.0),
    )

    assert report.submitted_entries == 1
    assert report.canceled_entries == 1
    assert report.pending_orders == 0


def test_expired_entry_retries_only_after_directional_regime_resets() -> None:
    decisions = _decisions(["TREND_DOWN"] * 8 + ["RANGE", "TREND_DOWN", "TREND_DOWN"])
    seconds = list(range(60, 661, 60))
    bids = [100.0 - float(index) for index in range(len(seconds))]
    asks = [bid + 1.0 for bid in bids]

    report = replay_maker_orders(
        _book(seconds, bids, asks),
        decisions,
        MakerReplayConfig(fill_rule="through", tick_size=1.0),
    )

    assert report.expired_entries == 1
    assert report.submitted_entries == 2
    assert report.submission_times_utc == (
        "2026-01-01T00:01:00+00:00",
        "2026-01-01T00:10:00+00:00",
    )
    assert [row.status for row in report.lifecycles] == ["expired", "pending"]
    assert report.lifecycles[0].outcome_time_utc == "2026-01-01T00:07:00+00:00"


def test_cli_reports_touch_and_through_without_placing_orders(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    decisions = _decisions(["TREND_UP", "TREND_UP", "TREND_UP"])
    bars = pd.DataFrame(
        {
            "timestamp": decisions.index,
            "open": [100.0] * 3,
            "high": [101.0] * 3,
            "low": [99.0] * 3,
            "close": [100.0] * 3,
            "volume": [1.0] * 3,
        }
    )
    book = _book([60, 70, 80], [100.0, 99.0, 100.2], [101.0, 100.0, 100.3])
    monkeypatch.setattr(
        "hypervector.commands.replay._load_bars",
        lambda _args: (bars, {"source": "fixture"}),
    )
    monkeypatch.setattr(
        "hypervector.regime.composite.classify_multitimeframe",
        lambda _bars, config: decisions,
    )
    monkeypatch.setattr(
        "hypervector.data.book_align.load_l2_jsonl",
        lambda _path: book,
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "hypervelocity-maker-replay",
            "--book-path",
            str(tmp_path / "book.jsonl"),
            "--initial-equity",
            "100",
            "--maker-fee-rate",
            "0",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["report_only"] is True
    assert payload["candidate"]["candidate_id"] == "bbwp_blueprint_full"
    assert payload["candidate"]["parameters"]["range_filter"] == "bbwp"
    assert len(payload["candidate"]["fingerprint"]) == 64
    assert set(payload["reports"]) == {"touch", "through"}
    assert payload["reports"]["touch"]["completed_trades"] == 1


def test_cli_streams_verified_archive_window_without_path_arguments(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verified archive window avoids thousands of repeated CLI arguments."""
    decisions = _decisions(["TREND_UP", "TREND_UP", "TREND_UP"])
    bars = pd.DataFrame(
        {
            "timestamp": decisions.index,
            "open": [100.0] * 3,
            "high": [101.0] * 3,
            "low": [99.0] * 3,
            "close": [100.0] * 3,
            "volume": [1.0] * 3,
        }
    )
    book = _book([60, 70, 80], [100.0, 99.0, 100.2], [101.0, 100.0, 100.3])
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, 1, tzinfo=UTC)
    bundle = OxaArchiveBundle(
        start,
        end,
        tmp_path / "books.jsonl.gz",
        tmp_path / "trades.jsonl.gz",
        3,
        0,
    )
    monkeypatch.setattr(
        "hypervector.commands.replay._load_bars", lambda _args: (bars, {"source": "fixture"})
    )
    monkeypatch.setattr(
        "hypervector.regime.composite.classify_multitimeframe",
        lambda _bars, config: decisions,
    )
    monkeypatch.setattr(
        "hypervector.data.oxa_archive_audit.verified_archive_bundles",
        lambda _config: (bundle,),
    )
    monkeypatch.setattr("hypervector.data.book_align.load_l2_jsonl", lambda _path: book)

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "hypervelocity-maker-replay",
            "--archive-start",
            start.isoformat(),
            "--archive-end",
            end.isoformat(),
            "--fill-rule",
            "touch",
            "--initial-equity",
            "100",
            "--maker-fee-rate",
            "0",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["archive"]["bundle_count"] == 1
    assert payload["archive"]["checksums_verified"] is True
    assert payload["reports"]["touch"]["completed_trades"] == 1


def test_cli_reports_trade_through_when_public_prints_are_supplied(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The comparison surface must expose all three fill assumptions."""
    decisions = _decisions(["TREND_UP", "TREND_UP"])
    bars = pd.DataFrame(
        {
            "timestamp": decisions.index,
            "open": [100.0] * 2,
            "high": [101.0] * 2,
            "low": [99.0] * 2,
            "close": [100.0] * 2,
            "volume": [1.0] * 2,
        }
    )
    monkeypatch.setattr(
        "hypervector.commands.replay._load_bars", lambda _args: (bars, {"source": "fixture"})
    )
    monkeypatch.setattr(
        "hypervector.regime.composite.classify_multitimeframe",
        lambda _bars, config: decisions,
    )
    monkeypatch.setattr(
        "hypervector.data.book_align.load_l2_jsonl",
        lambda _path: _book([60], [100.0], [101.0]),
    )
    monkeypatch.setattr(
        "hypervector.data.oxa_trades.load_trade_jsonl",
        lambda _path: _trades([61], ["sell"], [99.0]),
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "hypervelocity-maker-replay",
            "--book-path",
            str(tmp_path / "books.jsonl"),
            "--trade-path",
            str(tmp_path / "trades.jsonl"),
            "--fill-rule",
            "all",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert set(payload["reports"]) == {"touch", "through", "trade-through"}
    assert payload["reports"]["trade-through"]["market_trade_prints"] == 1
    assert payload["trade_paths"] == [str(tmp_path / "trades.jsonl")]
