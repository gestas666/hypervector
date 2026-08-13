"""Machine-bound safety contract for the v11-to-v14 transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v14.md")
_CURRENT = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml"
)
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
)
_FROZEN_BREAKOUT_SOURCE_SHA256 = (
    "3210a0f85d62a13ef8f5d99277d62ae02b496cea5200fbf897196365a48d270d"
)
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v14_runbook_binds_exact_generations_and_execution_scope() -> None:
    """The runbook cannot silently substitute or widen either generation."""
    text = _RUNBOOK.read_text(encoding="utf-8")
    contract = _contract(text)
    current = load_multi_asset_live_config(_CURRENT, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")

    assert contract == {
        "current_path": str(_CURRENT),
        "current_profile_id": current.profile_id,
        "current_profile_fingerprint": current.profile_fingerprint,
        "current_file_sha256": sha256(_CURRENT.read_bytes()).hexdigest(),
        "candidate_path": str(_CANDIDATE),
        "candidate_profile_id": candidate.profile_id,
        "candidate_profile_fingerprint": candidate.profile_fingerprint,
        "candidate_file_sha256": sha256(_CANDIDATE.read_bytes()).hexdigest(),
        "breakout_source_sha256": _FROZEN_BREAKOUT_SOURCE_SHA256,
        "execution_scope": [
            "hulk_expansion_bidirectional_tuned_v2|BTC",
            "hype_breakout_onset_bidirectional_v1|BTC",
            "hype_breakout_onset_bidirectional_v1|ETH",
            "hype_breakout_onset_bidirectional_v1|SOL",
            "hype_breakout_onset_bidirectional_v1|HYPE",
        ],
        "requires_completed_transition_drain": True,
        "requires_flat_no_orders": True,
        "automatic_restart": False,
    }


def test_v14_runbook_requires_recoverable_drain_backup_and_rollback() -> None:
    """Cutover and rollback preserve current lifecycles and durable evidence."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert '.transition_drain.status == "completed"' in text
    assert "scripts/cohort_transition_drain_archive.py" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text
    assert "--resume-transition-drain" in text
    assert "--mode live" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "Do not send SIGKILL" in text
    assert "rm data/live/bidirectional_cohort/transition_drain.json" not in text
    assert "There is no hot rollback" in text


def test_v14_runbook_acceptance_matches_all_asset_breakout_contract() -> None:
    """Acceptance verifies all four breakout routes and shared-account limits."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "$25 BTC maximum notional" in text
    assert "$25 ETH maximum notional" in text
    assert "$75 SOL maximum notional" in text
    assert "$75 HYPE maximum notional" in text
    assert "isolated 5x" in text
    assert "80-bps protective stop" in text
    assert "both long and short" in text
    assert "maximum four simultaneous positions" in text
    assert "one position per coin" in text
    assert "does not establish edge" in text


def _contract(text: str) -> dict[str, object]:
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json")
    assert fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())
