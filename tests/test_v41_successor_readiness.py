"""Tests for the exact v41 successor-readiness assessment."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v41_successor_readiness import (
    build_v41_successor_readiness,
)

_ROOT = Path(__file__).parents[1]
_CONFIG = _ROOT / (
    "configs/multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41.toml"
)
_PREFLIGHT = _ROOT / (
    "data/runtime/bidirectional_cohort/growth_5000_v41_preflight_20260811T1718Z.json"
)
_REPRICE = _ROOT / (
    "data/logs/research/bidirectional_cohort/"
    "v40_p99_risk_normalized_exact_reprice_20260811T0226Z_v1.json"
)
_CONCENTRATION = _ROOT / (
    "data/logs/research/bidirectional_cohort/"
    "v41_provider_family_concentration_20260811T0535Z_v1.json"
)
_RETURNS = _ROOT / (
    "data/logs/research/bidirectional_cohort/"
    "v41_return_panel_coverage_20260811T0558Z_v1.json"
)
_V39_REVIEW = _ROOT / (
    "data/logs/research/bidirectional_cohort/"
    "v39_route_portfolio_review_20260811T1715Z_v2.json"
)


def test_readiness_separates_technical_sizing_from_profit_optimality() -> None:
    """Risk-normalized sizing must not be mislabeled as proven route edge."""
    report = _build()

    assert report["candidate"]["profile_fingerprint"].startswith("c940b2ef")
    assert report["capacity"] == {
        "account_position_cap": 10,
        "configured_assets": 8,
        "maximum_simultaneous_positions": 8,
        "unused_account_slots": 2,
    }
    assert report["sizing"]["maximum_margin_fraction"] == pytest.approx(0.24)
    assert report["sizing"]["gross_notional_usd"] == pytest.approx(6000.0)
    assert report["risk"]["p99_stop_wave_loss_usd"] == pytest.approx(58.0238628)
    assert report["risk"]["covariance_weighting_status"] == "withheld"
    assert report["assessment"]["sizing_technically_coherent"] is True
    assert report["assessment"]["profit_optimality_proven"] is False
    assert report["assessment"]["transition_ready_now"] is False
    assert report["contract"]["performance_gate"] is False
    assert report["contract"]["execution_authority"] == "none"


def test_readiness_reconciles_notional_and_cluster_risk() -> None:
    """Every configured asset and concentration cluster must reconcile exactly."""
    report = _build()

    notionals = report["sizing"]["by_asset_notional_usd"]
    assert set(notionals) == {
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:BRENTOIL",
    }
    assert sum(notionals.values()) == pytest.approx(6000.0)
    clusters = report["risk"]["provider_family_clusters"]
    assert sum(row["p99_loss_usd"] for row in clusters) == pytest.approx(
        report["risk"]["p99_stop_wave_loss_usd"]
    )


def test_readiness_rejects_identity_and_notional_drift() -> None:
    """Aliased profile evidence or changed sizing cannot support the report."""
    inputs = _inputs()
    changed_identity = deepcopy(inputs)
    changed_identity["preflight"]["identity"]["candidate_profile_fingerprint"] = "wrong"
    with pytest.raises(ValueError, match="preflight candidate identity"):
        _call(changed_identity)

    changed_notional = deepcopy(inputs)
    changed_notional["preflight"]["assets"][0]["sizing"]["planned_notional_usd"] += 1.0
    with pytest.raises(ValueError, match="asset notional"):
        _call(changed_notional)

    changed_config_hash = deepcopy(inputs)
    changed_config_hash["concentration"]["evidence"]["config"]["sha256"] = "wrong"
    with pytest.raises(ValueError, match="config hash"):
        _call(changed_config_hash)


def test_readiness_requires_report_only_source_contracts() -> None:
    """No source with execution or hidden performance authority is accepted."""
    inputs = _inputs()
    inputs["v39_review"]["contract"]["performance_gate"] = True

    with pytest.raises(ValueError, match="v39 review contract"):
        _call(inputs)


def _build() -> dict[str, object]:
    return _call(_inputs())


def _call(inputs: dict[str, object]) -> dict[str, object]:
    return build_v41_successor_readiness(config=_config(), **inputs)


def _config() -> object:
    return load_multi_asset_live_config(
        _CONFIG,
        mode="observe",
        enabled=False,
        accepts_live_risk=False,
    )


def _inputs() -> dict[str, object]:
    return {
        "preflight": _read(_PREFLIGHT),
        "reprice": _read(_REPRICE),
        "concentration": _read(_CONCENTRATION),
        "return_panel": _read(_RETURNS),
        "v39_review": _read(_V39_REVIEW),
    }


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    assert isinstance(value, dict)
    return value
