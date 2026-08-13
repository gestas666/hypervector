"""Research-only maker contract variation tests."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.research.maker_replay_models import MakerReplayConfig, OpenPosition
from hypervector.research.maker_replay import replay_maker_orders
from hypervector.research.maker_replay_risk import position_liquidation_price
from hypervector.research.maker_replay_signals import (
    available_entry_allocation_multipliers,
)


def test_replay_config_accepts_btc_allocation_and_leverage_variants() -> None:
    """Research config may vary sizing without changing the faithful contract."""
    config = MakerReplayConfig(margin_fraction=1.0, leverage=20.0)

    assert config.margin_fraction == 1.0
    assert config.leverage == 20.0
    assert config.target_margin_pct == 8.0


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("margin_fraction", 0.0),
        ("margin_fraction", 1.01),
        ("leverage", 0.0),
        ("leverage", 40.01),
        ("target_margin_pct", 0.0),
    ),
)
def test_replay_config_rejects_invalid_btc_contract_variants(
    field: str, value: float
) -> None:
    """The research surface remains inside finite BTC venue constraints."""
    with pytest.raises(ValueError, match=field.replace("_", " ")):
        MakerReplayConfig(**{field: value})


def test_liquidation_maintenance_uses_btc_venue_tier_not_chosen_leverage() -> None:
    """Selecting 20x must not silently substitute a different BTC venue tier."""
    entry_price = 100_000.0
    quantity = 2.0
    margin = 10_000.0
    position = OpenPosition(
        lifecycle_id=1,
        direction="long",
        signal_time=pd.Timestamp("2026-01-01T00:00:00Z"),
        submitted_time=pd.Timestamp("2026-01-01T00:00:01Z"),
        entry_time=pd.Timestamp("2026-01-01T00:00:02Z"),
        entry_price=entry_price,
        quantity=quantity,
        margin=margin,
        notional=quantity * entry_price,
        target_price=100_400.0,
        venue_max_leverage=40.0,
    )
    expected = IsolatedMarginPosition(
        symbol="BTC",
        side="long",
        quantity=quantity,
        entry_price=entry_price,
        isolated_margin=margin,
        maintenance_rate=maintenance_rate_for_max_leverage(40.0),
    ).liquidation_price()

    assert position_liquidation_price(position) == pytest.approx(expected)


def test_replay_applies_configured_allocation_leverage_and_target() -> None:
    """The event replay must use the research contract rather than fixed 70/40."""
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    book = pd.DataFrame(
        {
            "ts_ms": [
                int((origin + pd.Timedelta(seconds=seconds)).timestamp() * 1000)
                for seconds in (60, 70, 80)
            ],
            "best_bid": [100.0, 99.0, 100.4],
            "best_ask": [101.0, 100.0, 100.5],
        }
    )
    decisions = pd.DataFrame(
        {
            "primary_regime": ["TREND_UP"] * 3,
            "breakout_direction": [None] * 3,
        },
        index=pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC"),
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            margin_fraction=1.0,
            leverage=20.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
        ),
    )

    trade = report.trades[0]
    assert trade.margin == pytest.approx(100.0)
    assert trade.notional == pytest.approx(2_000.0)
    assert trade.exit_price == pytest.approx(100.4)
    assert report.final_equity == pytest.approx(108.0)


def test_replay_applies_causal_entry_allocation_multiplier() -> None:
    """A decision-time sizing annotation must scale only its submitted entry."""
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    book = pd.DataFrame(
        {
            "ts_ms": [
                int((origin + pd.Timedelta(seconds=seconds)).timestamp() * 1000)
                for seconds in (60, 70, 80)
            ],
            "best_bid": [100.0, 99.0, 100.4],
            "best_ask": [101.0, 100.0, 100.5],
        }
    )
    decisions = pd.DataFrame(
        {
            "primary_regime": ["TREND_UP"] * 3,
            "breakout_direction": [None] * 3,
            "entry_allocation_multiplier": [0.5] * 3,
        },
        index=pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC"),
    )

    report = replay_maker_orders(
        book,
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            margin_fraction=1.0,
            leverage=20.0,
            maker_fee_rate=0.0,
            fill_rule="touch",
        ),
    )

    trade = report.trades[0]
    assert trade.margin == pytest.approx(50.0)
    assert trade.notional == pytest.approx(1_000.0)
    assert report.final_equity == pytest.approx(104.0)


def test_entry_allocation_multiplier_rejects_zero() -> None:
    """A decision annotation must not silently suppress or invert an entry."""
    decisions = pd.DataFrame(
        {"entry_allocation_multiplier": [0.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-01-01T00:00:00Z")]),
    )

    with pytest.raises(ValueError, match=r"within \(0, 1\]"):
        available_entry_allocation_multipliers(decisions)
