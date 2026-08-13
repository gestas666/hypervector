"""Machine-bound contract for the inactive v25-to-v31 transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v31.md")
_V32_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v32.md")
_CURRENT = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_CANDIDATE = Path("configs/multi_asset_bidirectional_swing_pruned_candidate_v31.toml")
_V32_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_commodity_swing_retired_candidate_v32.toml"
)
_JOURNAL = Path("docs/research-journal/hip3-route-authority-pruning-v2.json")
_V32_JOURNAL = Path("docs/research-journal/hip3-route-authority-pruning-v3.json")
_BASELINE = Path(
    "data/logs/research/bidirectional_cohort/"
    "v31_route_forward_baseline_20260809T185635Z.json"
)
_COMPARISON = Path("data/logs/research/hip3_route_authority_pruning_20260809.json")
_PRESSURE_DIAGNOSTIC = Path(
    "data/logs/research/bidirectional_cohort/"
    "v25_hip3_pressure_clock_root_cause_20260808T193618Z.json"
)
_PRESSURE_OBSERVER = Path(
    "data/logs/research/bidirectional_cohort/"
    "v25_pressure_parity_observer_20260808T201243Z.json"
)
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v31_runbook_binds_exact_authority_delta_and_evidence() -> None:
    contract = _contract(_RUNBOOK.read_text(encoding="utf-8"))
    current = load_multi_asset_live_config(_CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    observed = {
        (provider.strategy_id, symbol)
        for provider in candidate.providers
        for symbol in provider.symbols
    }
    executable = candidate.executable_provider_symbols

    assert contract["current_profile_fingerprint"] == current.profile_fingerprint
    assert contract["candidate_profile_fingerprint"] == candidate.profile_fingerprint
    assert contract["candidate_run_fingerprint_observe"] == candidate.run_fingerprint
    assert contract["current_file_sha256"] == _sha(_CURRENT)
    assert contract["candidate_file_sha256"] == _sha(_CANDIDATE)
    assert contract["execution_scope"] == _routes(executable)
    assert contract["observe_only_scope"] == _routes(observed - executable)
    assert len(contract["execution_scope"]) == 22
    assert contract["maximum_positions"] == len(candidate.assets) == 9
    assert contract["research_revision_id"] == (
        "ec25c0b3a4ce9fb5151a1dc0d23e88b4e917ce0c50c1664e68b79ba4c627fbf4"
    )
    assert contract["research_record_sha256"] == _sha(_JOURNAL)
    assert contract["forward_baseline_sha256"] == _sha(_BASELINE)
    assert contract["comparison_artifact_sha256"] == _sha(_COMPARISON)
    assert contract["pressure_clock_diagnostic_sha256"] == _sha(_PRESSURE_DIAGNOSTIC)
    assert contract["pressure_repair_observer_sha256"] == _sha(_PRESSURE_OBSERVER)


def test_v31_runbook_stays_fail_closed_until_fresh_flat_boundary() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    contract = _contract(text)

    assert contract["candidate_active"] is False
    assert contract["transition_authorized"] is False
    assert contract["flat_and_order_free_verified"] is False
    assert contract["transition_readiness_snapshot"] is None
    assert contract["prechange_bundle"] is None
    for required in (
        "v25 remains active",
        "does not authorize a restart",
        'transition_drain.status == "completed"',
        "scripts/cohort_transition_drain_archive.py",
        "scripts/cohort_prestart_backup_verify.py",
        "--resume-transition-drain",
        "--enabled --i-accept-live-risk",
        "No hot rollback",
        "both long and short",
        "one position per asset",
    ):
        assert required in text


def test_v31_runbook_requires_post_start_hip3_pressure_adoption() -> None:
    """The successor must prove the staged causal pressure clock is loaded."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    for required in (
        "first completed HIP-3 breakout-pressure evaluation",
        "scripts/v31_poststart_acceptance.py",
        "scripts/v31_raw_ledger_acceptance.py",
        "v31_route_material_changes.jsonl",
        "material route, economic, authority, or health state changes",
        "causal_pressure_books",
        "funding_cursor_continuity",
        '"accepted": true',
        "exit status 2",
        "`imbalance_10`",
        "`pressure_age_seconds`",
        "finite",
        "numeric",
        "30-second maximum",
        "historical v25 metric gaps remain attributed",
        "do not relabel them as complete",
    ):
        assert required in text


def test_v32_runbook_binds_the_superseding_exact_authority_delta() -> None:
    """V32 must bind its own fingerprint rather than inherit v31 authority."""
    text = _V32_RUNBOOK.read_text(encoding="utf-8")
    contract = _contract(text)
    current = load_multi_asset_live_config(_CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(_V32_CANDIDATE, mode="observe")
    observed = {
        (provider.strategy_id, symbol)
        for provider in candidate.providers
        for symbol in provider.symbols
    }

    assert contract["current_profile_fingerprint"] == current.profile_fingerprint
    assert contract["candidate_profile_fingerprint"] == candidate.profile_fingerprint
    assert contract["candidate_run_fingerprint_observe"] == candidate.run_fingerprint
    assert contract["current_file_sha256"] == _sha(_CURRENT)
    assert contract["candidate_file_sha256"] == _sha(_V32_CANDIDATE)
    assert contract["research_record_sha256"] == _sha(_V32_JOURNAL)
    assert contract["research_revision_id"] == (
        "482feff06a142dcd4a906c58be1f49b0e42df3f71cd1469838c6fe56fedec2a5"
    )
    assert contract["execution_scope"] == _routes(candidate.executable_provider_symbols)
    assert contract["observe_only_scope"] == _routes(
        observed - candidate.executable_provider_symbols
    )
    assert len(contract["execution_scope"]) == 21
    assert len(contract["observe_only_scope"]) == 3


def test_v32_runbook_is_inactive_and_requires_a_fresh_flat_boundary() -> None:
    """A superseding candidate must not inherit v31 transition readiness."""
    text = _V32_RUNBOOK.read_text(encoding="utf-8")
    contract = _contract(text)

    assert contract["candidate_active"] is False
    assert contract["transition_authorized"] is False
    assert contract["flat_and_order_free_verified"] is False
    assert contract["transition_readiness_snapshot"] is None
    assert contract["prechange_bundle"] is None
    assert contract["post_start_acceptance_ready"] is True
    assert contract["route_forward_tracking_ready"] is True
    assert contract["route_forward_tracker_active"] is False
    assert contract["route_forward_baseline_phase"] == "pretransition_v25_baseline"
    assert not any(
        "acceptance is not implemented" in blocker
        for blocker in contract["readiness_blockers"]
    )
    for required in (
        "v25 remains active",
        "v31 is superseded",
        "does not authorize a restart",
        'transition_drain.status == "completed"',
        "scripts/cohort_transition_drain_archive.py",
        "scripts/cohort_prestart_backup_verify.py",
        "--resume-transition-drain",
        "--enabled --i-accept-live-risk",
        "No hot rollback",
        "both long and short",
        "one position per asset",
        "first completed HIP-3 breakout-pressure evaluation",
        "scripts/v32_acceptance.py",
        "scripts/v32_route_forward_monitor.py --once",
        "v32_route_material_changes.jsonl",
        "v31 identity remains isolated",
        "v32_poststart_acceptance_v1",
        "v32_raw_ledger_acceptance_v1",
        "exit status 2",
    ):
        assert required in text


def _contract(text: str) -> dict[str, object]:
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json") and fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _routes(routes: object) -> list[str]:
    return sorted(f"{provider}|{symbol}" for provider, symbol in routes)
