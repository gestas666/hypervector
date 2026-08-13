"""Exact-delta contract for the inactive all-live v35 successor."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tomllib

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_V34 = Path("configs/multi_asset_bidirectional_route_hardening_canary_v34.toml")
_V35 = Path("configs/multi_asset_bidirectional_all_live_canary_v35.toml")


def test_v35_changes_only_capacity_profile_and_execution_authority() -> None:
    """Every observed route becomes executable without changing its contract."""
    source = _raw(_V34)
    candidate = _raw(_V35)

    source["profile"] = candidate["profile"]
    source["maximum_positions"] = 10
    for provider in _providers(source):
        provider["execution_symbols"] = provider["symbols"]

    assert source == candidate


def test_v35_executes_every_observed_route_in_both_directions() -> None:
    """The requested successor has no observe-only provider/asset pair."""
    config = load_multi_asset_live_config(_V35, mode="observe")
    observed = _observed(config)

    assert config.maximum_positions == 10
    assert len(config.assets) == 9
    assert len(observed) == 24
    assert config.executable_provider_symbols == observed
    for provider in config.providers:
        assert provider.execution_symbols == provider.symbols
        assert provider.sides == frozenset({"long", "short"})


def test_v35_preserves_v34_risk_sizing_and_eth_context() -> None:
    """All-live authority must not smuggle in a capital-sizing change."""
    source = load_multi_asset_live_config(_V34, mode="observe")
    candidate = load_multi_asset_live_config(_V35, mode="observe")

    assert _raw(_V35)["assets"] == _raw(_V34)["assets"]
    assert source.maximum_positions == 9
    assert candidate.maximum_positions == 10
    source_range = next(
        provider
        for provider in source.providers
        if provider.strategy_id == "range_onset_bidirectional_v1"
    )
    candidate_range = next(
        provider
        for provider in candidate.providers
        if provider.strategy_id == "range_onset_bidirectional_v1"
    )
    assert candidate_range.entry_context_overrides == (("ETH", "dual_mtf_not_opposed"),)
    assert candidate_range.execution == source_range.execution


def test_v35_loader_does_not_mutate_v34_profile() -> None:
    """Loading the successor preserves the prior rollback candidate."""
    source = load_multi_asset_live_config(_V34, mode="observe")
    before = deepcopy(source)

    load_multi_asset_live_config(_V35, mode="observe")

    assert source == before


def _raw(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _providers(config: dict[str, object]) -> list[dict[str, object]]:
    providers = config["providers"]
    assert isinstance(providers, list)
    return providers


def _observed(config: MultiAssetLiveConfig) -> frozenset[tuple[str, str]]:
    return frozenset(
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    )
