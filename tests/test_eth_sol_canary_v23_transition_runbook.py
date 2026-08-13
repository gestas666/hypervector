"""Machine-bound contract for the v14-to-v23 live transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v23.md")
_CURRENT = Path(
    "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
)
_CANDIDATE = Path("configs/multi_asset_bidirectional_eth_sol_canary_v23.toml")
_REPLAY = Path(
    "data/logs/research/eth_sol_shared_canary_falsification_20260807_v1.json"
)
_FROZEN_ETH_SOURCE_SHA256 = (
    "11f50718099be4282027a8370144312121db126ca42d821c247bc00c3bfae497"
)
_FROZEN_SOL_SOURCE_SHA256 = (
    "2d94ee6a757a8997e2bfc0a59de14bc2324872e3b31b16fe9b89d26db73ef0e2"
)
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v23_runbook_binds_exact_identity_routes_and_evidence() -> None:
    """The transition must reject nearby profiles or changed replay evidence."""
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
        "replay_path": str(_REPLAY),
        "replay_file_sha256": sha256(_REPLAY.read_bytes()).hexdigest(),
        "eth_source_sha256": _FROZEN_ETH_SOURCE_SHA256,
        "sol_source_sha256": _FROZEN_SOL_SOURCE_SHA256,
        "execution_scope": [
            "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
            "range_onset_bidirectional_v1|SOL",
        ],
        "observe_only_scope": [],
        "requires_completed_transition_drain": True,
        "requires_flat_no_orders": True,
        "automatic_restart": False,
    }


def test_v23_runbook_requires_safe_boundary_backup_and_explicit_arm() -> None:
    """The candidate may start only through the recoverable live procedure."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert '.transition_drain.status == "completed"' in text
    assert "scripts/cohort_transition_drain_archive.py" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text
    assert "--resume-transition-drain" in text
    assert "--mode live" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "one position per symbol" in text
    assert "No observer provider" in text
    assert "does not establish durable edge" in text
    assert "No economic result automatically changes live authority" in text


def test_v23_runbook_names_exact_live_and_monitor_commands() -> None:
    """Live launch and read-only attachment must select the frozen profile."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert text.count(str(_CANDIDATE)) >= 4
    assert "uv run python -m hypervector cohort-tui" in text
    assert "--mode monitor" in text
    assert "--mode live" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "--venue-portfolio" in text


def _contract(text: str) -> dict[str, object]:
    """Decode the embedded JSON transition contract."""
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json")
    assert fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())
