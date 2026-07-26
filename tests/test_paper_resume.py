"""Persistent Hypervelocity shadow portfolio restart tests."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.paper.resume import load_shadow_portfolio_resume


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
