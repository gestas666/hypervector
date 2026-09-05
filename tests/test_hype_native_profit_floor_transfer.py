"""Tests for the frozen HYPE-native mature-profit-floor transfer."""

from __future__ import annotations

import pytest

from hypervector.research.hype_native_profit_floor_transfer import (
    FundingCashflow,
    NativeLifecycle,
    ProfitFloorBar,
    build_hype_native_profit_floor_transfer,
)


def _bar(timestamp_ms: int, *, high: float, low: float) -> ProfitFloorBar:
    return ProfitFloorBar(timestamp_ms, 100.5, high, low, 100.5)


def _book(timestamp_ms: int, *bids: tuple[float, float]) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "run_id": "observer-run",
        "payload": {
            "symbol": "HYPE",
            "exchange_ts_ms": timestamp_ms - 5,
            "recv_ts_ms": timestamp_ms,
            "bids": [{"price": price, "size": size} for price, size in bids],
            "asks": [{"price": 101.0, "size": 100.0}],
        },
    }


def _lifecycle(
    lifecycle_id: str,
    *,
    actual_net: float | None,
    funding_complete_ms: int | None,
    funding: tuple[FundingCashflow, ...] = (),
) -> NativeLifecycle:
    return NativeLifecycle(
        lifecycle_id=lifecycle_id,
        entry_time_ms=10_000,
        natural_exit_time_ms=240_000 if actual_net is not None else None,
        as_of_ms=240_000,
        entry_price=100.0,
        quantity=1.0,
        actual_net_after_funding_usd=actual_net,
        actual_exit_reason="maximum_hold" if actual_net is not None else None,
        funding_cashflows=funding,
        funding_complete_through_ms=funding_complete_ms,
    )


def test_floor_uses_completed_bar_then_first_causal_depth_book() -> None:
    lifecycle = _lifecycle(
        "HYPE:first",
        actual_net=-1.0,
        funding_complete_ms=240_000,
        funding=(FundingCashflow(150_000, -0.01),),
    )
    bars = (
        _bar(60_000, high=101.1, low=100.4),
        _bar(120_000, high=100.8, low=100.2),
        _bar(180_000, high=100.7, low=100.4),
    )
    books = (_book(180_005, (100.24, 0.4), (100.23, 0.6)),)

    report = build_hype_native_profit_floor_transfer(
        (lifecycle,), {lifecycle.lifecycle_id: bars}, {lifecycle.lifecycle_id: books}
    )

    outcome = report["lifecycles"][0]
    assert outcome["status"] == "resolved_triggered"
    assert outcome["activation_bar_ms"] == 60_000
    assert outcome["trigger_bar_ms"] == 120_000
    assert outcome["decision_time_ms"] == 180_000
    assert outcome["exit_book_time_ms"] == 180_005
    assert outcome["exit_price"] == pytest.approx(100.234)
    expected = 0.234 - (200.234 * 4.32 / 10_000) - (200.234 * 2.0 / 10_000)
    assert outcome["estimated_net_before_funding_usd"] == pytest.approx(expected)
    assert outcome["estimated_net_after_funding_usd"] == pytest.approx(expected - 0.01)
    assert report["comparison"]["floor_minus_native_net_usd"] == pytest.approx(
        expected + 0.99
    )
    assert not any(
        "remains provisional" in limitation for limitation in report["limitations"]
    )


def test_open_trigger_stays_provisional_until_funding_is_complete() -> None:
    lifecycle = _lifecycle("HYPE:open", actual_net=None, funding_complete_ms=None)
    bars = (
        _bar(60_000, high=101.1, low=100.4),
        _bar(120_000, high=100.8, low=100.2),
        _bar(180_000, high=100.7, low=100.4),
    )

    report = build_hype_native_profit_floor_transfer(
        (lifecycle,),
        {lifecycle.lifecycle_id: bars},
        {lifecycle.lifecycle_id: (_book(180_005, (100.25, 2.0)),)},
    )

    outcome = report["lifecycles"][0]
    assert outcome["status"] == "provisional_trigger_funding_pending"
    assert outcome["estimated_net_before_funding_usd"] is not None
    assert outcome["estimated_net_after_funding_usd"] is None
    assert report["comparison"]["status"] == "provisional_open_lifecycle"
    assert report["contract"]["automatic_live_change"] is False


def test_untriggered_closed_lifecycle_preserves_natural_economics() -> None:
    lifecycle = _lifecycle("HYPE:quiet", actual_net=2.0, funding_complete_ms=240_000)
    bars = (
        _bar(60_000, high=100.9, low=100.4),
        _bar(120_000, high=100.8, low=100.2),
        _bar(180_000, high=100.7, low=100.4),
    )

    report = build_hype_native_profit_floor_transfer(
        (lifecycle,), {lifecycle.lifecycle_id: bars}, {lifecycle.lifecycle_id: ()}
    )

    outcome = report["lifecycles"][0]
    assert outcome["status"] == "resolved_not_triggered"
    assert outcome["estimated_net_after_funding_usd"] == 2.0
    assert report["comparison"]["floor_minus_native_net_usd"] == 0.0


def test_missing_causal_exit_book_withholds_instead_of_using_later_price() -> None:
    lifecycle = _lifecycle("HYPE:late", actual_net=-1.0, funding_complete_ms=240_000)
    bars = (
        _bar(60_000, high=101.1, low=100.4),
        _bar(120_000, high=100.8, low=100.2),
        _bar(180_000, high=100.7, low=100.4),
    )

    report = build_hype_native_profit_floor_transfer(
        (lifecycle,),
        {lifecycle.lifecycle_id: bars},
        {lifecycle.lifecycle_id: (_book(241_000, (100.25, 2.0)),)},
    )

    outcome = report["lifecycles"][0]
    assert outcome["status"] == "withheld_exit_book_delay"
    assert outcome["estimated_net_after_funding_usd"] is None
    assert report["comparison"]["status"] == "technically_unresolved"
