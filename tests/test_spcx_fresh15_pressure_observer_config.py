"""Authority and identity tests for the corrected SPCX pressure observer."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.hip3_cohort_providers import Hip3BreakoutPressureCollector
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_strategy_evidence import strategy_evidence_payloads

_PROFILE = Path("tests/fixtures/profiles/index_fresh15_pressure.toml")
_STRATEGY = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2"


def test_spcx_pressure_observer_is_exact_and_execution_incapable() -> None:
    """Corrected index signals are collected without order authority."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    provider = config.providers[0]

    assert config.profile_id == "fixture_index_fresh15_pressure"
    assert config.symbols == ("xyz:SP500", "xyz:SPCX")
    assert config.maximum_positions == 2
    assert config.executable_provider_symbols == frozenset()
    assert config.cohort_ledger == Path(
        "data/observe/index_fresh15_pressure_v2/decisions.jsonl"
    )
    assert provider.strategy_id == _STRATEGY
    assert provider.symbols == ("xyz:SP500", "xyz:SPCX")
    assert provider.sides == frozenset({"long", "short"})
    assert provider.execution_symbols == ()


def test_spcx_pressure_observer_uses_fresh15_collector_and_evidence() -> None:
    """Factory and telemetry retain the distinct repaired route identity."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    collector = build_default_collector(config.providers[0], config, Path("unused"))
    evidence = {
        row["symbol"]: row for row in strategy_evidence_payloads(config.providers)
    }

    assert isinstance(collector, Hip3BreakoutPressureCollector)
    assert set(evidence) == {"xyz:SP500", "xyz:SPCX"}
    assert all(row["strategy_id"] == _STRATEGY for row in evidence.values())
    assert all(
        row["research_state"] == "unreviewed_exact_mapping" for row in evidence.values()
    )
    assert all(row["execution_effect"] == "report_only" for row in evidence.values())


def test_spcx_pressure_observer_refuses_live_authority() -> None:
    """Explicit arming flags cannot turn the observer into an order route."""
    with pytest.raises(
        MultiAssetLiveConfigError,
        match="at least one explicit provider execution symbol",
    ):
        load_multi_asset_live_config(
            _PROFILE,
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        )
