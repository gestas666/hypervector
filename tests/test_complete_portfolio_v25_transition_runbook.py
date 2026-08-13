"""Machine-bound contract for the v24-to-v25 portfolio transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v25.md")
_CURRENT = Path(
    "configs/multi_asset_bidirectional_eth_sol_full_observation_canary_v24.toml"
)
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml"
)
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v25_runbook_binds_exact_profiles_and_all_execution_routes() -> None:
    """The transition contract must cover every configured provider-symbol."""
    contract = _contract(_RUNBOOK.read_text(encoding="utf-8"))
    current = load_multi_asset_live_config(_CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    expected_routes = [
        f"{provider.strategy_id}|{symbol}"
        for provider in candidate.providers
        for symbol in provider.execution_symbols
    ]

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
    assert contract["execution_scope"] == expected_routes
    assert contract["observe_only_scope"] == []
    assert contract["maximum_positions"] == len(candidate.assets) == 9
    assert contract["one_position_per_asset"] is True


def test_v25_runbook_requires_safe_boundary_and_explicit_live_arm() -> None:
    """The complete candidate must remain fail-closed through transition."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert '.transition_drain.status == "completed"' in text
    assert "scripts/cohort_transition_drain_archive.py" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text
    assert "--resume-transition-drain" in text
    assert "--mode live" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "SETUPS 24/24 // COMPLETE" in text
    assert "all nine assets" in text
    assert "automatic_restart" in text


def _contract(text: str) -> dict[str, object]:
    """Decode the embedded JSON transition contract."""
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json")
    assert fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())
