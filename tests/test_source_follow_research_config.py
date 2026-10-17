"""Frozen research contract for the source-follow short candidate."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tomllib

import pytest

from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile


def test_source_follow_candidate_is_explicitly_non_executable() -> None:
    path = Path("configs/research/hypervelocity_source_follow_short.toml")
    with path.open("rb") as handle:
        config = tomllib.load(handle)

    candidate = config["candidate"]
    assert candidate["runtime_promoted"] is False
    assert candidate["execution_authority"] == "none"
    assert candidate["model_authority"] == "observe"
    assert candidate["side"] == "short"
    assert candidate["long_arm_validated"] is False


def test_source_follow_candidate_freezes_evidence_and_risk_contract() -> None:
    path = Path("configs/research/hypervelocity_source_follow_short.toml")
    with path.open("rb") as handle:
        config = tomllib.load(handle)

    signal = config["signal"]
    risk = config["risk"]
    result = config["development_result"]["trade_through"]
    assert signal["source_revision"].startswith("ad15f2bd")
    assert signal["primary_regime"] == "TREND_DOWN"
    assert signal["onset_only"] is True
    assert signal["entry_ttl_seconds"] == 60
    assert signal["maximum_completed_5m_range_bps"] == 100.0
    assert risk == {
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "margin_mode": "isolated",
        "gross_margin_target_pct": 8.0,
        "maximum_positions_per_symbol": 1,
        "fixed_stop": "none",
    }
    assert result["fills"] == 20
    assert result["targets"] == 20
    assert result["liquidations"] == 0
    assert result["final_equity"] == 25_600.17224488378


@pytest.mark.evidence
def test_source_follow_candidate_artifact_hashes_are_current() -> None:
    path = Path("configs/research/hypervelocity_source_follow_short.toml")
    with path.open("rb") as handle:
        evidence = tomllib.load(handle)["evidence"]

    for prefix in ("touch", "through", "trade_through"):
        artifact = Path(evidence[f"{prefix}_artifact"])
        observed = hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert observed == evidence[f"{prefix}_sha256"]


def test_source_follow_candidate_cannot_load_as_runtime_profile() -> None:
    path = Path("configs/research/hypervelocity_source_follow_short.toml")

    with pytest.raises(ValueError, match="profile must be"):
        load_hypervelocity_profile(path)
