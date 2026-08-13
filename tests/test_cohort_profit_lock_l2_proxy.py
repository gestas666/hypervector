"""Tests for causal L2-midpoint profit-lock proxy evidence."""

from __future__ import annotations

from hypervector.research.cohort_profit_lock_l2_proxy import (
    ProxyLifecycle,
    ProxyMinuteBar,
    build_profit_lock_proxy_report,
)


def _bar(
    timestamp_ms: int,
    *,
    low: float,
    high: float,
    gap_ms: int = 1_000,
    open_price: float = 100.5,
) -> ProxyMinuteBar:
    return ProxyMinuteBar(
        timestamp_ms=timestamp_ms,
        open=open_price,
        high=high,
        low=low,
        close=open_price,
        snapshot_count=60,
        first_delay_ms=0,
        maximum_internal_gap_ms=gap_ms,
        end_boundary_age_ms=1_000,
    )


def _trade(lifecycle_id: str, *, entry_ms: int = 1_000) -> ProxyLifecycle:
    return ProxyLifecycle(
        lifecycle_id=lifecycle_id,
        phase="validation",
        side="long",
        entry_timestamp_ms=entry_ms,
        exit_timestamp_ms=240_000,
        entry_price=100.0,
        exit_price=100.2,
        quantity=1.0,
        gross_pnl_usd=0.2,
        fees_usd=0.09,
    )


def test_trigger_before_first_incomplete_minute_remains_resolved() -> None:
    bars = {
        60_000: _bar(60_000, low=100.4, high=101.0),
        120_000: _bar(120_000, low=100.1, high=100.7),
        180_000: _bar(180_000, low=100.4, high=100.7, gap_ms=20_000),
    }

    report = build_profit_lock_proxy_report((_trade("SP500:1"),), bars, (15_000,))

    result = report["thresholds_ms"]["15000"]["by_phase"]["validation"]
    assert result["a25_floor15_trail10"] == {
        "trades": 1,
        "resolved": 1,
        "withheld": 0,
        "triggered": 1,
        "wins": 1,
        "losses": 0,
        "breakeven": 0,
        "estimated_net_ex_funding_usd": 0.409865,
        "actual_net_ex_funding_same_rows_usd": 0.11,
        "delta_usd": 0.299865,
        "profit_factor": None,
        "net_excluding_largest_winner_usd": 0.0,
    }


def test_gap_before_trigger_withholds_instead_of_using_future_bars() -> None:
    bars = {
        60_000: _bar(60_000, low=99.9, high=100.1, open_price=100.0),
        120_000: _bar(120_000, low=100.4, high=101.0, gap_ms=20_000),
        180_000: _bar(180_000, low=100.1, high=100.7),
    }

    report = build_profit_lock_proxy_report((_trade("SP500:2"),), bars, (15_000,))

    row = report["thresholds_ms"]["15000"]["lifecycles"][0]
    assert row["status"] == "withheld_incomplete_l2_prefix"
    assert row["first_incomplete_minute_ms"] == 120_000
    assert row["policies"]["a25_floor15_trail10"]["triggered"] is False


def test_completeness_threshold_sensitivity_is_explicit() -> None:
    bars = {
        60_000: _bar(60_000, low=100.4, high=101.0),
        120_000: _bar(120_000, low=100.1, high=100.7, gap_ms=20_000),
        180_000: _bar(180_000, low=100.4, high=100.7),
    }

    report = build_profit_lock_proxy_report(
        (_trade("SP500:3"),), bars, (15_000, 30_000)
    )

    assert report["thresholds_ms"]["15000"]["lifecycles"][0]["status"] == (
        "withheld_incomplete_l2_prefix"
    )
    assert report["thresholds_ms"]["30000"]["lifecycles"][0]["status"] == (
        "resolved_complete_path"
    )
