"""Source-derived Tier-0 peak-protection replay tests."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.maker_replay import MakerReplayConfig, replay_maker_orders
from hypervector.research.maker_replay_context import MakerReplayContext
from hypervector.research.maker_replay_models import OpenPosition, ReplayState
from hypervector.research.maker_replay_risk import update_peak_protection


def _decisions(direction: str) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "entry_direction": [direction, direction],
            "structural_direction": [direction, direction],
        },
        index=index,
    )


def _book(seconds: list[int], bids: list[float], asks: list[float]) -> pd.DataFrame:
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    timestamps = [origin + pd.Timedelta(seconds=value) for value in seconds]
    return pd.DataFrame(
        {
            "ts_ms": [int(value.timestamp() * 1000) for value in timestamps],
            "best_bid": bids,
            "best_ask": asks,
        }
    )


def _context(second: int, mark: float) -> MakerReplayContext:
    timestamp = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(seconds=second)
    prices = pd.DataFrame(
        {
            "ts_ms": [int(timestamp.timestamp() * 1000)],
            "mark_price": [mark],
            "oracle_price": [mark],
        }
    )
    funding = pd.DataFrame(columns=["event_ts_ms", "funding_rate"])
    return MakerReplayContext(prices, funding)


def _open_peak_state(direction: str = "long") -> ReplayState:
    position = OpenPosition(
        lifecycle_id=0,
        direction=direction,
        signal_time=pd.Timestamp("2026-01-01T00:00:00Z"),
        submitted_time=pd.Timestamp("2026-01-01T00:00:01Z"),
        entry_time=pd.Timestamp("2026-01-01T00:00:02Z"),
        entry_price=100.0,
        quantity=28.0,
        margin=70.0,
        notional=2_800.0,
        target_price=100.2 if direction == "long" else 99.8,
        initial_quantity=28.0,
    )
    return ReplayState(equity=100.0, position=position, peak_equity=100.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"peak_protection_activation_margin_pct": 6.0},
        {"peak_protection_lock_ratio": 0.55},
        {
            "peak_protection_activation_margin_pct": 0.0,
            "peak_protection_lock_ratio": 0.55,
        },
        {
            "peak_protection_activation_margin_pct": 6.0,
            "peak_protection_lock_ratio": 0.0,
        },
        {
            "peak_protection_activation_margin_pct": 6.0,
            "peak_protection_lock_ratio": 1.01,
        },
    ],
)
def test_peak_protection_config_rejects_incomplete_or_invalid_pairs(
    kwargs: dict[str, float],
) -> None:
    """Activation and lock ratio form one explicit replay assumption."""
    with pytest.raises(ValueError, match="peak protection"):
        MakerReplayConfig(**kwargs)


def test_long_peak_arms_source_tier_and_exits_at_adverse_bbo() -> None:
    """A +6% authentic mark arms a 55%-of-peak long stop without lookahead."""
    report = replay_maker_orders(
        _book(
            [60, 70, 79, 90],
            [100.0, 99.9, 100.14, 100.07],
            [101.0, 100.0, 100.16, 100.08],
        ),
        _decisions("long"),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
            peak_protection_activation_margin_pct=6.0,
            peak_protection_lock_ratio=0.55,
        ),
        context=_context(80, 100.15),
    )

    assert report.peak_protection_arms == 1
    assert report.peak_protection_exits == 1
    assert report.stops == 1
    assert report.liquidations == 0
    assert report.trades[0].status == "stopped"
    assert report.trades[0].exit_price == 100.07
    assert report.lifecycles[0].stop_price == pytest.approx(100.0825)


def test_short_peak_uses_mirrored_locked_stop_price() -> None:
    """The identical Tier-0 rule tightens below entry for a profitable short."""
    report = replay_maker_orders(
        _book(
            [60, 70, 79, 90],
            [99.0, 100.0, 99.84, 99.92],
            [100.0, 100.1, 99.86, 99.93],
        ),
        _decisions("short"),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
            peak_protection_activation_margin_pct=6.0,
            peak_protection_lock_ratio=0.55,
        ),
        context=_context(80, 99.85),
    )

    assert report.peak_protection_arms == 1
    assert report.peak_protection_exits == 1
    assert report.trades[0].exit_price == 99.93
    assert report.lifecycles[0].stop_price == pytest.approx(99.9175)


def test_peak_below_activation_does_not_create_a_stop() -> None:
    """Favorable movement below +6% cannot mutate the position exit policy."""
    report = replay_maker_orders(
        _book(
            [60, 70, 79, 90],
            [100.0, 99.9, 100.14, 100.07],
            [101.0, 100.0, 100.16, 100.08],
        ),
        _decisions("long"),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
            peak_protection_activation_margin_pct=6.0,
            peak_protection_lock_ratio=0.55,
        ),
        context=_context(80, 100.14),
    )

    assert report.peak_protection_arms == 0
    assert report.peak_protection_exits == 0
    assert report.stops == 0
    assert report.open_positions == 1


def test_cooldown_retains_new_peak_for_next_allowed_update() -> None:
    """A peak observed during cooldown must tighten from stored peak afterward."""
    state = _open_peak_state()
    config = MakerReplayConfig(
        peak_protection_activation_margin_pct=6.0,
        peak_protection_lock_ratio=0.55,
    )
    origin = pd.Timestamp("2026-01-01T00:00:10Z")

    assert update_peak_protection(state, origin, 100.15, config) is True
    assert (
        update_peak_protection(state, origin + pd.Timedelta(seconds=30), 100.25, config)
        is False
    )
    assert (
        update_peak_protection(state, origin + pd.Timedelta(seconds=60), 100.24, config)
        is True
    )
    assert state.position is not None
    assert state.position.stop_price == pytest.approx(100.1375)
    assert state.peak_protection_updates == 2


def test_peak_stop_never_widens_or_moves_below_minimum_delta() -> None:
    """Stored peak protection remains monotonic and ignores micro changes."""
    state = _open_peak_state()
    config = MakerReplayConfig(
        peak_protection_activation_margin_pct=6.0,
        peak_protection_lock_ratio=0.55,
        peak_protection_update_cooldown_seconds=0.0,
    )
    origin = pd.Timestamp("2026-01-01T00:00:10Z")

    assert update_peak_protection(state, origin, 100.15, config) is True
    assert (
        update_peak_protection(state, origin + pd.Timedelta(seconds=1), 100.16, config)
        is False
    )
    assert (
        update_peak_protection(state, origin + pd.Timedelta(seconds=2), 100.14, config)
        is False
    )
    assert state.position is not None
    assert state.position.stop_price == pytest.approx(100.0825)
    assert state.peak_protection_updates == 1
