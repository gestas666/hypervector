"""Persistent Hypervelocity shadow portfolio restart tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.paper.resume import (
    ShadowResumeError,
    load_shadow_portfolio_resume,
    portfolio_fingerprint,
)
from hypervector.paper.event_resume import event_resume_details


def test_flat_filled_run_does_not_require_position_average(tmp_path: Path) -> None:
    """A closed position may persist a null average price and remains resumable."""
    path = tmp_path / "decisions.jsonl"
    common: dict[str, object] = {
        "run_id": "closed-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
    }
    rows = [
        {
            **common,
            "feed_ts": "2026-07-25T18:00:00Z",
            "action": "enter_long",
            "fill_qty": 1.0,
            "position_qty": 1.0,
            "position_avg_px": 100.0,
            "realized_pnl": -0.1,
            "unrealized_pnl": 0.0,
            "equity": 9_999.9,
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:05:00Z",
            "action": "close",
            "position_qty": 0.0,
            "position_avg_px": None,
            "realized_pnl": 19.8,
            "unrealized_pnl": 0.0,
            "equity": 10_019.8,
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:06:00Z",
            "action": "regime_observation",
            "position_qty": 0.0,
            "position_avg_px": None,
            "realized_pnl": None,
            "equity": None,
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert resumed is not None
    assert resumed.position_qty == 0.0
    assert resumed.position_avg_px == 0.0
    assert resumed.realized_pnl == 19.8


def test_closed_fill_residue_resumes_as_flat(tmp_path: Path) -> None:
    """Sub-epsilon target-fill residue must not reopen as a tiny short."""
    path = tmp_path / "decisions.jsonl"
    common: dict[str, object] = {
        "run_id": "residual-close",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
    }
    rows = [
        {
            **common,
            "feed_ts": "2026-07-29T00:11:38Z",
            "action": "enter_long",
            "fill_qty": 4.37301,
            "fee_usd": 41.9999185935,
            "position_qty": 4.37301,
            "position_avg_px": 64_029.0,
            "realized_pnl": -41.9999185935,
            "unrealized_pnl": 0.0,
            "equity": 9_958.0000814065,
        },
        {
            **common,
            "feed_ts": "2026-07-29T00:45:57Z",
            "action": "close",
            "fee_usd": 2.227611609,
            "position_qty": -4.440892098500626e-16,
            "position_avg_px": 64_158.0,
            "realized_pnl": 480.0338350694,
            "unrealized_pnl": 1.0e-13,
            "equity": 10_480.0338350694,
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert resumed is not None
    assert resumed.position_qty == 0.0
    assert resumed.position_avg_px == 0.0
    assert resumed.unrealized_pnl == 0.0
    assert resumed.active_targets == ()
    assert resumed.open_position_fees_usd == 0.0
    assert resumed.open_position_funding_net_usd == 0.0
    assert resumed.liquidation_cooldown_until_ms is None


def test_resume_rejects_inconsistent_equity_identity(tmp_path: Path) -> None:
    """Finite but internally inconsistent portfolio state is not authoritative."""
    path = tmp_path / "decisions.jsonl"
    row = {
        "run_id": "broken-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "feed_ts": "2026-07-25T18:00:00Z",
        "action": "enter_long",
        "fill_qty": 1.0,
        "init_cash": 10_000.0,
        "position_qty": 1.0,
        "position_avg_px": 100.0,
        "realized_pnl": -1.0,
        "unrealized_pnl": 5.0,
        "equity": 50_000.0,
    }
    path.write_text(f"{json.dumps(row)}\n", encoding="utf-8")

    with pytest.raises(ShadowResumeError, match="equity identity"):
        load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")


def test_open_position_accepts_explicit_entry_rearm_policy_migration(
    tmp_path: Path,
) -> None:
    """An entry-only policy addition cannot strand an existing position."""
    path = tmp_path / "decisions.jsonl"
    old_spec = {
        "strategy_name": "hypervelocity_1m_scalper",
        "execution": {"entry_ttl_seconds": 300.0},
    }
    new_spec = {
        **old_spec,
        "execution": {
            "entry_ttl_seconds": 300.0,
            "expired_entry_rearm_policy": "regime_reset",
            "same_direction_reentry_policy": "regime_reset",
        },
    }
    common = {
        "run_id": "migration-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
    }
    rows = [
        {
            **common,
            "feed_ts": "session_start",
            "action": "session_start",
            "portfolio_spec": old_spec,
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:05:00Z",
            "action": "enter_short",
            "fill_qty": 2.0,
            "position_qty": -2.0,
            "position_avg_px": 100.0,
            "realized_pnl": -0.1,
            "unrealized_pnl": -4.0,
            "equity": 9_995.9,
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(
        path,
        symbol="BTC",
        timeframe="1m",
        expected_spec=new_spec,
    )

    assert resumed is not None
    assert resumed.portfolio_fingerprint == portfolio_fingerprint(new_spec)
    assert resumed.portfolio_profile_changed_from == portfolio_fingerprint(old_spec)


def test_open_position_accepts_explicit_event_execution_migration(
    tmp_path: Path,
) -> None:
    """The declared legacy comparator may migrate without fabricating fills."""
    path = tmp_path / "decisions.jsonl"
    old_execution = {
        "fill_rule": "through_one_tick",
        "fill_model": "post_only_limit_through_v1",
        "entry_ttl_seconds": 300.0,
        "liquidation_execution_model": "full_at_mark_shadow_approximation_v1",
        "partial_liquidation_supported": False,
        "partial_liquidation_threshold_usd": 100_000.0,
    }
    new_execution = {
        **old_execution,
        "fill_rule": "public_l2_trade_event_tape",
        "fill_model": "nautilus_event_v1",
        "legacy_comparator": "legacy_bar_through_v1",
        "submit_latency_ms": 50,
        "cancel_latency_ms": 50,
        "update_latency_ms": 50,
        "max_event_age_ms": 3000,
        "liquidation_execution_model": "hyperliquid_market_liquidation_v2",
        "partial_liquidation_supported": True,
        "partial_liquidation_fraction": 0.20,
        "liquidation_cooldown_ms": 30_000,
        "backstop_liquidation_supported": True,
        "backstop_maintenance_fraction": 2.0 / 3.0,
        "backstop_accounting_model": "isolated_margin_transfer_composite_v1",
    }
    old_spec = {"strategy_name": "hypervelocity_1m_scalper", "execution": old_execution}
    new_spec = {**old_spec, "execution": new_execution}
    common = {
        "run_id": "event-migration-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
    }
    rows = [
        {
            **common,
            "feed_ts": "session_start",
            "action": "session_start",
            "portfolio_spec": old_spec,
        },
        {
            **common,
            "feed_ts": "2026-07-26T18:05:00Z",
            "action": "enter_long",
            "fill_qty": 1.0,
            "position_qty": 1.0,
            "position_avg_px": 100.0,
            "realized_pnl": -0.1,
            "unrealized_pnl": 0.0,
            "equity": 9_999.9,
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(
        path,
        symbol="BTC",
        timeframe="1m",
        expected_spec=new_spec,
    )

    assert resumed is not None
    assert resumed.execution_model == "legacy_bar_through_v1"
    assert resumed.portfolio_fingerprint == portfolio_fingerprint(new_spec)


def test_resume_restores_latest_unmatched_pending_entry(tmp_path: Path) -> None:
    """A submitted maker entry is durable even before the portfolio has a fill."""
    path = tmp_path / "decisions.jsonl"
    common = {
        "run_id": "pending-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
        "position_qty": 0.0,
        "position_avg_px": 0.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "equity": 10_000.0,
    }
    rows = [
        {**common, "feed_ts": "session_start", "action": "session_start"},
        {
            **common,
            "feed_ts": "2026-07-25T18:05:00Z",
            "action": "submit_entry",
            "side": "buy",
            "requested_qty": 2.0,
            "fill_px": 100.0,
            "order_status": "pending",
            "conviction": 0.75,
            "conviction_source": "fixed",
            "metalabel_p": 0.62,
            "metalabel_bundle_id": "bundle-long",
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert resumed is not None
    assert resumed.pending_entry is not None
    assert resumed.pending_entry.direction == "long"
    assert resumed.pending_entry.qty == 2.0
    assert resumed.pending_entry.limit_price == 100.0
    assert resumed.pending_entry.submitted_at == "2026-07-25T18:05:00Z"
    assert resumed.pending_entry.metalabel_p == 0.62
    assert resumed.pending_entry.metalabel_bundle_id == "bundle-long"


def test_event_resume_restores_partial_entry_target_and_open_costs(
    tmp_path: Path,
) -> None:
    """Event runtime restart retains both unfilled entry and target coverage."""
    path = tmp_path / "decisions.jsonl"
    common: dict[str, object] = {
        "run_id": "event-run",
        "execution_mode": "shadow",
        "execution_model": "nautilus_event_v1",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
        "position_avg_px": 64_500.0,
        "unrealized_pnl": 0.0,
    }
    rows = [
        {
            **common,
            "feed_ts": "session_start",
            "action": "session_start",
            "position_qty": 0.0,
            "position_avg_px": 0.0,
            "realized_pnl": 0.0,
            "equity": 10_000.0,
        },
        {
            **common,
            "feed_ts": "2026-07-26T20:00:00+00:00",
            "action": "submit_entry",
            "side": "buy",
            "client_order_id": "hv-btc-entry-00000001",
            "requested_qty": 4.0,
            "fill_px": 64_500.0,
            "cumulative_filled_qty": 0.0,
            "remaining_qty": 4.0,
            "position_qty": 0.0,
            "realized_pnl": 0.0,
            "equity": 10_000.0,
        },
        {
            **common,
            "feed_ts": "2026-07-26T20:00:01+00:00",
            "action": "enter_long",
            "side": "buy",
            "client_order_id": "hv-btc-entry-00000001",
            "fill_qty": 1.0,
            "fee_usd": 9.675,
            "cumulative_filled_qty": 1.0,
            "remaining_qty": 3.0,
            "position_qty": 1.0,
            "realized_pnl": -9.675,
            "equity": 9_990.325,
        },
        {
            **common,
            "feed_ts": "2026-07-26T20:00:01+00:00",
            "action": "submit_target",
            "side": "sell",
            "client_order_id": "hv-btc-target-00000002",
            "requested_qty": 1.0,
            "fill_px": 64_629.0,
            "cumulative_filled_qty": 0.0,
            "remaining_qty": 1.0,
            "position_qty": 1.0,
            "realized_pnl": -9.675,
            "equity": 9_990.325,
        },
        {
            **common,
            "feed_ts": "2026-07-26T21:00:00+00:00",
            "action": "funding",
            "funding_payment_usd": 6.45,
            "position_qty": 1.0,
            "realized_pnl": -16.125,
            "equity": 9_983.875,
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert resumed is not None
    assert resumed.execution_model == "nautilus_event_v1"
    assert resumed.pending_entry is not None
    assert resumed.pending_entry.client_order_id == "hv-btc-entry-00000001"
    assert resumed.pending_entry.cumulative_quantity == pytest.approx(1.0)
    assert len(resumed.active_targets) == 1
    assert resumed.active_targets[0].client_order_id == "hv-btc-target-00000002"
    assert resumed.next_order_sequence == 3
    assert resumed.open_position_fees_usd == pytest.approx(9.675)
    assert resumed.open_position_funding_net_usd == pytest.approx(-6.45)


def test_resume_restores_first_fill_time_and_configured_maximum_hold(
    tmp_path: Path,
) -> None:
    """Restart must retain the original hold deadline across partial fills."""
    path = tmp_path / "decisions.jsonl"
    common: dict[str, object] = {
        "run_id": "source-hold-run",
        "execution_mode": "shadow",
        "execution_model": "nautilus_event_v1",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
        "position_avg_px": 64_500.0,
        "unrealized_pnl": 0.0,
    }
    rows = [
        {
            **common,
            "feed_ts": "session_start",
            "action": "session_start",
            "portfolio_spec": {"regime_policy": {"maximum_hold_seconds": 86_400.0}},
            "position_qty": 0.0,
            "position_avg_px": 0.0,
            "realized_pnl": 0.0,
            "equity": 10_000.0,
        },
        {
            **common,
            "feed_ts": "2026-07-26T20:00:01+00:00",
            "action": "enter_short",
            "side": "sell",
            "fill_qty": 1.0,
            "fee_usd": 9.675,
            "position_qty": -1.0,
            "realized_pnl": -9.675,
            "equity": 9_990.325,
        },
        {
            **common,
            "feed_ts": "2026-07-26T20:00:04+00:00",
            "action": "enter_short",
            "side": "sell",
            "fill_qty": 1.0,
            "fee_usd": 9.675,
            "position_qty": -2.0,
            "realized_pnl": -19.35,
            "equity": 9_980.65,
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert resumed is not None
    assert resumed.position_opened_at == "2026-07-26T20:00:01+00:00"
    assert resumed.maximum_hold_seconds == 86_400.0


def test_event_resume_releases_cost_basis_after_partial_target() -> None:
    """Restart restores only fees and funding assigned to the open residue."""
    rows = [
        {"action": "session_start", "position_qty": 0.0},
        {
            "action": "enter_long",
            "position_qty": 4.0,
            "fee_usd": 38.7,
            "funding_payment_usd": 0.0,
        },
        {
            "action": "funding",
            "position_qty": 4.0,
            "fee_usd": 0.0,
            "funding_payment_usd": 25.8,
        },
        {
            "action": "reduce_target",
            "position_qty": 0.05,
            "fee_usd": 38.295,
            "funding_payment_usd": 0.0,
        },
    ]

    details = event_resume_details(rows)

    assert details.open_position_fees_usd == pytest.approx(0.48375)
    assert details.open_position_funding_net_usd == pytest.approx(-0.3225)


def test_event_resume_drops_rejected_target() -> None:
    rows = [
        {
            "action": "submit_target",
            "client_order_id": "hv-btc-target-00000002",
            "side": "sell",
            "feed_ts": "2026-07-26T20:00:01+00:00",
            "requested_qty": 1.0,
            "fill_px": 64_629.0,
            "remaining_qty": 1.0,
            "position_qty": 1.0,
        },
        {
            "action": "rejected_target",
            "client_order_id": "hv-btc-target-00000002",
            "position_qty": 1.0,
        },
    ]

    assert event_resume_details(rows).active_targets == ()


def test_event_resume_preserves_open_partial_liquidation_cooldown() -> None:
    rows = [
        {
            "action": "partial_liquidation",
            "position_qty": 3.2,
            "liquidation_cooldown_until_ms": 1_785_103_230_000,
        },
        {
            "action": "submit_target",
            "client_order_id": "hv-btc-target-00000003",
            "side": "sell",
            "feed_ts": "2026-07-26T20:00:01+00:00",
            "requested_qty": 3.2,
            "fill_px": 64_629.0,
            "remaining_qty": 3.2,
            "position_qty": 3.2,
        },
    ]

    details = event_resume_details(rows)

    assert details.liquidation_cooldown_until_ms == 1_785_103_230_000
    assert len(details.active_targets) == 1


def test_resume_clears_pending_entry_after_cancel(tmp_path: Path) -> None:
    """A later cancel is authoritative over a prior pending submit."""
    path = tmp_path / "decisions.jsonl"
    common = {
        "run_id": "pending-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
        "position_qty": 0.0,
        "position_avg_px": 0.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "equity": 10_000.0,
    }
    rows = [
        {**common, "feed_ts": "session_start", "action": "session_start"},
        {
            **common,
            "feed_ts": "2026-07-25T18:05:00Z",
            "action": "submit_entry",
            "side": "sell",
            "requested_qty": 2.0,
            "fill_px": 100.0,
            "order_status": "pending",
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:06:00Z",
            "action": "cancel_entry",
            "side": "sell",
            "requested_qty": 2.0,
            "fill_px": 100.0,
            "order_status": "canceled",
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert resumed is not None
    assert resumed.pending_entry is None


def test_resume_restores_expired_entry_direction_until_regime_reset(
    tmp_path: Path,
) -> None:
    """Restart cannot bypass a consumed maker attempt in the same trend."""
    path = tmp_path / "decisions.jsonl"
    common = {
        "run_id": "expired-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
        "position_qty": 0.0,
        "position_avg_px": 0.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "equity": 10_000.0,
    }
    rows = [
        {**common, "feed_ts": "session_start", "action": "session_start"},
        {
            **common,
            "feed_ts": "2026-07-25T18:05:00Z",
            "action": "submit_entry",
            "side": "sell",
            "requested_qty": 2.0,
            "fill_px": 100.0,
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:11:00Z",
            "action": "cancel_entry",
            "side": "sell",
            "reason": "entry_ttl_expired",
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:12:00Z",
            "action": "regime_observation",
            "entry_direction": "short",
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert resumed is not None
    assert getattr(resumed, "expired_entry_direction", None) == "short"


def test_resume_clears_expired_direction_after_nonmatching_regime(
    tmp_path: Path,
) -> None:
    """A directionless regime observation durably re-arms later attempts."""
    path = tmp_path / "decisions.jsonl"
    common = {
        "run_id": "rearmed-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
        "position_qty": 0.0,
        "position_avg_px": 0.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "equity": 10_000.0,
    }
    rows = [
        {**common, "feed_ts": "session_start", "action": "session_start"},
        {
            **common,
            "feed_ts": "2026-07-25T18:05:00Z",
            "action": "submit_entry",
            "side": "buy",
            "requested_qty": 2.0,
            "fill_px": 100.0,
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:11:00Z",
            "action": "cancel_entry",
            "side": "buy",
            "reason": "entry_ttl_expired",
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:12:00Z",
            "action": "regime_observation",
            "entry_direction": None,
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert resumed is not None
    assert getattr(resumed, "expired_entry_direction", None) is None


def test_resume_restores_completed_direction_until_regime_reset(
    tmp_path: Path,
) -> None:
    """Restart cannot bypass the re-arm requirement after a completed long."""
    path = tmp_path / "decisions.jsonl"
    common = {
        "run_id": "completed-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
        "position_qty": 0.0,
        "position_avg_px": 0.0,
        "realized_pnl": 20.0,
        "unrealized_pnl": 0.0,
        "equity": 10_020.0,
    }
    rows = [
        {**common, "feed_ts": "session_start", "action": "session_start"},
        {
            **common,
            "feed_ts": "2026-07-25T18:00:00Z",
            "action": "enter_long",
            "fill_qty": 1.0,
            "position_qty": 1.0,
            "position_avg_px": 100.0,
            "realized_pnl": -0.1,
            "equity": 9_999.9,
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:05:00Z",
            "action": "close",
            "side": "sell",
        },
        {
            **common,
            "feed_ts": "2026-07-25T18:06:00Z",
            "action": "regime_observation",
            "entry_direction": "long",
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")

    resumed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert resumed is not None
    assert resumed.completed_trade_direction == "long"

    reset = {
        **common,
        "feed_ts": "2026-07-25T18:07:00Z",
        "action": "regime_observation",
        "entry_direction": None,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(reset)}\n")

    rearmed = load_shadow_portfolio_resume(path, symbol="BTC", timeframe="1m")

    assert rearmed is not None
    assert rearmed.completed_trade_direction is None
