"""Source-bound v51 index lifecycle contract tests."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/v51_growth_sizing_stress_20260813_v1.json"
)


@pytest.mark.evidence
@pytest.mark.parametrize(
    ("symbol", "stress_bps", "scope"),
    (
        ("xyz:SP500", 0.7711316496625931, "same_provider_xyz_spcx_proxy"),
        ("xyz:SPCX", 6.106480384658619, "exact_symbol"),
    ),
)
def test_contract_binds_exact_v51_route_without_depth_double_count(
    symbol: str, stress_bps: float, scope: str
) -> None:
    """Freeze v51 identity, exits, capped notional, and residual cost semantics."""
    module = importlib.import_module(
        "hypervector.research.v51_index_lifecycle_contract"
    )
    contract = module.load_v51_index_lifecycle_contract(_CONFIG, _STRESS, symbol)

    assert contract.profile_fingerprint == (
        "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908"
    )
    assert contract.notional_usd == pytest.approx(5_000.0)
    assert contract.nominal_residual_bps_per_side == 0.0
    assert contract.stress_extra_bps_per_side == pytest.approx(stress_bps)
    assert contract.exit_slippage_evidence_scope == scope
    assert contract.replay_config.fixed_stop_bps == pytest.approx(80.0)
    assert contract.replay_config.signal_exit_enabled is False
    assert contract.replay_config.opposite_entry_exit_enabled is True
    assert contract.replay_config.profit_lock_policy.activation_bps == 100.0
    assert contract.replay_config.profit_lock_policy.floor_bps == 40.0
    assert contract.replay_config.profit_lock_policy.trailing_giveback_bps == 80.0
    assert contract.replay_config.execution_profile_id == contract.profile_id
    assert (
        contract.replay_config.execution_profile_fingerprint
        == contract.profile_fingerprint
    )


def test_contract_rejects_a_superseded_or_changed_profile(tmp_path: Path) -> None:
    """Do not label another profile as the v51 lifecycle contract."""
    module = importlib.import_module(
        "hypervector.research.v51_index_lifecycle_contract"
    )
    changed = tmp_path / "changed.toml"
    changed.write_text(
        _CONFIG.read_text(encoding="utf-8").replace(
            "profit_lock_candidate_v51", "six_asset_candidate_v50"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="v51 profile"):
        module.load_v51_index_lifecycle_contract(changed, _STRESS, "xyz:SP500")


@pytest.mark.evidence
def test_contract_rejects_changed_route_economics(tmp_path: Path) -> None:
    """Fail closed when a source artifact changes the frozen stop contract."""
    module = importlib.import_module(
        "hypervector.research.v51_index_lifecycle_contract"
    )
    values = json.loads(_STRESS.read_text(encoding="utf-8"))
    scenario = next(
        row for row in values["scenarios"] if row["account_value_usd"] == 5_000.0
    )
    route = scenario["asset_slots"]["xyz:SP500"]["routes"][0]
    route["stop_bps"] = 81.0
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(values), encoding="utf-8")

    with pytest.raises(ValueError, match="stop"):
        module.load_v51_index_lifecycle_contract(_CONFIG, changed, "xyz:SP500")
