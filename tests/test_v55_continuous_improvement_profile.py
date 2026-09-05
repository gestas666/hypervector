"""Exact identity contract for the v55 continuous-improvement feed."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_ROOT = Path(__file__).parents[1]
_CONFIG = _ROOT / "configs/multi_asset_growth_first_5000_spcx_cash_open_v55.toml"
_OVERRIDES = _ROOT / "configs/research/cohort_improvement_decision_overrides_v55.json"
_SCRIPT = _ROOT / "scripts/cohort_improvement_monitor.py"
_ROUTES = {
    "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX",
    "hulk_expansion_short_robust_v3|BTC",
    "hype_breakout_compression_alignment_bidirectional_v2|HYPE",
    "liquidity_sweep_long_1h_stop60_target60_v2|BTC",
}


def test_v55_override_is_exact_report_only_and_requires_new_approval() -> None:
    """The feed must describe v55 without inheriting stale live authority."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    payload = json.loads(_OVERRIDES.read_text())

    assert payload["source_profile_id"] == config.profile_id
    assert payload["source_profile_fingerprint"] == config.profile_fingerprint
    assert set(payload["routes"]) == _ROUTES
    assert payload["change_proposals"] == []
    assert payload.get("standing_live_change_approval") is None
    assert payload["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def test_v55_override_evidence_is_immutable_and_loadable() -> None:
    """Every v55 decision source must reconcile before digest publication."""
    spec = spec_from_file_location("v55_improvement_monitor", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load cohort improvement monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    payload, raw = module._load_decision_overrides(_OVERRIDES)

    assert raw == _OVERRIDES.read_bytes()
    assert len(payload["evidence"]) == 10
    active = {row["hypothesis_id"]: row for row in payload["active_hypotheses"]}
    assert active["v55-first-spcx-live-lifecycle-v1"]["status"] == "being_tested"
    assert active["v55-first-spcx-live-lifecycle-v1"]["execution_effect"] == (
        "report_only"
    )


def test_v55_override_preserves_no_relaxation_decisions() -> None:
    """Zero trades cannot silently reopen rejected BTC/HYPE relaxations."""
    payload = json.loads(_OVERRIDES.read_text())
    decisions = {row["hypothesis_id"]: row for row in payload["hypothesis_decisions"]}

    assert decisions["v55-hype-onset-relaxation-v1"]["status"] == "rejected"
    assert decisions["v55-btc-sweep-relaxation-v1"]["status"] == "rejected"
    assert decisions["v55-eth-pullback-first-forward-v1"]["status"] == "rejected"
    assert all(row.get("proposed_live_change") is None for row in decisions.values())
