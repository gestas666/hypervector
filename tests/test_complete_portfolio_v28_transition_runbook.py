"""Machine-bound contract for the inactive v25-to-v28 transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v28.md")
_CURRENT = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_complete_portfolio_canary_v28.toml"
)
_JOURNAL = Path("docs/research-journal/sol-ht-breakout-transfer-v2.json")
_BUNDLE = Path(
    "data/backups/bidirectional_cohort/prestart_20260808T052126.703591Z_90285e71220a"
)
_SKILL = Path("skills/hypervector-cli/SKILL.md")
_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v28_runbook_binds_profile_route_evidence_and_backup() -> None:
    """The transition must bind the exact one-route removal and its evidence."""
    contract = _contract(_RUNBOOK.read_text(encoding="utf-8"))
    current = load_multi_asset_live_config(_CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    manifest_path = _BUNDLE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    routes = [
        f"{provider.strategy_id}|{symbol}"
        for provider in candidate.providers
        for symbol in provider.execution_symbols
    ]

    assert contract["current_run_id"] == "bidirectional-live-1786137154835"
    assert contract["current_profile_fingerprint"] == current.profile_fingerprint
    assert contract["current_file_sha256"] == _sha(_CURRENT)
    assert contract["candidate_profile_id"] == candidate.profile_id
    assert contract["candidate_profile_fingerprint"] == candidate.profile_fingerprint
    assert contract["candidate_run_fingerprint_observe"] == candidate.run_fingerprint
    assert contract["candidate_file_sha256"] == _sha(_CANDIDATE)
    assert contract["execution_scope"] == routes
    assert contract["removed_execution_scope"] == [f"{_BREAKOUT}|SOL"]
    assert contract["observe_only_scope"] == [f"{_BREAKOUT}|SOL"]
    assert contract["research_revision_id"] == (
        "8f0d4d52ed4d068dca222c1069b2b7cd5a3c27ea8b03259377cf8d44921f6561"
    )
    assert contract["research_record_sha256"] == _sha(_JOURNAL)
    assert contract["prechange_bundle"] == str(_BUNDLE)
    assert contract["prechange_manifest_sha256"] == _sha(manifest_path)
    assert (
        contract["implementation_file_count"]
        == (manifest["implementation_identity"]["file_count"])
    )
    assert (
        contract["implementation_sha256"]
        == (manifest["implementation_identity"]["sha256"])
    )


def test_v28_runbook_preserves_live_and_bidirectional_invariants() -> None:
    """Guidance must keep v25 untouched and require a flat explicit transition."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    for required in (
        "HT-Breakout",
        "23 executable",
        "24/24 observed",
        "Hulk and Range Onset",
        "both long and short",
        "TRANSITION DRAIN",
        "requires_flat_no_orders",
        "scripts/cohort_transition_drain_archive.py",
        "scripts/cohort_prestart_backup_verify.py",
        "--resume-transition-drain",
        "--enabled --i-accept-live-risk",
        "No hot rollback",
        "performance result rather than an implicit abort condition",
    ):
        assert required in text
    assert "v25 remains active" in text
    assert "does not authorize a restart" in text


def test_cli_skill_routes_next_flat_transition_to_v29() -> None:
    """Operator guidance must name the latest inactive evidence-routed profile."""
    text = _SKILL.read_text(encoding="utf-8")

    assert "cohort-live-transition-and-rollback-v29.md" in text
    assert (
        "multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml" in text
    )
    assert "six executable routes" in text
    assert "v28 is retained as a" in text
    assert "v25 remains active until" in text


def _contract(text: str) -> dict[str, object]:
    """Decode the embedded transition contract."""
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json") and fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())


def _sha(path: Path) -> str:
    """Return one file's SHA-256 identity."""
    return sha256(path.read_bytes()).hexdigest()
