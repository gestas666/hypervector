"""Contracts for the compact append-only v31 material-change journal."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from hypervector.research.v31_route_change_journal import (
    append_v31_material_change,
)
from hypervector.research.v32_route_change_journal import (
    append_v32_material_change,
)


def test_first_material_state_is_appended_with_report_only_contract(
    tmp_path: Path,
) -> None:
    """The first state must create one hash-bound report-only event."""
    path = tmp_path / "changes.jsonl"

    appended = append_v31_material_change(path, _snapshot())

    rows = _rows(path)
    assert appended is True
    assert len(rows) == 1
    assert rows[0]["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_transition": False,
        "automatic_retuning": False,
    }
    assert rows[0]["previous_event_sha256"] is None
    assert rows[0]["event_sha256"]


def test_timestamp_and_evaluation_only_refresh_is_deduplicated(tmp_path: Path) -> None:
    """Two-minute refresh noise must not grow the durable journal."""
    path = tmp_path / "changes.jsonl"
    first = _snapshot()
    second = deepcopy(first)
    second["generated_at_utc"] = "2026-08-09T20:02:00+00:00"
    second["source_checkpoint_generated_at_utc"] = "2026-08-09T20:01:00+00:00"
    routes = second["routes"]
    assert isinstance(routes, list)
    routes[0]["forward_evaluations"] = 138
    live = second["live_state"]
    assert isinstance(live, dict)
    portfolio = live["portfolio"]
    assert isinstance(portfolio, dict)
    portfolio["final_equity_usd"] = 503.91
    portfolio["maximum_drawdown_pct"] = 0.43

    assert append_v31_material_change(path, first) is True
    assert append_v31_material_change(path, second) is False

    assert len(_rows(path)) == 1


def test_economic_change_appends_a_hash_chained_event(tmp_path: Path) -> None:
    """A resolved outcome must be retained as a new material decision state."""
    path = tmp_path / "changes.jsonl"
    first = _snapshot()
    second = deepcopy(first)
    routes = second["routes"]
    assert isinstance(routes, list)
    routes[0]["eligible_signals"] = 2
    routes[0]["resolved_signal_horizons"] = 8

    assert append_v31_material_change(path, first) is True
    assert append_v31_material_change(path, second) is True

    rows = _rows(path)
    assert len(rows) == 2
    assert rows[1]["previous_event_sha256"] == rows[0]["event_sha256"]
    assert rows[1]["routes"][0]["eligible_signals"] == 2


def test_corrupt_existing_chain_is_rejected(tmp_path: Path) -> None:
    """A malformed durable journal cannot be treated as an empty history."""
    path = tmp_path / "changes.jsonl"
    path.write_text('{"event_sha256":"wrong"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="journal event"):
        append_v31_material_change(path, _snapshot())


def test_execution_capable_snapshot_is_rejected(tmp_path: Path) -> None:
    """The change recorder accepts only execution-incapable source reports."""
    snapshot = _snapshot()
    contract = snapshot["contract"]
    assert isinstance(contract, dict)
    contract["execution_authority"] = "live"

    with pytest.raises(ValueError, match="execution authority"):
        append_v31_material_change(tmp_path / "changes.jsonl", snapshot)


def test_v32_material_state_uses_distinct_schema_and_chain(tmp_path: Path) -> None:
    path = tmp_path / "v32-changes.jsonl"
    snapshot = _snapshot()
    snapshot["schema_version"] = "v32_route_forward_snapshot_v1"
    snapshot["phase"] = "candidate_v32_forward"
    snapshot["candidate"]["profile_id"] = (
        "multi_asset_bidirectional_commodity_swing_retired_candidate_v32"
    )
    snapshot["assessment"]["candidate_active"] = True
    snapshot["assessment"]["recommendation"] = (
        "collect_v32_removed_vs_breakout_control_evidence"
    )

    assert append_v32_material_change(path, snapshot) is True
    assert append_v32_material_change(path, snapshot) is False

    rows = _rows(path)
    assert len(rows) == 1
    assert rows[0]["schema_version"] == "v32_route_material_change_v1"
    assert rows[0]["phase"] == "candidate_v32_forward"


def _snapshot() -> dict[str, object]:
    return {
        "schema_version": "v31_route_forward_snapshot_v1",
        "generated_at_utc": "2026-08-09T20:00:00+00:00",
        "source_checkpoint_generated_at_utc": "2026-08-09T19:59:00+00:00",
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
            "recommendation": "wait_for_flat_and_explicit_v31_authorization",
        },
        "live_state": {
            "faults": 0,
            "all_open_positions_protected": True,
            "open_positions": [
                {
                    "symbol": "SOL",
                    "position_size_signed": 1.0,
                    "protected_if_open": True,
                    "stop_oid": 123,
                }
            ],
            "execution": {
                "closed_trades": 12,
                "wins": 6,
                "losses": 6,
                "net_pnl_usd": 1.97,
                "profit_factor": 1.8,
                "fees_usd": 0.47,
                "funding_usd": -0.08,
            },
            "portfolio": {
                "final_equity_usd": 504.27,
                "maximum_drawdown_pct": 0.41,
                "maximum_margin_used_usd": 46.05,
                "maximum_notional_usd": 225.51,
            },
        },
        "routes": [
            {
                "route": "hip3_swing_ha_sndk_gold_brent_bidirectional_v1|xyz:SNDK",
                "group": "removed",
                "current_authority": "executable",
                "candidate_authority": "observe_only",
                "forward_evaluations": 137,
                "eligible_signals": 1,
                "resolved_signal_horizons": 4,
                "forward_assessment": "descriptive_adverse_paths",
                "eligible_signal_horizons": {
                    "5": {
                        "independent": 1,
                        "resolved": 1,
                        "mean_directional_return_bps": -1.0,
                        "positive_directional_rate": 0.0,
                    }
                },
                "execution_performance": {
                    "closed_trades": 1,
                    "wins": 0,
                    "losses": 1,
                    "net_pnl_usd": -1.09,
                    "profit_factor": 0.0,
                    "fees_usd": 0.01,
                    "funding_usd": 0.01,
                },
            }
        ],
    }


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
