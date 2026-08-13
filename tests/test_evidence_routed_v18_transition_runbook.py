"""Machine-bound contract for the inactive v14-to-v18 transition."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_RUNBOOK = Path("docs/guides/cohort-live-transition-and-rollback-v18.md")
_CURRENT = Path(
    "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
)
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_evidence_routed_candidate_v18.toml"
)
_FROZEN_HYPE_SOURCE_SHA256 = (
    "3210a0f85d62a13ef8f5d99277d62ae02b496cea5200fbf897196365a48d270d"
)
_FROZEN_ETH_SOURCE_SHA256 = (
    "11f50718099be4282027a8370144312121db126ca42d821c247bc00c3bfae497"
)
_START = "<!-- cohort-transition-contract:start -->"
_END = "<!-- cohort-transition-contract:end -->"


def test_v18_runbook_binds_exact_generations_sources_and_routes() -> None:
    """No nearby profile or widened provider scope may substitute at cutover."""
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
        "hype_source_sha256": _FROZEN_HYPE_SOURCE_SHA256,
        "eth_source_sha256": _FROZEN_ETH_SOURCE_SHA256,
        "execution_scope": [
            "hulk_expansion_bidirectional_tuned_v2|BTC",
            "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
            "hype_breakout_onset_bidirectional_v1|HYPE",
        ],
        "requires_completed_transition_drain": True,
        "requires_flat_no_orders": True,
        "automatic_restart": False,
    }


def test_v18_runbook_requires_recoverable_drain_backup_and_rollback() -> None:
    """Cutover preserves active lifecycles, evidence, and rollback identity."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert '.transition_drain.status == "completed"' in text
    assert "scripts/cohort_transition_drain_archive.py" in text
    assert "scripts/cohort_prestart_backup_verify.py" in text
    assert "--resume-transition-drain" in text
    assert "--mode live" in text
    assert "--enabled --i-accept-live-risk" in text
    assert "Do not send SIGKILL" in text
    assert "Do not force-close" in text
    assert "Do not remove the transition marker manually" in text
    assert "There is no hot rollback" in text


def test_v18_runbook_acceptance_matches_exact_shared_portfolio_contract() -> None:
    """Acceptance checks the bounded routes without inventing profitability."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "$25 maximum BTC notional" in text
    assert "$25 maximum ETH notional" in text
    assert "$75 maximum HYPE notional" in text
    assert "isolated 5x" in text
    assert "both ETH directions" in text
    assert "60-bps protective stop" in text
    assert "12-hour fixed maximum hold" in text
    assert "both HYPE directions" in text
    assert "80-bps protective stop" in text
    assert "eight-hour soft deadline" in text
    assert "24-hour hard deadline" in text
    assert "maximum four simultaneous positions" in text
    assert "one position per coin" in text
    assert "SOL remains observe-only" in text
    assert "No economic result automatically changes live authority" in text
    assert "does not establish edge" in text


def test_v18_runbook_names_exact_live_and_monitor_commands() -> None:
    """The operator can reproduce deployment and read-only monitoring."""
    text = _RUNBOOK.read_text(encoding="utf-8")

    assert "multi_asset_bidirectional_evidence_routed_candidate_v18.toml" in text
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
