"""Direction-specific provider profit-lock configuration and binding."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live.cohort_execution_contract_selection import (
    select_execution_contract,
)
from hypervector.live.multi_asset_cohort_payloads import provider_config_payload
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)

_PROFILE = Path("tests/fixtures/profiles/four_asset_mixed_sides.toml")
_HYPE = "test_squeeze_1m"
_OVERRIDES = (
    "profit_lock_overrides = { HYPE = { long = { policy = "
    '"completed_bar_trailing", activation_bps = 25.0, floor_bps = 8.0, '
    'giveback_bps = 6.0 }, short = { policy = "none" } } }\n'
)


def _profile_with_overrides(tmp_path: Path, overrides: str = _OVERRIDES) -> Path:
    text = _PROFILE.read_text(encoding="utf-8")
    anchor = 'execution_symbols = ["HYPE"]\n'
    profile = tmp_path / "directional-profit-lock.toml"
    profile.write_text(text.replace(anchor, anchor + overrides, 1), encoding="utf-8")
    return profile


def test_directional_profit_lock_override_is_exact_and_visible(tmp_path: Path) -> None:
    """A long-only lock must not leak into the short execution contract."""
    config = load_multi_asset_live_config(
        _profile_with_overrides(tmp_path), mode="observe"
    )
    provider = next(row for row in config.providers if row.strategy_id == _HYPE)
    long = provider.execution_for("HYPE", "long")
    short = provider.execution_for("HYPE", "short")

    assert long.profit_lock_policy == "completed_bar_trailing"
    assert long.profit_lock_activation_bps == pytest.approx(25.0)
    assert long.profit_lock_floor_bps == pytest.approx(8.0)
    assert long.profit_lock_giveback_bps == pytest.approx(6.0)
    assert short.profit_lock_policy == "none"
    assert provider.execution.profit_lock_policy == "none"
    assert provider_config_payload(provider)["profit_lock_overrides"] == {
        "HYPE": {
            "long": {
                "policy": "completed_bar_trailing",
                "activation_bps": 25.0,
                "floor_bps": 8.0,
                "giveback_bps": 6.0,
            },
            "short": {"policy": "none"},
        }
    }


def test_runtime_selection_prefers_direction_then_symbol_then_provider(
    tmp_path: Path,
) -> None:
    """Automatic and operator-attributed entries bind the exact side contract."""
    config = load_multi_asset_live_config(
        _profile_with_overrides(tmp_path), mode="observe"
    )
    contracts = config.provider_execution_contracts

    long = select_execution_contract(contracts, _HYPE, "HYPE", "long")
    manual = select_execution_contract(
        contracts, f"operator_override:{_HYPE}", "HYPE", "long"
    )
    short = select_execution_contract(contracts, _HYPE, "HYPE", "short")

    assert long is not None and long.profit_lock_policy == "completed_bar_trailing"
    assert manual == long
    assert short is not None and short.profit_lock_policy == "none"


def test_profit_lock_override_cannot_exceed_execution_scope(tmp_path: Path) -> None:
    """A side or symbol without live authority cannot acquire an exit override."""
    invalid = _OVERRIDES.replace("HYPE =", "ETH =")

    with pytest.raises(MultiAssetLiveConfigError, match="profit_lock_overrides"):
        load_multi_asset_live_config(
            _profile_with_overrides(tmp_path, invalid), mode="observe"
        )
