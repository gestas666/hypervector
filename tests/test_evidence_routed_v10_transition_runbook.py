"""Machine-bound safety contract for the v10 next-flat transition."""

from __future__ import annotations

import json
from pathlib import Path

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v10.md")
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"
_PROFILE = (
    "configs/"
    "multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml"
)
_FINGERPRINT = "a7dde9ae84c18620476a7c8dc491ac12915a9f111515584bcd98e19e2265cf08"
_FILE_SHA = "aa5bf4d1b3261c7ff7defe5cf1fe6701ecac39052579553eeb53419dfbbf1197"


def test_v10_runbook_binds_exact_candidate_and_authority() -> None:
    """The operator sequence cannot silently substitute a wider profile."""
    text = _RUNBOOK.read_text(encoding="utf-8")
    payload = _contract(text)

    assert payload == {
        "candidate_path": _PROFILE,
        "candidate_profile_id": (
            "multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_v10"
        ),
        "candidate_profile_fingerprint": _FINGERPRINT,
        "candidate_file_sha256": _FILE_SHA,
        "execution_scope": [
            "hulk_expansion_bidirectional_tuned_v2|BTC",
            "hype_breakout_onset_bidirectional_v1|HYPE",
        ],
        "hype_breakout_observation_scope": ["BTC", "ETH", "SOL", "HYPE"],
        "requires_flat_no_orders": True,
        "automatic_restart": False,
    }


def test_v10_runbook_preserves_fail_closed_transition_and_recovery() -> None:
    """Legacy and drain-capable paths retain explicit independent checks."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert '.transition_drain.status == "unavailable"' in text
    assert '.transition_drain.status == "completed"' in text
    assert "--resume-transition-drain" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text
    assert "scripts/cohort_transition_drain_archive.py" in text
    assert "pgrep -af 'scripts/multi_asset_bidirectional_live.py'" in text
    assert "pgrep -af 'scripts/multi_asset_bidirectional_live_checkpoint.py'" in text
    assert "rm data/live/bidirectional_cohort/STOP" not in text
    assert "legacy_STOP_<UTC>" in text


def test_v10_runbook_launch_and_acceptance_use_exact_profile() -> None:
    """Only the unified launcher may arm the exact verified v10 identity."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert f"--config {_PROFILE}" in text
    assert f'"{_FINGERPRINT}"' in text
    assert "--mode live" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "HYPE-breakout/BTC, ETH, and SOL labeled observe-only" in text
    assert "HYPE-breakout/HYPE labeled bidirectional canary" in text
    assert "No automatic strategy promotion" in text


def _contract(text: str) -> dict[str, object]:
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json")
    assert fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())
