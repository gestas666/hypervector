"""Per-symbol stop contracts for shared multi-symbol providers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.live.cohort_execution_contract_selection import (
    select_execution_contract,
)
from hypervector.live.multi_asset_cohort_payloads import provider_config_payload
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v43_portfolio_friction_stress import (
    build_v43_portfolio_friction_stress,
)

_PROFILE = Path("configs/multi_asset_growth_first_5000_repaired_candidate_v49.toml")
_VENUE = Path(
    "data/logs/research/bidirectional_cohort/"
    "v40_growth_sizing_stress_20260811T0200Z.json"
)
_FRICTION = Path(
    "data/logs/research/bidirectional_cohort/"
    "v46_execution_friction_stress_20260812_v1.json"
)
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/v49_growth_sizing_stress_20260812_v1.json"
)
_RANGE = "range_onset_bidirectional_v1"


def test_v49_uses_evidence_specific_range_stops_by_symbol() -> None:
    """ETH retains 60 bps while SOL uses its reconciled 80-bps contract."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    provider = next(row for row in config.providers if row.strategy_id == _RANGE)

    assert provider.execution.stop_bps == pytest.approx(60.0)
    assert provider.execution_for("ETH").stop_bps == pytest.approx(60.0)
    assert provider.execution_for("SOL").stop_bps == pytest.approx(80.0)
    assert provider_config_payload(provider)["stop_bps_overrides"] == {"SOL": 80.0}


def test_v49_runtime_contract_selection_honors_symbol_override() -> None:
    """Automatic and manual-attributed SOL entries bind the 80-bps plan."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    contracts = config.provider_execution_contracts

    eth = select_execution_contract(contracts, _RANGE, "ETH")
    sol = select_execution_contract(contracts, _RANGE, "SOL")
    manual = select_execution_contract(
        contracts,
        f"operator_override:{_RANGE}",
        "SOL",
    )

    assert eth is not None and eth.stop_bps == pytest.approx(60.0)
    assert sol is not None and sol.stop_bps == pytest.approx(80.0)
    assert manual == sol


def test_v49_stress_uses_effective_symbol_stop_contracts() -> None:
    """Sizing evidence must not collapse SOL back to the provider default."""
    friction = json.loads(_FRICTION.read_text(encoding="utf-8"))
    report = build_v43_portfolio_friction_stress(
        _PROFILE,
        venue_stress_path=_VENUE,
        execution_friction=friction["execution_friction_evidence"],
        account_values_usd=(5_000.0,),
        schema_version="test_v49_symbol_stops",
    )
    slots = report["scenarios"][0]["asset_slots"]
    eth = slots["ETH"]["routes"][0]
    sol = slots["SOL"]["routes"][0]

    assert eth["stop_bps"] == pytest.approx(60.0)
    assert sol["stop_bps"] == pytest.approx(80.0)
    assert sol["stacked_p99_stop_loss_usd"] > eth["stacked_p99_stop_loss_usd"]


def test_v49_immutable_stress_artifact_matches_repaired_contract() -> None:
    """Published $5K evidence must retain the exact symbol stops and wave loss."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    report = json.loads(_STRESS.read_text(encoding="utf-8"))
    scenario = next(
        row for row in report["scenarios"] if row["account_value_usd"] == 5_000.0
    )

    assert report["profile_id"] == config.profile_id
    assert report["profile_fingerprint"] == config.profile_fingerprint
    assert scenario["asset_slots"]["ETH"]["routes"][0]["stop_bps"] == 60.0
    assert scenario["asset_slots"]["SOL"]["routes"][0]["stop_bps"] == 80.0
    assert scenario["stacked_p99_stop_wave_loss_usd"] == pytest.approx(309.297924)
    assert scenario["stacked_p99_stop_wave_loss_pct_equity"] == pytest.approx(6.185958)
