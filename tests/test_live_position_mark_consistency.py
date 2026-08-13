"""Venue-synchronous mark projection for open live positions."""

from __future__ import annotations

import pytest

from hypervector.live.hyperliquid_protocol import (
    SolAccountSnapshot,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
)
from hypervector.live.multi_asset_live_runner_support import asset_snapshot
from hypervector.live.sol_range_onset_state import SolLiveSnapshot, SolLiveState
from hypervector.research.cohort_live_audit_open import open_position_summary


def _position() -> SolPositionSnapshot:
    """Return an account position whose synchronous mark is exactly 101."""
    return SolPositionSnapshot(
        size_signed=2.0,
        entry_price=100.0,
        liquidation_price=80.0,
        margin_used_usd=40.4,
        position_value_usd=202.0,
        unrealized_pnl_usd=2.0,
        leverage_type="isolated",
        leverage=5,
    )


def _venue() -> SolReconciliationSnapshot:
    """Wrap the deterministic position in a reconciliation snapshot."""
    account = SolAccountSnapshot(500.0, 450.0, 40.4, 202.0, _position())
    return SolReconciliationSnapshot(account, (), ())


def test_asset_snapshot_uses_venue_synchronous_mark_for_open_position() -> None:
    """A later market poll cannot be paired with earlier account PnL."""
    snapshot = asset_snapshot(
        "BTC",
        SolLiveSnapshot(
            state=SolLiveState.OPEN,
            entry_oid=1,
            stop_oid=2,
            position_size_signed=2.0,
            opened_at_ms=1,
        ),
        _venue(),
        mark_price=95.0,
    ).as_payload()

    assert snapshot["mark_price"] == pytest.approx(101.0)
    assert snapshot["market_reference_price"] == pytest.approx(95.0)
    assert snapshot["mark_price_source"] == "venue_position_value_div_size"
    assert snapshot["unrealized_pnl_usd"] == pytest.approx(2.0)
    assert snapshot["liquidation_distance_pct"] == pytest.approx(20.7920792)


def test_audit_repairs_legacy_mixed_timestamp_position_mark() -> None:
    """Checkpoint projection corrects persisted snapshots from older runners."""
    asset = {
        "symbol": "BTC",
        "position_size_signed": 2.0,
        "position_side": "long",
        "entry_price": 100.0,
        "mark_price": 95.0,
        "liquidation_price": 80.0,
        "liquidation_distance_pct": 15.0,
        "margin_used_usd": 40.4,
        "position_value_usd": 202.0,
        "unrealized_pnl_usd": 2.0,
        "fees_net_usd": 0.1,
        "funding_net_usd": 0.0,
        "realized_pnl_usd": 0.0,
        "leverage": 5,
    }
    records = [{"event_type": "cohort_snapshot", "payload": {"assets": [asset]}}]
    journals = {
        "BTC": {
            "open_lifecycles": [
                {
                    "status": "open",
                    "fees_usd": 0.05,
                    "funding_usd": -0.01,
                }
            ]
        }
    }

    position = open_position_summary(records, journals)[0]

    assert position["mark_price"] == pytest.approx(101.0)
    assert position["market_reference_price"] == pytest.approx(95.0)
    assert position["mark_price_source"] == "venue_position_value_div_size"
    assert position["market_reference_skew_bps"] == pytest.approx(-594.059406)
    assert position["liquidation_distance_pct"] == pytest.approx(20.7920792)
    assert position["active_lifecycle_marked_net_pnl_usd"] == pytest.approx(1.94)
