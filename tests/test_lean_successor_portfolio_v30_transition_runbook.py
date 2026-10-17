"""Machine-bound contract for the inactive v25-to-v30 transition candidate."""

import pytest

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v30.md")
CURRENT = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
CANDIDATE = Path("configs/multi_asset_bidirectional_lean_successor_canary_v30.toml")
JOURNAL = Path("docs/research-journal/lean-successor-portfolio-v1.json")
ARTIFACT = Path(
    "data/logs/research/lean_successor_portfolio_comparison_20260809T161609Z.json"
)
START = "<!-- cohort-transition-contract:start -->"
END = "<!-- cohort-transition-contract:end -->"


@pytest.mark.evidence
def test_v30_runbook_binds_candidate_routes_and_research_identity() -> None:
    """The inactive candidate must be reconstructable without staging it."""
    contract = _contract(RUNBOOK.read_text(encoding="utf-8"))
    current = load_multi_asset_live_config(CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(CANDIDATE, mode="observe")
    routes = sorted(
        f"{provider.strategy_id}|{symbol}"
        for provider in candidate.providers
        for symbol in provider.execution_symbols
    )

    assert contract["current_profile_id"] == current.profile_id
    assert contract["current_profile_fingerprint"] == current.profile_fingerprint
    assert contract["candidate_profile_id"] == candidate.profile_id
    assert contract["candidate_profile_fingerprint"] == candidate.profile_fingerprint
    assert contract["candidate_run_fingerprint_observe"] == candidate.run_fingerprint
    assert contract["candidate_file_sha256"] == _sha(CANDIDATE)
    assert contract["execution_scope"] == routes
    assert contract["maximum_positions"] == len(candidate.assets) == 3
    assert contract["research_revision_id"] == (
        "a97034d76756d80a7ae18e6765ea2e91b2d828f331ec4ea962c5d6ed9e39c9ef"
    )
    assert contract["research_record_sha256"] == _sha(JOURNAL)
    assert contract["comparison_artifact_sha256"] == _sha(ARTIFACT)


def test_v30_runbook_is_fail_closed_until_fresh_flat_boundary() -> None:
    """Prepared files may not imply transition or live execution authority."""
    text = RUNBOOK.read_text(encoding="utf-8")
    contract = _contract(text)

    assert contract["candidate_active"] is False
    assert contract["transition_authorized"] is False
    assert contract["flat_and_order_free_verified"] is False
    assert contract["transition_readiness_snapshot"] is None
    assert contract["prechange_bundle"] is None
    for required in (
        "v25 remains active",
        "does not authorize a restart",
        "verified flat-and-order-free",
        "--enabled --i-accept-live-risk",
        "No hot rollback",
        "both long and short",
        "one position per asset",
        "performance result rather than an implicit abort condition",
    ):
        assert required in text


def _contract(text: str) -> dict[str, object]:
    """Decode the embedded transition contract."""
    raw = text.split(START, maxsplit=1)[1].split(END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json") and fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())


def _sha(path: Path) -> str:
    """Return one file's SHA-256 identity."""
    return sha256(path.read_bytes()).hexdigest()
