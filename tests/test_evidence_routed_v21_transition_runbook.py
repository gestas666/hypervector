"""Machine-bound contract for the inactive v14-to-v21 transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v21.md")
_CURRENT = Path(
    "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
)
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_evidence_routed_retest_observer_candidate_v21.toml"
)
_FROZEN_V1_SOURCE_SHA256 = (
    "3210a0f85d62a13ef8f5d99277d62ae02b496cea5200fbf897196365a48d270d"
)
_FROZEN_V2_SOURCE_SHA256 = (
    "3f02ae7051ebcc3791e97b155d7f0ea4df77870eab2ccc84c087994b60027121"
)
_FROZEN_V2_POLICY_SHA256 = (
    "cf0edd6d96fd06fc39db7e9db3d9eab80564f38f5f75976f0703a9a4207fc189"
)
_FROZEN_ETH_SOURCE_SHA256 = (
    "11f50718099be4282027a8370144312121db126ca42d821c247bc00c3bfae497"
)
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v21_runbook_binds_exact_identity_routes_and_observer() -> None:
    """The transition must reject nearby profiles and widened v2 authority."""
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
        "v1_source_sha256": _FROZEN_V1_SOURCE_SHA256,
        "v2_source_sha256": _FROZEN_V2_SOURCE_SHA256,
        "v2_policy_sha256": _FROZEN_V2_POLICY_SHA256,
        "eth_source_sha256": _FROZEN_ETH_SOURCE_SHA256,
        "execution_scope": [
            "hulk_expansion_bidirectional_tuned_v2|BTC",
            "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
            "hype_breakout_onset_bidirectional_v1|HYPE",
        ],
        "retest_observe_only_scope": ["BTC", "ETH", "SOL", "HYPE"],
        "requires_completed_transition_drain": True,
        "requires_flat_no_orders": True,
        "automatic_restart": False,
    }


def test_v21_runbook_requires_safe_boundary_backup_and_explicit_arm() -> None:
    """The candidate may start only through the recoverable live procedure."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert '.transition_drain.status == "completed"' in text
    assert "scripts/cohort_transition_drain_archive.py" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text
    assert "--resume-transition-drain" in text
    assert "--mode live" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "one position per coin" in text
    assert "Retest v2 remains observe-only" in text
    assert "does not establish edge" in text
    assert "No economic result automatically changes live authority" in text


def test_v21_runbook_names_exact_live_and_monitor_commands() -> None:
    """Launch and independent monitoring must select the frozen v21 profile."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert text.count(str(_CANDIDATE)) >= 4
    assert "uv run python -m hypervector cohort-tui" in text
    assert "--mode monitor" in text
    assert "--mode live" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "--eligible-policy-forward" in text


def _contract(text: str) -> dict[str, object]:
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    fenced = raw.strip()
    assert fenced.startswith("```json")
    assert fenced.endswith("```")
    return json.loads(fenced.removeprefix("```json").removesuffix("```").strip())
