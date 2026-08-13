"""Report-only open-profit protection arithmetic tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_open_profit_protection import (
    build_open_profit_protection,
)


def test_long_stop_below_entry_exposes_open_profit_giveback() -> None:
    """A profitable long with a losing stop reports the complete exposure."""
    result = build_open_profit_protection(
        "long",
        {"price": 100.0, "size": 1.0},
        {"oid": 7, "trigger_price": 99.0},
        {
            "mark_price": 110.0,
            "fees_usd": 0.04,
            "funding_usd": -0.01,
            "active_lifecycle_marked_net_pnl_usd": 9.95,
        },
    )

    assert result["status"] == "open_profit_unprotected"
    assert result["estimated_exit_now_net_usd"] == pytest.approx(9.906)
    assert result["estimated_stop_net_usd"] == pytest.approx(-1.0896)
    assert result["marked_to_stop_giveback_usd"] == pytest.approx(10.9956)
    assert result["protected_profit_fraction"] == pytest.approx(0.0)
    assert result["stop_distance_from_mark_bps"] == pytest.approx(1_000.0)


def test_short_stop_below_entry_locks_part_of_open_profit() -> None:
    """Short-side arithmetic retains direction and measured fee provenance."""
    result = build_open_profit_protection(
        "short",
        {"price": 100.0, "size": 1.0},
        {"oid": 8, "trigger_price": 95.0},
        {
            "mark_price": 90.0,
            "fees_usd": 0.04,
            "funding_usd": 0.01,
            "active_lifecycle_marked_net_pnl_usd": 9.97,
        },
    )

    assert result["status"] == "partial_profit_locked"
    assert result["estimated_exit_now_net_usd"] == pytest.approx(9.934)
    assert result["estimated_stop_net_usd"] == pytest.approx(4.932)
    assert result["marked_to_stop_giveback_usd"] == pytest.approx(5.002)
    assert result["protected_profit_fraction"] == pytest.approx(4.932 / 9.934)
    assert result["stop_distance_from_mark_bps"] == pytest.approx(555.5555556)


def test_missing_stop_is_explicitly_unavailable() -> None:
    """Missing protection cannot be success-shaped into a zero-risk result."""
    result = build_open_profit_protection(
        "long",
        {"price": 100.0, "size": 1.0},
        None,
        {
            "mark_price": 101.0,
            "fees_usd": 0.04,
            "funding_usd": 0.0,
            "active_lifecycle_marked_net_pnl_usd": 0.96,
        },
    )

    assert result == {
        "status": "unavailable",
        "reason": "protective_stop_unavailable",
    }


def test_marked_net_must_reconcile_before_risk_is_reported() -> None:
    """Cross-timestamp or corrupted economics fail instead of shaping risk."""
    with pytest.raises(
        ValueError,
        match="marked net PnL does not reconcile to entry economics",
    ):
        build_open_profit_protection(
            "long",
            {"price": 100.0, "size": 1.0},
            {"oid": 9, "trigger_price": 99.0},
            {
                "mark_price": 110.0,
                "fees_usd": 0.04,
                "funding_usd": -0.01,
                "active_lifecycle_marked_net_pnl_usd": -99.0,
            },
        )
