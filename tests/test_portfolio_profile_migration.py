"""Safety tests for persistent shadow portfolio profile migrations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.paper.resume import (
    ShadowResumeError,
    load_shadow_portfolio_resume,
    portfolio_fingerprint,
)


def _execution_spec(max_event_age_ms: int) -> dict[str, object]:
    return {
        "strategy_name": "hypervelocity_1m_scalper",
        "execution": {
            "max_event_age_ms": max_event_age_ms,
            "restart_queue_policy": "requeue_behind_displayed_liquidity",
        },
    }


def _common_row() -> dict[str, object]:
    return {
        "run_id": "event-age-migration-run",
        "execution_mode": "shadow",
        "strategy_name": "hypervelocity_1m_scalper",
        "symbol": "BTC",
        "timeframe": "1m",
        "init_cash": 10_000.0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "equity": 10_000.0,
    }


def test_flat_pending_entry_accepts_measured_event_age_upgrade(
    tmp_path: Path,
) -> None:
    """A 3s-to-6s upgrade may resume only an unfilled requeued maker order."""
    path = tmp_path / "decisions.jsonl"
    old_spec = _execution_spec(3_000)
    new_spec = _execution_spec(6_000)
    common = _common_row()
    rows = [
        {
            **common,
            "feed_ts": "session_start",
            "action": "session_start",
            "portfolio_spec": old_spec,
            "position_qty": 0.0,
            "position_avg_px": 0.0,
        },
        {
            **common,
            "feed_ts": "2026-07-28T21:18:00Z",
            "action": "submit_entry",
            "side": "buy",
            "requested_qty": 1.0,
            "fill_px": 63_883.0,
            "order_status": "pending",
            "position_qty": 0.0,
            "position_avg_px": 0.0,
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows))

    resumed = load_shadow_portfolio_resume(
        path,
        symbol="BTC",
        timeframe="1m",
        expected_spec=new_spec,
    )

    assert resumed is not None
    assert resumed.pending_entry is not None
    assert resumed.portfolio_fingerprint == portfolio_fingerprint(new_spec)
    assert resumed.portfolio_profile_changed_from == portfolio_fingerprint(old_spec)


def test_open_position_rejects_measured_event_age_upgrade(tmp_path: Path) -> None:
    """Changing execution freshness cannot alter an already-filled position."""
    path = tmp_path / "decisions.jsonl"
    old_spec = _execution_spec(3_000)
    new_spec = _execution_spec(6_000)
    common = _common_row()
    rows = [
        {
            **common,
            "feed_ts": "session_start",
            "action": "session_start",
            "portfolio_spec": old_spec,
            "position_qty": 0.0,
            "position_avg_px": 0.0,
        },
        {
            **common,
            "feed_ts": "2026-07-28T21:18:00Z",
            "action": "enter_long",
            "fill_qty": 1.0,
            "position_qty": 1.0,
            "position_avg_px": 63_883.0,
        },
    ]
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows))

    with pytest.raises(ShadowResumeError, match="incompatible.*open position"):
        load_shadow_portfolio_resume(
            path,
            symbol="BTC",
            timeframe="1m",
            expected_spec=new_spec,
        )
