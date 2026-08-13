"""Hash-chained material evidence for the exact v33 tracker."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.research.v33_route_change_journal import (
    append_v33_material_change,
)


def test_v33_material_state_uses_distinct_schema_and_chain(tmp_path: Path) -> None:
    path = tmp_path / "v33-changes.jsonl"
    snapshot = _snapshot()
    snapshot["schema_version"] = "v33_route_forward_snapshot_v1"
    snapshot["phase"] = "candidate_v33_forward"
    snapshot["candidate"]["profile_id"] = (
        "multi_asset_bidirectional_spcx_swing_retired_candidate_v33"
    )
    snapshot["assessment"]["candidate_active"] = True
    snapshot["assessment"]["recommendation"] = (
        "collect_v33_removed_vs_retained_control_evidence"
    )

    assert append_v33_material_change(path, snapshot) is True
    assert append_v33_material_change(path, snapshot) is False

    rows = _rows(path)
    assert len(rows) == 1
    assert rows[0]["schema_version"] == "v33_route_material_change_v1"
    assert rows[0]["phase"] == "candidate_v33_forward"


def _snapshot() -> dict[str, object]:
    return {
        "schema_version": "v31_route_forward_snapshot_v1",
        "generated_at_utc": "2026-08-09T23:10:00+00:00",
        "source_checkpoint_generated_at_utc": "2026-08-09T23:09:00+00:00",
        "phase": "pretransition_v25_baseline",
        "tracking_state": "candidate_inactive_baseline_captured",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "source_run": {
            "run_id": "run-v25",
            "profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
            "profile_fingerprint": "a" * 64,
        },
        "candidate": {
            "profile_id": "multi_asset_bidirectional_swing_pruned_candidate_v31",
            "profile_fingerprint": "b" * 64,
        },
        "assessment": {
            "automatic_transition_authorized": False,
            "candidate_active": False,
            "confidence": "medium",
            "current_open_positions": 1,
            "recommendation": "wait_for_flat",
        },
        "live_state": {
            "faults": 0,
            "all_open_positions_protected": True,
            "open_positions": [
                {
                    "symbol": "BTC",
                    "position_size_signed": 1.0,
                    "protected_if_open": True,
                    "stop_oid": 123,
                }
            ],
            "execution": {
                "closed_trades": 1,
                "wins": 1,
                "losses": 0,
                "net_pnl_usd": 0.1,
                "profit_factor": None,
                "fees_usd": 0.01,
                "funding_usd": 0.0,
            },
            "portfolio": {
                "final_equity_usd": 500.1,
                "maximum_drawdown_pct": 0.1,
                "maximum_margin_used_usd": 15.0,
                "maximum_notional_usd": 75.0,
            },
        },
        "routes": [
            {
                "route": "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX",
                "group": "removed",
                "current_authority": "executable",
                "candidate_authority": "observe_only",
                "eligible_signals": 1,
                "resolved_signal_horizons": 4,
                "forward_assessment": "descriptive_adverse_paths",
                "eligible_signal_horizons": {},
                "execution_performance": None,
            }
        ],
    }


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
