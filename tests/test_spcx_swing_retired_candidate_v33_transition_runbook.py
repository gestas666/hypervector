"""Machine-bound contract for the inactive v25-to-v33 transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v33.md")
_CURRENT = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_spcx_swing_retired_candidate_v33.toml"
)
_JOURNAL = Path("docs/research-journal/hip3-route-authority-pruning-v4.json")
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v33_runbook_binds_exact_authority_and_evidence() -> None:
    contract = _contract(_RUNBOOK.read_text(encoding="utf-8"))
    current = load_multi_asset_live_config(_CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    observed = {
        (provider.strategy_id, symbol)
        for provider in candidate.providers
        for symbol in provider.symbols
    }

    assert contract["current_profile_fingerprint"] == current.profile_fingerprint
    assert contract["candidate_profile_fingerprint"] == candidate.profile_fingerprint
    assert contract["candidate_run_fingerprint_observe"] == candidate.run_fingerprint
    assert contract["current_file_sha256"] == _sha(_CURRENT)
    assert contract["candidate_file_sha256"] == _sha(_CANDIDATE)
    assert contract["research_record_sha256"] == _sha(_JOURNAL)
    assert contract["research_revision_id"] == (
        "2bf4678b317b35e25f050393555467ee49ddb87efe80c1fb925c053e303ca8a3"
    )
    assert contract["execution_scope"] == _routes(candidate.executable_provider_symbols)
    assert contract["observe_only_scope"] == _routes(
        observed - candidate.executable_provider_symbols
    )
    assert len(contract["execution_scope"]) == 20
    assert len(contract["observe_only_scope"]) == 4
    assert contract["maximum_positions"] == len(candidate.assets) == 9


def test_v33_runbook_is_inactive_and_requires_exact_acceptance() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
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
    for required in (
        "v25 remains active",
        "v32 is superseded",
        "does not authorize a restart",
        'transition_drain.status == "completed"',
        "scripts/cohort_transition_drain_archive.py",
        "scripts/cohort_prestart_backup_verify.py",
        "--resume-transition-drain",
        "--enabled --i-accept-live-risk",
        "No hot rollback",
        "both long and short",
        "one position per asset",
        "scripts/v33_acceptance.py",
        "scripts/v33_route_forward_monitor.py --once",
        "v33_route_material_changes.jsonl",
        "v33_poststart_acceptance_v1",
        "v33_raw_ledger_acceptance_v1",
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
