"""Machine-bound contract for the inactive v25-to-v29 transition."""

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v29.md")
CURRENT = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
CANDIDATE = Path(
    "configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml"
)
JOURNAL = Path("docs/research-journal/evidence-selected-portfolio-v29-v6.json")
COMMON_WINDOW = Path(
    "data/logs/research/"
    "evidence_selected_portfolio_v29_common_window_20260808T080301Z.json"
)
TRANSITION_SNAPSHOT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v25_transition_readiness_bidirectional-live-1786182011216_"
    "20260808T162644Z.json"
)
BUNDLE = Path(
    "data/backups/bidirectional_cohort/prestart_20260808T163708.093622Z_d1f4cd3b0319"
)
SKILL = Path("skills/hypervector-cli/SKILL.md")
START = "<!-- cohort-transition-contract:start -->"
END = "<!-- cohort-transition-contract:end -->"


def test_v29_runbook_binds_exact_profile_routes_evidence_and_backup() -> None:
    """The transition must be reconstructable from immutable identities."""
    contract = _contract(RUNBOOK.read_text(encoding="utf-8"))
    current = load_multi_asset_live_config(CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(CANDIDATE, mode="observe")
    manifest_path = BUNDLE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = json.loads(TRANSITION_SNAPSHOT.read_text(encoding="utf-8"))
    routes = [
        f"{provider.strategy_id}|{symbol}"
        for provider in candidate.providers
        for symbol in provider.execution_symbols
    ]

    assert contract["current_run_id"] == "bidirectional-live-1786182011216"
    assert contract["current_profile_fingerprint"] == current.profile_fingerprint
    assert contract["current_file_sha256"] == _sha(CURRENT)
    assert contract["candidate_profile_id"] == candidate.profile_id
    assert contract["candidate_profile_fingerprint"] == candidate.profile_fingerprint
    assert contract["candidate_run_fingerprint_observe"] == candidate.run_fingerprint
    assert contract["candidate_file_sha256"] == _sha(CANDIDATE)
    assert contract["execution_scope"] == routes
    assert contract["observe_only_scope"] == []
    assert contract["research_revision_id"] == (
        "48065e346de21ffb45e7d58de7e4c2de4173966755480214283e3db16805321e"
    )
    assert contract["research_record"] == str(JOURNAL)
    assert contract["research_record_sha256"] == _sha(JOURNAL)
    assert contract["common_window_evidence"] == str(COMMON_WINDOW)
    assert contract["common_window_evidence_sha256"] == _sha(COMMON_WINDOW)
    assert contract["checkpoint_snapshot_evidence"] == str(TRANSITION_SNAPSHOT)
    assert contract["checkpoint_snapshot_evidence_sha256"] == _sha(TRANSITION_SNAPSHOT)
    assert snapshot["lifecycle"]["state"] == "running_consistent"
    assert snapshot["audit"]["run"]["run_id"] == contract["current_run_id"]
    assert snapshot["audit"]["health"]["faults"] == 0
    assert sorted(
        symbol
        for symbol, health in snapshot["audit"]["health"]["assets"].items()
        if health["final_state"] == "OPEN" and health["protected_if_open"]
    ) == ["BTC", "SOL", "xyz:GOLD", "xyz:SPCX"]
    assert contract["prechange_bundle"] == str(BUNDLE)
    assert contract["prechange_manifest_sha256"] == _sha(manifest_path)
    assert (
        contract["implementation_file_count"]
        == (manifest["implementation_identity"]["file_count"])
    )
    assert (
        contract["implementation_sha256"]
        == (manifest["implementation_identity"]["sha256"])
    )
    assert contract["maximum_positions"] == len(candidate.assets) == 5


def test_v29_runbook_preserves_current_protection_and_explicit_authority() -> None:
    """No candidate artifact may hot-patch or implicitly replace active v25."""
    text = RUNBOOK.read_text(encoding="utf-8")

    for required in (
        "v25 remains active",
        "BTC, SOL, xyz:GOLD, and xyz:SPCX",
        "protected",
        "does not authorize a restart",
        "TRANSITION DRAIN",
        "requires_flat_no_orders",
        "scripts/cohort_transition_drain_archive.py",
        "--resume-transition-drain",
        "--enabled --i-accept-live-risk",
        "No hot rollback",
        "six executable routes",
        "both long and short",
        "performance result rather than an implicit abort condition",
        "revision 4",
        "560 accepted",
        "+12.19%",
        "PF 1.51",
        "+11.06%",
        "PF 1.45",
        "SOL Range Onset",
        "SP500 breakout pressure",
        "GOLD Swing/HA",
        "winner concentration",
        "sealed HIP-3 holdout was not accessed",
        "revision 5",
        "22.36-day common entry window",
        "97 accepted",
        "+3.30%",
        "98 accepted",
        "+2.73%",
        "SPCX Swing/HA",
        "ETH precompression pullback",
        "two SOL Range Onset longs",
        "no SOL Range Onset shorts",
        "revision 6",
        "provider_metric_telemetry_missing",
        "numeric pressure_age_seconds",
        "numeric imbalance_10",
        "causal in-window book",
        "does not backfill historical gaps",
    ):
        assert required in text


def test_cli_skill_names_v29_as_the_latest_inactive_candidate() -> None:
    """Operator guidance must stop pointing at the rejected v28 profile."""
    text = SKILL.read_text(encoding="utf-8")

    assert "cohort-live-transition-and-rollback-v29.md" in text
    assert CANDIDATE.name in text
    assert "six executable routes" in text
    assert "v25 remains active until" in text


def _contract(text: str) -> dict[str, object]:
    """Decode the embedded transition contract."""
    raw = text.split(START, maxsplit=1)[1].split(END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json") and fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())


def _sha(path: Path) -> str:
    """Return one file's SHA-256 identity."""
    return sha256(path.read_bytes()).hexdigest()
