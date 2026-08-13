"""Exact-delta contract for the inactive SPCX Swing retirement candidate."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tomllib

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_V32 = Path(
    "configs/multi_asset_bidirectional_commodity_swing_retired_candidate_v32.toml"
)
_V33 = Path("configs/multi_asset_bidirectional_spcx_swing_retired_candidate_v33.toml")
_SWING = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
_REMOVED = (_SWING, "xyz:SPCX")


def test_v33_only_removes_spcx_swing_execution_from_v32() -> None:
    source = _raw(_V32)
    candidate = _raw(_V33)

    assert candidate["profile"].endswith("spcx_swing_retired_candidate_v33")
    source["profile"] = candidate["profile"]
    source_provider = _provider(source, _SWING)
    candidate_provider = _provider(candidate, _SWING)
    assert source_provider["execution_symbols"] == ["xyz:SP500", "xyz:SPCX"]
    assert candidate_provider["execution_symbols"] == ["xyz:SP500"]
    source_provider["execution_symbols"] = ["xyz:SP500"]

    assert source == candidate


def test_v33_preserves_observation_sides_capacity_and_all_other_authority() -> None:
    source = load_multi_asset_live_config(_V32, mode="observe")
    candidate = load_multi_asset_live_config(_V33, mode="observe")
    observed_source = _observed(source)
    observed_candidate = _observed(candidate)

    assert source.symbols == candidate.symbols
    assert candidate.maximum_positions == len(candidate.assets) == 9
    assert observed_candidate == observed_source
    assert (
        source.executable_provider_symbols - candidate.executable_provider_symbols
        == {_REMOVED}
    )
    assert len(candidate.executable_provider_symbols) == 20
    assert observed_candidate - candidate.executable_provider_symbols == {
        (
            "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
            "xyz:SNDK",
        ),
        (
            "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
            "xyz:GOLD",
        ),
        (
            "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
            "xyz:BRENTOIL",
        ),
        _REMOVED,
    }
    for provider in candidate.providers:
        assert set(provider.sides) == {"long", "short"}


def test_v33_loader_does_not_mutate_v32_profile() -> None:
    source = load_multi_asset_live_config(_V32, mode="observe")
    before = deepcopy(source)

    load_multi_asset_live_config(_V33, mode="observe")

    assert source == before


def _raw(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _provider(config: dict[str, object], strategy_id: str) -> dict[str, object]:
    providers = config["providers"]
    assert isinstance(providers, list)
    matches = [row for row in providers if row["strategy_id"] == strategy_id]
    assert len(matches) == 1
    return matches[0]


def _observed(config: MultiAssetLiveConfig) -> set[tuple[str, str]]:
    return {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }
