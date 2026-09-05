"""SNDK v4 candidate wiring preserves the frozen portfolio and risk contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from hypervector.live.hip3_fresh15_journal_provider import (
    Hip3Fresh15JournalCollector,
    default_index_fresh15_journals,
)
from hypervector.live.hip3_breakout_shadow_specs import SNDK_SHADOW_SPEC
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_route_contract_validation import (
    validate_reused_route_contract,
)
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.multi_asset_strategy_evidence import strategy_research_evidence
from hypervector.live.cohort_tui_commands import index_observer_dependency_command

_BASELINE = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml"
)
_PRIOR = "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3"
_CANDIDATE = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_sndk_durable_onset_candidate_v87.toml"
)


def _candidate(tmp_path: Path) -> Path:
    path = tmp_path / "candidate.toml"
    path.write_text(_BASELINE.read_text().replace(_PRIOR, SNDK_SHADOW_SPEC.provider_id))
    return path


def test_candidate_changes_only_sndk_signal_identity(tmp_path: Path) -> None:
    """No asset leverage, cap, side or lifecycle rule changes during correction."""
    old = load_multi_asset_live_config(_BASELINE, mode="observe")
    new = load_multi_asset_live_config(_candidate(tmp_path), mode="observe")
    assert new.assets == old.assets
    for prior, candidate in zip(old.providers, new.providers, strict=True):
        expected = (
            replace(prior, strategy_id=SNDK_SHADOW_SPEC.provider_id)
            if prior.strategy_id == _PRIOR
            else prior
        )
        assert candidate == expected
    provider = next(
        row for row in new.providers if row.strategy_id == SNDK_SHADOW_SPEC.provider_id
    )
    assert provider.executable_sides("xyz:SNDK") == frozenset({"short"})
    assert isinstance(
        build_default_collector(provider, new, tmp_path), Hip3Fresh15JournalCollector
    )
    assert set(default_index_fresh15_journals()) == {"xyz:SP500", "xyz:SPCX"}


@pytest.mark.parametrize("defect", ["stop", "hold", "long"])
def test_v4_identity_rejects_unversioned_execution_drift(
    tmp_path: Path, defect: str
) -> None:
    """An onset correction cannot hide a changed stop, hold or executable side."""
    config = load_multi_asset_live_config(_candidate(tmp_path), mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == SNDK_SHADOW_SPEC.provider_id
    )
    if defect == "stop":
        provider = replace(
            provider, execution=replace(provider.execution, stop_bps=100)
        )
    elif defect == "hold":
        provider = replace(
            provider, execution=replace(provider.execution, maximum_hold_seconds=3600)
        )
    else:
        provider = replace(
            provider, execution_side_overrides=(("xyz:SNDK", frozenset({"long"})),)
        )
    with pytest.raises(MultiAssetLiveConfigError, match="SNDK v4"):
        validate_reused_route_contract(provider)


def test_observer_rejects_execution_flags_without_starting() -> None:
    """The standalone source collector cannot be armed as an order client."""
    result = subprocess.run(
        [sys.executable, "scripts/sndk_hip3_breakout_shadow_observe.py", "--enabled"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "unrecognized arguments: --enabled" in result.stderr


def test_published_candidate_keeps_risk_and_requires_its_own_approval() -> None:
    """The reviewable candidate cannot inherit the prior live transition approval."""
    baseline = load_multi_asset_live_config(_BASELINE, mode="observe")
    candidate = load_multi_asset_live_config(_CANDIDATE, mode="observe")
    assert (
        tuple(
            replace(asset, parent_profile_id=baseline.profile_id)
            for asset in candidate.assets
        )
        == baseline.assets
    )
    assert candidate.profile_id != baseline.profile_id
    assert candidate.transition_approval != baseline.transition_approval
    assert candidate.transition_approval is not None
    assert not candidate.transition_approval.exists()
    command = index_observer_dependency_command(candidate)
    assert command is not None
    assert command[1] == "scripts/hip3_pressure_dependency_group.py"
    assert command[-1] == str(candidate.source_path)


def test_tui_distinguishes_confirmed_defect_from_unproven_correction() -> None:
    """A technical correction cannot inherit predecessor profitability evidence."""
    prior = strategy_research_evidence(_PRIOR, "xyz:SNDK").as_payload()
    corrected = strategy_research_evidence(
        SNDK_SHADOW_SPEC.provider_id, "xyz:SNDK"
    ).as_payload()
    assert "discrepancy" in str(prior)
    assert "economics_pending" in str(corrected)
    assert "profit" in str(corrected)
