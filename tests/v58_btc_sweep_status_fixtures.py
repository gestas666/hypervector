"""Exact V58 BTC sweep watcher fixtures shared by focused tests."""

from __future__ import annotations

from datetime import datetime, timedelta


def btc_sweep_status(
    now: datetime, run_id: str, profile_fingerprint: str
) -> dict[str, object]:
    """Return one unresolved, fresh, report-only BTC watcher status."""
    profile_id = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
    contract = {
        "report_only": True,
        "execution_authority": "none",
        "portfolio_pnl_claimed": False,
        "actual_orders_or_fills_claimed": False,
        "source_strategy_id": "liquidity_sweep_long_1h_stop60_target60_v2",
        "symbol": "BTC",
        "source_run_id": run_id,
        "profile_id": profile_id,
        "profile_fingerprint": profile_fingerprint,
        "sides": ["long"],
        "notional_usd": 5_000.0,
        "stop_bps": 60.0,
        "target_bps": 60.0,
        "maximum_hold_minutes": 1_440,
        "maximum_entry_delay_ms": 30_000,
    }
    return {
        "schema_version": 1,
        "mode": "v58_btc_sweep_exact_mark_depth_lifecycle_v1",
        "state": "awaiting_resolution",
        "watch_state": "awaiting_resolution",
        "watch_state_id": "unused_without_snapshot",
        "observed_at_utc": (now - timedelta(seconds=10)).isoformat(),
        "snapshot": None,
        "contract": contract,
        "identity": {
            "profile_id": profile_id,
            "profile_fingerprint": profile_fingerprint,
            "source_run_id": run_id,
            "prospective_start_ms": 1,
        },
        "summary": {
            "selected_non_overlapping": 0,
            "overlapping_excluded": 0,
            "resolved": 0,
            "pending": 0,
            "technical_incomplete": 0,
        },
        "latest_attempts": [],
        "latest_executions": [],
    }
