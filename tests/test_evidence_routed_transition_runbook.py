"""Contract tests for the evidence-routed live-transition runbook."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback.md")
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_extension_candidate.toml"
)
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_runbook_binds_exact_evidence_routed_candidate() -> None:
    """The machine-readable handoff must match the loadable candidate bytes."""
    guide = _RUNBOOK.read_text(encoding="utf-8")
    encoded = guide.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    contract = json.loads(encoded.replace("```json", "").replace("```", ""))
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")

    assert contract["candidate_path"] == str(_CANDIDATE)
    assert contract["candidate_profile_id"] == candidate.profile_id
    assert contract["candidate_profile_fingerprint"] == candidate.profile_fingerprint
    assert (
        contract["candidate_file_sha256"] == sha256(_CANDIDATE.read_bytes()).hexdigest()
    )
    assert contract["execution_scope"] == [
        "hulk_expansion_bidirectional_tuned_v2|BTC",
        "hype_breakout_onset_bidirectional_v1|HYPE",
    ]
    assert contract["automatic_restart"] is False
    assert contract["requires_flat_no_orders"] is True
    assert (
        "multi_asset_bidirectional_range_retired_hype_fixed8_candidate.toml"
        not in guide
    )
