"""Identity tests for the remaining V58 exact-route lifecycle collectors."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest


_ROOT = Path(__file__).parents[1]
_JOURNAL = _ROOT / "docs/research-journal"
_RUN_ID = "bidirectional-live-1787272893887"
_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_FINGERPRINT = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_BRENTOIL_FORWARD = (
    _JOURNAL / "v58-brentoil-profit-lock-future-only-preregistration-20260821-v4.json"
)
_SP500_FORWARD = (
    _JOURNAL
    / "v58-sp500-lower-activation-profit-lock-future-only-preregistration-20260821-v4.json"
)
_ROUTES = {
    "v58-btc-robust-v3-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hulk_expansion_short_robust_v3",
        "BTC",
        3,
    ),
    "v58-btc-tuned-v2-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hulk_expansion_short_tuned_v2",
        "BTC",
        3,
    ),
    "v58-sol-hulk-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hulk_expansion_bidirectional_tuned_v2",
        "SOL",
        3,
    ),
    "v58-spcx-cash-open-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1",
        "xyz:SPCX",
        120,
    ),
    "v58-sndk-pressure-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2",
        "xyz:SNDK",
        4,
    ),
}


def test_v58_brentoil_profit_lock_lane_excludes_hypothesis_formation_trade() -> None:
    """The existing open trade must not validate a future exit policy."""
    payload = json.loads(_BRENTOIL_FORWARD.read_text())
    boundary = payload["prospective_boundary"]

    assert payload["mode"] == "v57_exact_route_lifecycle_tracker_preregistration"
    assert payload["hypothesis_id"] == "v58-brentoil-profit-lock-future-only-v1"
    assert payload["live_identity"] == {
        "run_id": _RUN_ID,
        "profile_id": _PROFILE,
        "profile_fingerprint": _FINGERPRINT,
        "provider_id": "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2",
        "signal_strategy_id": "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2",
        "symbol": "xyz:BRENTOIL",
        "route": "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL",
        "required_sides": ["long", "short"],
    }
    assert boundary["capture_start_ms"] == 1787276284274
    assert boundary["baseline_route_evaluations"] == 4
    assert boundary["baseline_eligible_evaluations"] == 0
    formation = payload["hypothesis_formation_evidence"]
    assert formation["excluded_lifecycle_ids"] == ["xyz:BRENTOIL:520642502465"]
    assert formation["may_support_policy_selection"] is False
    assert payload["exit_policy_diagnostic"]["policy_ids"] == [
        "a25_floor15_trail10",
        "a40_floor15_trail20",
        "a60_floor15_trail30",
    ]
    assert (
        payload["minimum_diagnostic_evidence"]["route_resolution_is_policy_verdict"]
        is False
    )
    assert payload["contract"]["execution_authority"] == "none"
    _assert_lineage_evidence(payload["lineage_evidence"])
    _assert_implementation_evidence(payload["implementation_evidence"])


def test_v58_sp500_profit_lock_lane_excludes_current_open_trade() -> None:
    """The observed SP500 giveback must not select a future exit policy."""
    payload = json.loads(_SP500_FORWARD.read_text())
    boundary = payload["prospective_boundary"]

    assert payload["mode"] == "v57_exact_route_lifecycle_tracker_preregistration"
    assert payload["hypothesis_id"] == (
        "v58-sp500-lower-activation-profit-lock-future-only-v1"
    )
    assert payload["live_identity"] == {
        "run_id": _RUN_ID,
        "profile_id": _PROFILE,
        "profile_fingerprint": _FINGERPRINT,
        "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
        "signal_strategy_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
        "symbol": "xyz:SP500",
        "route": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500",
        "required_sides": ["long", "short"],
    }
    assert boundary["capture_start_ms"] == 1787276284274
    assert boundary["baseline_route_evaluations"] == 4
    assert boundary["baseline_eligible_evaluations"] == 0
    formation = payload["hypothesis_formation_evidence"]
    assert formation["excluded_lifecycle_ids"] == ["xyz:SP500:520755869955"]
    assert formation["may_support_policy_selection"] is False
    diagnostic = payload["exit_policy_diagnostic"]
    assert diagnostic["policy_ids"] == [
        "a25_floor15_trail10",
        "a40_floor15_trail20",
        "a60_floor15_trail30",
    ]
    assert diagnostic["control_exit_contract"] == (
        "protective_stop_then_completed_bar_trailing_100_40_80_then_"
        "opposite_eligible_intent_then_fixed_24h_maximum_hold"
    )
    minimum = payload["minimum_diagnostic_evidence"]
    assert minimum["route_resolution_is_policy_verdict"] is False
    assert minimum["promotion_threshold"] is False
    assert payload["contract"]["execution_authority"] == "none"
    _assert_lineage_evidence(payload["lineage_evidence"])
    _assert_implementation_evidence(payload["implementation_evidence"])


@pytest.mark.parametrize(("filename", "expected"), _ROUTES.items())
def test_v58_route_preregistration_is_exact_and_source_bound(
    filename: str, expected: tuple[str, str, int]
) -> None:
    """Each remaining route must freeze the exact V58 run and source bytes."""
    payload = json.loads((_JOURNAL / filename).read_text())
    provider, symbol, baseline = expected
    identity = payload["live_identity"]
    boundary = payload["prospective_boundary"]

    assert payload["mode"] == "v57_exact_route_lifecycle_tracker_preregistration"
    assert identity == {
        "run_id": _RUN_ID,
        "profile_id": _PROFILE,
        "profile_fingerprint": _FINGERPRINT,
        "provider_id": provider,
        "signal_strategy_id": provider,
        "symbol": symbol,
        "route": f"{provider}|{symbol}",
        "required_sides": ["short"],
    }
    assert boundary["capture_start_ms"] == 1787276284274
    assert boundary["baseline_route_evaluations"] == baseline
    assert boundary["baseline_eligible_evaluations"] == 0
    assert payload["outage_recovery"]["pool_with_predecessor_epoch"] is False
    assert payload["contract"]["execution_authority"] == "none"
    _assert_lineage_evidence(payload["lineage_evidence"])
    _assert_implementation_evidence(payload["implementation_evidence"])


def _assert_lineage_evidence(rows: list[dict[str, object]]) -> None:
    assert {row["role"] for row in rows} == {
        "semantic_predecessor_v2",
        "technical_predecessor_v3",
    }
    for row in rows:
        path = _JOURNAL / str(row["path"])
        raw = path.read_bytes()
        assert row["bytes"] == len(raw)
        assert row["sha256"] == sha256(raw).hexdigest()


def _assert_implementation_evidence(rows: list[dict[str, object]]) -> None:
    assert len(rows) == 4
    for row in rows:
        path = _ROOT / str(row["path"])
        raw = path.read_bytes()
        assert row["bytes"] == len(raw)
        assert row["sha256"] == sha256(raw).hexdigest()
