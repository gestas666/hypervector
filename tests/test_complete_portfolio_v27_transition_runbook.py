"""Machine-bound contract for the inactive v25-to-v27 transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.cohort_prestart_backup import verify_cohort_prestart_backup
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v27.md")
_CURRENT = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_complete_portfolio_canary_v27.toml"
)
_BUNDLE = Path(
    "data/backups/bidirectional_cohort/prestart_20260808T042806.773285Z_c671c7aaedbd"
)
_SKILL = Path("skills/hypervector-cli/SKILL.md")
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v27_runbook_binds_profiles_routes_and_verified_sources() -> None:
    """V27 must bind exact configuration, authority, and source identities."""
    contract = _contract(_RUNBOOK.read_text(encoding="utf-8"))
    current = load_multi_asset_live_config(_CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    manifest = json.loads((_BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    routes = [
        f"{provider.strategy_id}|{symbol}"
        for provider in candidate.providers
        for symbol in provider.execution_symbols
    ]
    recipe_exit_policies = {
        provider.strategy_id: provider.execution.provider_recipe_exit_policy
        for provider in candidate.providers
    }

    assert contract["current_path"] == str(_CURRENT)
    assert contract["current_profile_id"] == current.profile_id
    assert contract["current_profile_fingerprint"] == current.profile_fingerprint
    assert contract["current_file_sha256"] == sha256(_CURRENT.read_bytes()).hexdigest()
    assert contract["current_run_id"] == "bidirectional-live-1786137154835"
    assert contract["candidate_path"] == str(_CANDIDATE)
    assert contract["candidate_profile_id"] == candidate.profile_id
    assert contract["candidate_profile_fingerprint"] == candidate.profile_fingerprint
    assert (
        contract["candidate_file_sha256"] == sha256(_CANDIDATE.read_bytes()).hexdigest()
    )
    assert contract["candidate_run_fingerprint_observe"] == candidate.run_fingerprint
    assert contract["execution_scope"] == routes
    assert contract["provider_recipe_exit_policies"] == recipe_exit_policies
    assert contract["observe_only_scope"] == []
    assert contract["maximum_positions"] == len(candidate.assets) == 9
    assert contract["prechange_bundle"] == str(_BUNDLE)
    assert (
        contract["prechange_manifest_sha256"]
        == sha256((_BUNDLE / "manifest.json").read_bytes()).hexdigest()
    )
    assert (
        contract["implementation_file_count"]
        == (manifest["implementation_identity"]["file_count"])
    )
    assert (
        contract["implementation_sha256"]
        == (manifest["implementation_identity"]["sha256"])
    )
    assert contract["one_position_per_asset"] is True
    assert contract["requires_completed_transition_drain"] is True
    assert contract["requires_flat_no_orders"] is True
    assert contract["automatic_restart"] is False


def test_v27_runbook_requires_default_ignore_recipe_exit_acceptance() -> None:
    """V27 guidance must not imply authority rejected by current evidence."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    for evidence in (
        "provider_recipe_exit_policy",
        "ignore",
        "honor",
        "provider_exit_decision",
        "exit_sides",
        "exit_reason",
        "hip3_swing_ha_flip",
        "hip3_swing_alignment_loss",
        "hip3_swing_gap_recovery",
        "same entry OID, provider, symbol, and side",
        "one-bar exit",
        "no cross-provider close",
        "24/24",
        "all nine assets",
        "no inherited exposure",
        "scripts/cohort_transition_drain_archive.py",
        "scripts/cohort_prestart_backup_verify.py",
        "--resume-transition-drain",
        "--enabled --i-accept-live-risk",
        "automatic_restart",
    ):
        assert evidence in text
    assert "must not append a `provider_exit_decision`" in text
    assert "direct `honor` execution remains rejected" in text
    assert "The backend can act on" not in text
    assert "first eligible recipe exit produces exactly one durable" not in text


def test_v27_superseded_source_baseline_remains_internally_verified() -> None:
    """The retired v27 bundle stays verifiable without matching newer source."""
    manifest = json.loads((_BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    verified = verify_cohort_prestart_backup(_BUNDLE)

    assert verified["implementation_identity"] == manifest["implementation_identity"]
    assert verified["target_identity"]["profile_id"] == (
        "multi_asset_bidirectional_complete_portfolio_canary_v27"
    )


def test_cli_skill_marks_v27_as_superseded_by_v29() -> None:
    """Operator instructions cannot launch the superseded v27 candidate."""
    text = _SKILL.read_text(encoding="utf-8")

    assert "cohort-live-transition-and-rollback-v29.md" in text
    assert (
        "multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml" in text
    )
    assert "v25 remains active until" in text
    assert "six executable routes" in text
    assert "v28 is retained as a" in text


def _contract(text: str) -> dict[str, object]:
    """Decode the embedded JSON transition contract."""
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json")
    assert fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())
