"""Causal open-lifecycle profit-lock challenger tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from hypervector.research.cohort_open_trade_evidence import build_open_trade_evidence


@dataclass(frozen=True)
class _Candle:
    """One completed candle used by the open-policy tests."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float


def test_long_lock_activates_then_triggers_on_a_later_completed_bar() -> None:
    """A stop created after one bar cannot trigger until a later bar."""
    lock = _evidence(
        "long",
        {
            60_000: _bar(60_000, 100.0, 100.30, 99.95, 100.20),
            120_000: _bar(120_000, 100.25, 100.25, 100.18, 100.20),
        },
    )["open_profit_lock_challenger"]

    policy = lock["policies"]["a25_floor15_trail10"]
    assert lock["status"] == "observed"
    assert policy["status"] == "triggered_before_current_boundary"
    assert policy["activation_timestamp_ms"] == 60_000
    assert policy["trigger_timestamp_ms"] == 120_000
    assert policy["trigger_reference_price"] == pytest.approx(100.1997)
    assert policy["stop_price_before_trigger"] == pytest.approx(100.1997)
    economics = policy["counterfactual_economics"]
    assert economics["status"] == "estimated_trigger_exit"
    assert economics["gross_return_bps"] == pytest.approx(19.97)
    assert economics["estimated_net_pnl_excluding_funding_usd"] == pytest.approx(
        0.11962012
    )
    assert economics[
        "estimated_minus_current_exit_net_excluding_funding_usd"
    ] == pytest.approx(-0.00029988)
    assert economics["funding_included"] is False
    assert economics["additional_slippage_included"] is False


def test_short_lock_is_directionally_symmetric() -> None:
    """Short activation, stop placement, and crossing mirror the long path."""
    lock = _evidence(
        "short",
        {
            60_000: _bar(60_000, 100.0, 100.05, 99.70, 99.80),
            120_000: _bar(120_000, 99.75, 99.82, 99.75, 99.80),
        },
    )["open_profit_lock_challenger"]

    policy = lock["policies"]["a25_floor15_trail10"]
    assert policy["status"] == "triggered_before_current_boundary"
    assert policy["trigger_reference_price"] == pytest.approx(99.7997)
    assert policy["best_completed_price_before_trigger"] == pytest.approx(99.70)


def test_armed_lock_reports_the_current_completed_bar_stop() -> None:
    """An active but uncrossed lock exposes its current causal stop."""
    lock = _evidence(
        "long",
        {
            60_000: _bar(60_000, 100.0, 100.30, 99.95, 100.20),
            120_000: _bar(120_000, 100.25, 100.35, 100.25, 100.30),
        },
    )["open_profit_lock_challenger"]

    policy = lock["policies"]["a25_floor15_trail10"]
    assert policy["status"] == "armed_not_triggered"
    assert policy["best_completed_price"] == pytest.approx(100.35)
    assert policy["active_stop_price"] == pytest.approx(100.24965)
    assert policy["trigger_timestamp_ms"] is None
    assert policy["counterfactual_economics"]["status"] == (
        "estimated_active_stop_exit"
    )


def test_missing_expected_bar_withholds_every_policy() -> None:
    """A data gap cannot masquerade as an untriggered policy."""
    lock = _evidence(
        "long",
        {60_000: _bar(60_000, 100.0, 100.30, 99.95, 100.20)},
        as_of_ms=270_000,
    )["open_profit_lock_challenger"]

    assert lock["status"] == "insufficient_candle_coverage"
    assert lock["completed_bars_expected"] == 2
    assert lock["completed_bars_observed"] == 1
    assert {policy["status"] for policy in lock["policies"].values()} == {
        "withheld_incomplete_candle_coverage"
    }


def test_recently_closed_bar_within_arrival_grace_is_not_a_data_gap() -> None:
    """Normal publication latency cannot erase already evaluated lock state."""
    lock = _evidence(
        "long",
        {60_000: _bar(60_000, 100.0, 100.30, 99.95, 100.20)},
        as_of_ms=189_000,
    )["open_profit_lock_challenger"]

    assert lock["status"] == "observed"
    assert lock["completed_bars_expected"] == 1
    assert lock["completed_bars_observed"] == 1
    assert lock["completed_bar_arrival_grace_ms"] == 60_000


def test_hip3_bar_still_in_publication_window_does_not_withhold_prefix() -> None:
    """Observed 32-second HIP-3 latency remains inside the causal grace."""
    lock = _evidence(
        "long",
        {60_000: _bar(60_000, 100.0, 100.30, 99.95, 100.20)},
        as_of_ms=212_000,
    )["open_profit_lock_challenger"]

    assert lock["status"] == "observed"
    assert lock["completed_bars_expected"] == 1
    assert lock["completed_bars_observed"] == 1


def test_future_candle_does_not_change_the_current_prefix() -> None:
    """A candle not fully complete at as-of cannot alter policy state."""
    candles = {
        60_000: _bar(60_000, 100.0, 100.30, 99.95, 100.20),
        120_000: _bar(120_000, 100.25, 100.35, 100.25, 100.30),
    }
    prefix = _evidence("long", candles)["open_profit_lock_challenger"]
    candles[180_000] = _bar(180_000, 99.0, 101.0, 90.0, 95.0)
    extended = _evidence("long", candles)["open_profit_lock_challenger"]

    assert extended == prefix


def test_open_evidence_includes_risk_normalized_late_lock() -> None:
    """Open telemetry must expose the original-stop normalized challenger."""
    evidence = _evidence(
        "long",
        {
            60_000: _bar(60_000, 100.0, 101.7, 99.9, 101.6),
            120_000: _bar(120_000, 102.0, 110.0, 101.8, 109.0),
        },
    )

    challenger = evidence["open_risk_normalized_profit_lock_challenger"]
    policy = challenger["policies"]["r2_floor1_trail1"]
    assert challenger["contract"]["execution_authority"] == "none"
    assert policy["activation_bps"] == pytest.approx(160.0)


def _evidence(
    side: str,
    candles: dict[int, _Candle],
    *,
    as_of_ms: int = 270_000,
) -> dict[str, object]:
    direction = 1.0 if side == "long" else -1.0
    gross_marked_pnl = direction * (100.2 - 100.0)
    return build_open_trade_evidence(
        candles,
        side,
        {"venue_timestamp_ms": 10_000, "price": 100.0, "size": 1.0},
        {
            "mark_price": 100.2,
            "fees_usd": 0.04,
            "funding_usd": 0.0,
            "active_lifecycle_marked_net_pnl_usd": gross_marked_pnl - 0.04,
        },
        {
            "soft_deadline_timestamp_ms": 9_000_000,
            "provider_recipe_exit_policy": "ignore",
        },
        as_of_ms,
        protective_stop={"trigger_price": 99.2 if side == "long" else 100.8},
    )


def _bar(
    timestamp_ms: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> _Candle:
    return _Candle(timestamp_ms, open_price, high, low, close)
