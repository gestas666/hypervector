"""Machine-bound contract for the v25-to-v26 telemetry-repair transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.cohort_prestart_backup import verify_cohort_prestart_backup
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v26.md")
_CURRENT = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_complete_portfolio_canary_v26.toml"
)
_PRECHANGE_BUNDLE = Path(
    "data/backups/bidirectional_cohort/prestart_20260808T023732.159368Z_2e5a46960175"
)
_CLI_SKILL = Path("skills/hypervector-cli/SKILL.md")
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v26_runbook_binds_profiles_routes_and_verified_source_baseline() -> None:
    """The transition must bind exact config and implementation identities."""
    contract = _contract(_RUNBOOK.read_text(encoding="utf-8"))
    current = load_multi_asset_live_config(_CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    expected_routes = [
        f"{provider.strategy_id}|{symbol}"
        for provider in candidate.providers
        for symbol in provider.execution_symbols
    ]
    manifest = json.loads(
        (_PRECHANGE_BUNDLE / "manifest.json").read_text(encoding="utf-8")
    )

    assert contract["current_path"] == str(_CURRENT)
    assert contract["current_profile_id"] == current.profile_id
    assert contract["current_profile_fingerprint"] == current.profile_fingerprint
    assert contract["current_file_sha256"] == sha256(_CURRENT.read_bytes()).hexdigest()
    assert contract["candidate_path"] == str(_CANDIDATE)
    assert contract["candidate_profile_id"] == candidate.profile_id
    assert contract["candidate_profile_fingerprint"] == candidate.profile_fingerprint
    assert (
        contract["candidate_file_sha256"] == sha256(_CANDIDATE.read_bytes()).hexdigest()
    )
    assert contract["candidate_run_fingerprint_observe"] == (candidate.run_fingerprint)
    assert contract["execution_scope"] == expected_routes
    assert contract["observe_only_scope"] == []
    assert contract["maximum_positions"] == len(candidate.assets) == 9
    assert contract["one_position_per_asset"] is True
    assert contract["prechange_bundle"] == str(_PRECHANGE_BUNDLE)
    assert (
        contract["implementation_file_count"]
        == (manifest["implementation_identity"]["file_count"])
    )
    assert (
        contract["implementation_sha256"]
        == (manifest["implementation_identity"]["sha256"])
    )


def test_v26_runbook_requires_flat_boundary_arm_and_exact_runtime_probes() -> None:
    """The repair generation must remain fail-closed and directly observable."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert '.transition_drain.status == "completed"' in text
    assert "scripts/cohort_transition_drain_archive.py" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text
    assert "--resume-transition-drain" in text
    assert "--mode live" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "numeric `L2 IMB10`" in text
    assert "numeric `HA COLOR`" in text
    assert "numeric `ORDER BLOCK`" in text
    assert "fresh causal exact-symbol book" in text
    assert "24/24" in text
    assert "all nine assets" in text
    assert "no inherited exposure" in text
    assert (
        "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml" in text
    )
    assert "automatic_restart" in text


def test_cli_skill_does_not_route_transition_to_superseded_v26() -> None:
    """Operator guidance must route through the newer source-bound candidate."""
    text = _CLI_SKILL.read_text(encoding="utf-8")

    assert "cohort-live-transition-and-rollback-v26.md" not in text
    assert "multi_asset_bidirectional_complete_portfolio_canary_v26.toml" not in text
    assert "cohort-live-transition-and-rollback-v29.md" in text
    assert (
        "multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml" in text
    )
    assert "v25 remains active until" in text


def test_v26_superseded_source_baseline_remains_internally_verified() -> None:
    """The retired v26 bundle stays verifiable without matching newer source."""
    manifest = json.loads(
        (_PRECHANGE_BUNDLE / "manifest.json").read_text(encoding="utf-8")
    )
    verified = verify_cohort_prestart_backup(_PRECHANGE_BUNDLE)

    assert verified["implementation_identity"] == manifest["implementation_identity"]
    assert verified["target_identity"]["profile_id"] == (
        "multi_asset_bidirectional_complete_portfolio_canary_v26"
    )


def _contract(text: str) -> dict[str, object]:
    """Decode the embedded JSON transition contract."""
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json")
    assert fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())
