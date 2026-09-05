"""Identity checks for the V58 post-outage report-only research epoch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_ROOT = Path(__file__).parents[1]
_JOURNAL = _ROOT / "docs/research-journal"
_LIVE_RUN = "bidirectional-live-1787272893887"
_OBSERVER_RUN = "bidirectional-observe-1787275983288"
_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_PROFILE_FINGERPRINT = (
    "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
)
_ROUTE_PREREGISTRATIONS = {
    "v58-btc-robust-v3-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hulk_expansion_short_robust_v3|BTC",
        3,
    ),
    "v58-btc-tuned-v2-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hulk_expansion_short_tuned_v2|BTC",
        3,
    ),
    "v58-sol-hulk-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hulk_expansion_bidirectional_tuned_v2|SOL",
        3,
    ),
    "v58-spcx-cash-open-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX",
        120,
    ),
    "v58-sndk-pressure-short-live-lifecycle-preregistration-20260821-v4.json": (
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:SNDK",
        4,
    ),
}
_EXPERIMENT_PREREGISTRATIONS = {
    "v58-sp500-lower-activation-profit-lock-future-only-preregistration-20260821-v4.json": (
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500",
        "xyz:SP500:520755869955",
    ),
    "v58-brentoil-profit-lock-future-only-preregistration-20260821-v4.json": (
        "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2|xyz:BRENTOIL",
        "xyz:BRENTOIL:520642502465",
    ),
}


@pytest.mark.parametrize(("filename", "expected"), _ROUTE_PREREGISTRATIONS.items())
def test_active_route_preregistration_rebinds_only_the_new_live_epoch(
    filename: str, expected: tuple[str, int]
) -> None:
    """Every active-route collector must start at the authenticated new run baseline."""
    payload = json.loads((_JOURNAL / filename).read_text())
    route, evaluations = expected
    identity = payload["live_identity"]
    boundary = payload["prospective_boundary"]

    assert identity["run_id"] == _LIVE_RUN
    assert identity["profile_id"] == _PROFILE
    assert identity["profile_fingerprint"] == _PROFILE_FINGERPRINT
    assert identity["route"] == route
    assert boundary["capture_start_ms"] == 1787276284274
    assert boundary["baseline_route_evaluations"] == evaluations
    assert boundary["baseline_eligible_evaluations"] == 0
    assert payload["contract"]["execution_authority"] == "none"
    assert payload["outage_recovery"]["pool_with_predecessor_epoch"] is False


def test_observer_lifecycle_preregistrations_exclude_the_retired_epoch() -> None:
    """BTC, ETH, and HYPE lifecycle evidence must use only the restarted observer."""
    btc = _load(
        "v58-btc-liquidity-sweep-exact-mark-lifecycle-preregistration-20260821-v3.json"
    )
    hype = _load(
        "v58-hype-alignment-exact-depth-shadow-lifecycle-preregistration-20260821-v3.json"
    )
    eth = _load("eth-breakout-precompression-pullback-v19.json")

    assert btc["observer_run_id"] == _OBSERVER_RUN
    assert hype["source"]["observer_run_id"] == _OBSERVER_RUN
    assert eth["frozen_identity"]["observer_run_id"] == _OBSERVER_RUN
    assert btc["ledger_prefix"] == hype["ledger_prefix"]
    assert btc["ledger_prefix"]["sha256"] == (
        "5abed7915649eff35a58979bfdc93fb69392c44349c5d4d7706271a3d7938517"
    )
    assert btc["analysis_contract"]["pool_with_predecessor_epoch"] is False
    assert hype["analysis_contract"]["pool_with_predecessor_epoch"] is False
    assert eth["frozen_identity"]["pool_with_predecessor_epoch"] is False


def test_active_route_override_sources_are_the_new_revisions() -> None:
    """The consolidator must not cite retired-run preregistrations as current."""
    overrides = json.loads(
        (
            _ROOT / "configs/research/v58_active_route_lifecycle_collectors.json"
        ).read_text()
    )
    rows = overrides["active_hypotheses"]
    sources = {Path(row["decision_source"]).name for row in rows}

    assert sources == set(_ROUTE_PREREGISTRATIONS)


@pytest.mark.parametrize(("filename", "expected"), _EXPERIMENT_PREREGISTRATIONS.items())
def test_future_only_exit_experiments_rebind_without_reusing_open_trades(
    filename: str, expected: tuple[str, str]
) -> None:
    """Inherited open positions remain excluded from post-outage policy selection."""
    payload = _load(filename)
    route, excluded_lifecycle = expected

    assert payload["live_identity"]["run_id"] == _LIVE_RUN
    assert payload["live_identity"]["route"] == route
    assert payload["prospective_boundary"]["capture_start_ms"] == 1787276284274
    assert payload["prospective_boundary"]["baseline_route_evaluations"] == 4
    assert payload["prospective_boundary"]["baseline_eligible_evaluations"] == 0
    assert payload["hypothesis_formation_evidence"]["excluded_lifecycle_ids"] == [
        excluded_lifecycle
    ]
    assert (
        payload["hypothesis_formation_evidence"]["may_support_policy_selection"]
        is False
    )
    assert payload["contract"]["execution_authority"] == "none"


def test_future_only_override_sources_are_the_new_revisions() -> None:
    """The consolidator must cite current-run future-only preregistrations."""
    overrides = json.loads(
        (
            _ROOT / "configs/research/v58_active_route_lifecycle_collectors.json"
        ).read_text()
    )
    rows = overrides["active_experiments"]

    assert {Path(row["decision_source"]).name for row in rows} == set(
        _EXPERIMENT_PREREGISTRATIONS
    )


def _load(filename: str) -> dict[str, object]:
    return json.loads((_JOURNAL / filename).read_text())
