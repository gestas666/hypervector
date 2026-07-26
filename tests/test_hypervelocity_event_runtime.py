"""Restart and construction tests for the authoritative event shadow runtime."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent
from hypervector.paper.event_resume import PendingTargetResume
from hypervector.paper.event_runtime import build_event_shadow_controller
from hypervector.paper.resume import PendingMakerResume, ShadowPortfolioResume
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile


PROFILE = Path("configs/hypervelocity_faithful.toml")
OBSERVED_AT = "2026-07-26T12:00:00+00:00"


def _resume() -> ShadowPortfolioResume:
    return ShadowPortfolioResume(
        run_id="run-event",
        init_cash=10_000.0,
        position_qty=0.02,
        position_avg_px=64_500.0,
        realized_pnl=-0.1935,
        unrealized_pnl=0.0,
        equity=9_999.8065,
        state_asof=OBSERVED_AT,
        last_exit_at=None,
        pending_entry=PendingMakerResume(
            direction="long",
            qty=0.04,
            limit_price=64_500.0,
            submitted_at=OBSERVED_AT,
            conviction=0.5,
            conviction_source="fixed",
            metalabel_p=None,
            metalabel_bundle_id=None,
            client_order_id="hv-btc-entry-00000001",
            cumulative_quantity=0.02,
            remaining_quantity=0.02,
        ),
        expired_entry_direction=None,
        completed_trade_direction=None,
        portfolio_fingerprint=None,
        portfolio_profile_changed_from=None,
        execution_model="nautilus_event_v1",
        active_targets=(
            PendingTargetResume(
                client_order_id="hv-btc-target-00000002",
                side="sell",
                quantity=0.02,
                limit_price=64_629.0,
                submitted_at=OBSERVED_AT,
                cumulative_quantity=0.0,
                remaining_quantity=0.02,
            ),
        ),
        next_order_sequence=3,
        open_position_fees_usd=0.1935,
        open_position_funding_net_usd=0.0,
    )


def _book() -> L2SnapshotEvent:
    exchange_ms = int(datetime.fromisoformat(OBSERVED_AT).timestamp() * 1_000) + 100
    return L2SnapshotEvent(
        symbol="BTC",
        exchange_ts_ms=exchange_ms,
        received_ts_ns=(exchange_ms + 1) * 1_000_000,
        bids=(BookLevel(64_500.0, 1.0, 1),),
        asks=(BookLevel(64_501.0, 1.0, 1),),
    )


def test_event_runtime_restores_partial_entry_target_and_account() -> None:
    profile = load_hypervelocity_profile(PROFILE)
    controller = build_event_shadow_controller(
        profile=profile,
        initial_cash_usd=10_000.0,
        observed_at=OBSERVED_AT,
        resume=_resume(),
    )

    assert controller.state.position_quantity == pytest.approx(0.02)
    assert controller.state.next_order_sequence == 3
    assert controller.state.pending_entry is not None
    assert controller.state.pending_entry.cumulative_quantity == pytest.approx(0.02)
    assert len(controller.state.active_targets) == 1
    assert controller.port.account_snapshot().position_quantity == pytest.approx(0.02)
    assert controller.port.order_telemetry(
        "hv-btc-entry-00000001"
    ).remaining_quantity == pytest.approx(0.02)

    cycle = controller.ingest(_book())

    assert [event.event_type for event in cycle.venue_events] == [
        "accepted",
        "accepted",
    ]
    assert cycle.execution_records == ()


def test_legacy_open_position_migrates_to_event_target_without_bar_fill() -> None:
    legacy = replace(
        _resume(),
        pending_entry=None,
        active_targets=(),
        execution_model="legacy_bar_through_v1",
        next_order_sequence=1,
    )
    controller = build_event_shadow_controller(
        profile=load_hypervelocity_profile(PROFILE),
        initial_cash_usd=10_000.0,
        observed_at=OBSERVED_AT,
        resume=legacy,
    )

    assert len(controller.state.active_targets) == 1
    target = controller.state.active_targets[0].command
    assert target.client_order_id == "hv-btc-target-00000001"
    assert target.quantity == pytest.approx(0.02)
    assert target.limit_price == pytest.approx(64_629.0)
    assert controller.port.execution_records() == ()
