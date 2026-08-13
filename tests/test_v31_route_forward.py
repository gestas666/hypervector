"""Contracts for prospective v31 route-pruning telemetry."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v31_route_forward import (
    REMOVED_ROUTES,
    RETAINED_CONTROL_ROUTES,
    build_v31_route_forward_snapshot,
)
from hypervector.research.v32_route_forward import (
    REMOVED_ROUTES as V32_REMOVED_ROUTES,
    RETAINED_CONTROL_ROUTES as V32_RETAINED_CONTROL_ROUTES,
    build_v32_route_forward_snapshot,
)

_SOURCE = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_CANDIDATE = Path("configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml")
_JOURNAL = Path("docs/research-journal/hip3-route-authority-pruning-v1.json")
_V32_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_commodity_swing_retired_candidate_v32.toml"
)
_V32_JOURNAL = Path("docs/research-journal/hip3-route-authority-pruning-v3.json")


def test_v25_snapshot_is_a_strict_pretransition_baseline() -> None:
    snapshot = _build_snapshot("source")

    assert snapshot["contract"]["execution_authority"] == "none"
    assert snapshot["phase"] == "pretransition_v25_baseline"
    assert snapshot["tracking_state"] == "candidate_inactive_baseline_captured"
    assert snapshot["protocol"]["declared_at_utc"] == "2026-08-09T18:44:02Z"
    assert snapshot["protocol"]["counters_are_cumulative_from_run_start"] is True
    assert snapshot["candidate"]["maximum_positions"] == 9
    assert snapshot["candidate"]["both_directions"] is True
    assert {row["route"] for row in snapshot["routes"]} == set(
        REMOVED_ROUTES + RETAINED_CONTROL_ROUTES
    )
    removed = [row for row in snapshot["routes"] if row["group"] == "removed"]
    assert {row["current_authority"] for row in removed} == {"executable"}
    assert {row["candidate_authority"] for row in removed} == {"observe_only"}


def test_v31_snapshot_requires_removed_routes_observe_only() -> None:
    snapshot = _build_snapshot("candidate")

    assert snapshot["phase"] == "candidate_v31_forward"
    assert snapshot["tracking_state"] == "candidate_forward_tracking"
    removed = [row for row in snapshot["routes"] if row["group"] == "removed"]
    controls = [row for row in snapshot["routes"] if row["group"] == "control"]
    assert {row["current_authority"] for row in removed} == {"observe_only"}
    assert {row["current_authority"] for row in controls} == {"executable"}
    assert snapshot["assessment"]["automatic_transition_authorized"] is False


def test_snapshot_rejects_candidate_authority_drift() -> None:
    checkpoint = _checkpoint("candidate")
    removed = REMOVED_ROUTES[0]
    checkpoint["audit"]["run"]["observe_only_provider_symbols"].remove(removed)
    checkpoint["audit"]["run"]["executable_provider_symbols"].append(removed)

    with pytest.raises(ValueError, match="candidate executable route scope"):
        _snapshot(checkpoint)


def test_snapshot_rejects_unknown_profile_and_missing_route() -> None:
    checkpoint = _checkpoint("source")
    checkpoint["audit"]["run"]["profile_id"] = "unknown"
    with pytest.raises(ValueError, match="not v25 or v31"):
        _snapshot(checkpoint)

    checkpoint = _checkpoint("source")
    checkpoint["audit"]["strategy_scorecard"]["by_provider_symbol"].pop(
        REMOVED_ROUTES[0]
    )
    with pytest.raises(ValueError, match="missing tracked route scorecards"):
        _snapshot(checkpoint)


def test_snapshot_rejects_changed_journal_candidate_hash() -> None:
    journal = _journal()
    evidence = next(
        row
        for row in journal["evidence"]
        if row["role"] == "inactive_exact_diff_candidate"
    )
    evidence["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="candidate config SHA-256"):
        build_v31_route_forward_snapshot(
            _checkpoint("source"), journal, _SOURCE, _CANDIDATE
        )


def test_v32_snapshot_tracks_all_three_retired_swing_routes() -> None:
    checkpoint = _v32_checkpoint()
    snapshot = build_v32_route_forward_snapshot(
        checkpoint, _v32_journal(), _SOURCE, _V32_CANDIDATE
    )

    assert snapshot["schema_version"] == "v32_route_forward_snapshot_v1"
    assert snapshot["phase"] == "candidate_v32_forward"
    assert snapshot["candidate"]["both_directions"] is True
    removed = [row for row in snapshot["routes"] if row["group"] == "removed"]
    controls = [row for row in snapshot["routes"] if row["group"] == "control"]
    assert {row["route"] for row in removed} == set(V32_REMOVED_ROUTES)
    assert {row["route"] for row in controls} == set(V32_RETAINED_CONTROL_ROUTES)
    assert {row["current_authority"] for row in removed} == {"observe_only"}
    assert {row["current_authority"] for row in controls} == {"executable"}


def _build_snapshot(phase: str) -> dict[str, object]:
    return _snapshot(_checkpoint(phase))


def _snapshot(checkpoint: dict[str, object]) -> dict[str, object]:
    return build_v31_route_forward_snapshot(checkpoint, _journal(), _SOURCE, _CANDIDATE)


def _checkpoint(phase: str) -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-09T19:00:00+00:00",
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "transition_drain": {"status": "inactive"},
        "audit": _audit(phase),
    }


def _audit(phase: str) -> dict[str, object]:
    source = load_multi_asset_live_config(_SOURCE, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    active = source if phase == "source" else candidate
    observed = {
        (provider.strategy_id, symbol)
        for provider in active.providers
        for symbol in provider.symbols
    }
    executable = active.executable_provider_symbols
    return {
        "run": {
            "run_id": f"{phase}-run",
            "profile_id": active.profile_id,
            "profile_fingerprint": active.profile_fingerprint,
            "executable_provider_symbols": _route_strings(executable),
            "observe_only_provider_symbols": _route_strings(
                observed.difference(executable)
            ),
        },
        "strategy_scorecard": {"by_provider_symbol": _scores(phase)},
        "execution": {"closed_trades": 4, "net_pnl_usd": 1.0},
        "portfolio": {"final_equity_usd": 501.0},
        "health": {"faults": 0, "assets": {"ETH": _open_asset()}},
    }


def _scores(phase: str) -> dict[str, object]:
    scores: dict[str, object] = {}
    for index, route in enumerate(REMOVED_ROUTES + RETAINED_CONTROL_ROUTES):
        score = _score(index)
        if phase == "candidate" and route in REMOVED_ROUTES:
            for field in (
                "execution_performance",
                "execution_performance_by_side",
                "repeatability_evidence",
            ):
                score.pop(field, None)
        scores[route] = score
    return scores


def _open_asset() -> dict[str, object]:
    return {
        "final_state": "OPEN",
        "position_size_signed": -0.1,
        "protected_if_open": True,
        "stop_oid": 123,
        "open_order_ids": [123],
    }


def _score(index: int) -> dict[str, object]:
    score: dict[str, object] = {
        "forward_evaluations": 100 + index,
        "eligible_signals": 1 if index == 0 else 0,
        "resolved_signal_horizons": 1 if index == 0 else 0,
        "forward_assessment": "descriptive_adverse_paths",
        "eligible_signal_horizons": {"15": {"resolved": 1}} if index == 0 else {},
    }
    if index == 0:
        score["execution_performance"] = {
            "closed_trades": 1,
            "wins": 0,
            "losses": 1,
            "fees_usd": 0.1,
            "funding_usd": -0.01,
            "net_pnl_usd": -1.0,
            "profit_factor": 0.0,
        }
        score["execution_performance_by_side"] = {"short": {"closed_trades": 1}}
        score["repeatability_evidence"] = {"net_pnl_excluding_largest_winner_usd": None}
    return score


def _journal() -> dict[str, object]:
    return deepcopy(json.loads(_JOURNAL.read_text(encoding="utf-8")))


def _v32_checkpoint() -> dict[str, object]:
    candidate = load_multi_asset_live_config(_V32_CANDIDATE, mode="observe")
    observed = {
        (provider.strategy_id, symbol)
        for provider in candidate.providers
        for symbol in provider.symbols
    }
    executable = candidate.executable_provider_symbols
    tracked = V32_REMOVED_ROUTES + V32_RETAINED_CONTROL_ROUTES
    scores = {route: _score(index) for index, route in enumerate(tracked)}
    for route in V32_REMOVED_ROUTES:
        for field in (
            "execution_performance",
            "execution_performance_by_side",
            "repeatability_evidence",
        ):
            scores[route].pop(field, None)
    return {
        "generated_at_utc": "2026-08-09T23:00:00+00:00",
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "transition_drain": {"status": "inactive"},
        "audit": {
            "run": {
                "run_id": "v32-live-run",
                "profile_id": candidate.profile_id,
                "profile_fingerprint": candidate.profile_fingerprint,
                "executable_provider_symbols": _route_strings(executable),
                "observe_only_provider_symbols": _route_strings(observed - executable),
            },
            "strategy_scorecard": {"by_provider_symbol": scores},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "portfolio": {"final_equity_usd": 500.0},
            "health": {"faults": 0, "assets": {}},
        },
    }


def _v32_journal() -> dict[str, object]:
    return deepcopy(json.loads(_V32_JOURNAL.read_text(encoding="utf-8")))


def _route_strings(routes: object) -> list[str]:
    return sorted(f"{provider}|{symbol}" for provider, symbol in routes)
