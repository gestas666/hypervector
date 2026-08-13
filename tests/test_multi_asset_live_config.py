"""Strict configuration tests for the multi-asset bidirectional canary."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

_PROFILE = Path("configs/multi_asset_bidirectional_canary.toml")
_BREAKOUT_OBSERVER_PROFILE = Path(
    "configs/multi_asset_bidirectional_breakout_observer_v3.toml"
)
_COMPLETE_PROFILE = Path(
    "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml"
)


def test_profile_enables_four_coins_with_both_directions() -> None:
    """The production configuration cannot collapse any coin to one side."""
    config = load_multi_asset_live_config(_PROFILE, mode="observe")

    assert config.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert config.maximum_positions == 4
    assert all(asset.sides == frozenset({"long", "short"}) for asset in config.assets)
    assert {provider.strategy_id for provider in config.providers} == {
        "hulk_expansion_bidirectional_tuned_v2",
        "range_onset_bidirectional_v1",
        "hypervelocity_source_follow_bidirectional_5m_v1",
        "hype_breakout_onset_bidirectional_v1",
    }
    assert all(
        provider.sides == frozenset({"long", "short"}) for provider in config.providers
    )
    assert len(config.executable_provider_symbols) == 10
    providers = {provider.strategy_id: provider for provider in config.providers}
    _assert_provider_contracts(providers)
    sol_asset = next(asset for asset in config.assets if asset.symbol == "SOL")
    assert sol_asset.max_notional_usd == 75.0
    assert providers["hulk_expansion_bidirectional_tuned_v2"].entry_sizing(
        "SOL"
    ).as_payload() == {
        "margin_fraction": 0.03,
        "max_notional_usd": 25.0,
    }
    assert providers["range_onset_bidirectional_v1"].entry_sizing(
        "SOL"
    ).as_payload() == {
        "margin_fraction": 0.10,
        "max_notional_usd": 75.0,
    }


def test_exact_hip3_asset_namespaces_are_accepted() -> None:
    """Qualified lowercase-dex/uppercase-asset identities remain exact."""
    config = load_multi_asset_live_config(_COMPLETE_PROFILE, mode="observe")

    assert config.symbols[-5:] == (
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:GOLD",
        "xyz:BRENTOIL",
    )


def test_malformed_hip3_asset_namespace_is_rejected(tmp_path: Path) -> None:
    """A display alias cannot become an ambiguous venue execution identity."""
    text = _COMPLETE_PROFILE.read_text(encoding="utf-8").replace(
        "xyz:SP500",
        "XYZ:SP500",
    )
    profile = tmp_path / "malformed-hip3.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="venue identity"):
        load_multi_asset_live_config(profile, mode="observe")


def _assert_provider_contracts(
    providers: dict[str, StrategyProviderConfig],
) -> None:
    assert providers["hulk_expansion_bidirectional_tuned_v2"].execution_symbols == (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
    )
    assert providers["range_onset_bidirectional_v1"].execution_symbols == (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
    )
    measured = providers["hypervelocity_source_follow_bidirectional_5m_v1"]
    assert measured.symbols == ("BTC",)
    assert measured.execution_symbols == ("BTC",)
    assert measured.source_profile == Path(
        "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow.toml"
    )
    hype = providers["hype_breakout_onset_bidirectional_v1"]
    assert hype.symbols == ("HYPE",)
    assert hype.timeframe == "1m"
    assert hype.execution_symbols == ("HYPE",)
    assert hype.execution.maximum_hold_seconds == 28_800
    assert hype.execution.maximum_hold_policy == "extend_while_regime_supported"
    assert hype.execution.hard_maximum_hold_seconds == 86_400
    range_contract = providers["range_onset_bidirectional_v1"].execution
    assert range_contract.stop_bps == 60.0
    assert range_contract.maximum_hold_seconds == 172_800
    assert providers["range_onset_bidirectional_v1"].entry_context_overrides == (
        ("ETH", "dual_mtf_not_opposed"),
    )
    hulk_contract = providers["hulk_expansion_bidirectional_tuned_v2"].execution
    assert hulk_contract.target_r_multiple == 3.0


def test_staged_breakout_observer_expands_observation_without_authority() -> None:
    """The staged profile adds evidence rows without adding executable pairs."""
    config = load_multi_asset_live_config(_BREAKOUT_OBSERVER_PROFILE, mode="observe")
    observed = {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == "hype_breakout_onset_bidirectional_v1"
    )

    assert len(observed) == 13
    assert len(config.executable_provider_symbols) == 10
    assert provider.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert provider.execution_symbols == ("HYPE",)


def test_hype_breakout_provider_keeps_its_exact_source_contract(
    tmp_path: Path,
) -> None:
    """Execution authority cannot change the HYPE source clock or symbol."""
    old = (
        'strategy_id = "hype_breakout_onset_bidirectional_v1"\n'
        'symbols = ["HYPE"]\n'
        'sides = ["long", "short"]\n'
        "priority = 40\n"
        'timeframe = "1m"\n'
    )
    text = _PROFILE.read_text(encoding="utf-8").replace(
        old,
        old.replace('timeframe = "1m"', 'timeframe = "5m"'),
        1,
    )
    profile = tmp_path / "hype-wrong-clock.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="1m source timeframe"):
        load_multi_asset_live_config(profile, mode="observe")


def test_hype_breakout_can_observe_all_assets_but_execute_only_hype(
    tmp_path: Path,
) -> None:
    """Cross-asset observation cannot silently widen live execution scope."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        'strategy_id = "hype_breakout_onset_bidirectional_v1"\nsymbols = ["HYPE"]\n',
        'strategy_id = "hype_breakout_onset_bidirectional_v1"\n'
        'symbols = ["BTC", "ETH", "SOL", "HYPE"]\n',
        1,
    )
    profile = tmp_path / "breakout-observer.toml"
    profile.write_text(text, encoding="utf-8")

    config = load_multi_asset_live_config(profile, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == "hype_breakout_onset_bidirectional_v1"
    )

    assert provider.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert provider.execution_symbols == ("HYPE",)


def test_hypervelocity_source_provider_requires_its_exact_profile(
    tmp_path: Path,
) -> None:
    """The measured 5m arm cannot run without its pinned source profile."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        'source_profile = "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow.toml"\n',
        "",
        1,
    )
    profile = tmp_path / "source-profile-missing.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="requires source_profile"):
        load_multi_asset_live_config(profile, mode="observe")


def test_observe_and_disarmed_live_refuse_execution_authority() -> None:
    """Mode plus both explicit flags remain independent live boundaries."""
    observe = load_multi_asset_live_config(_PROFILE, mode="observe")
    with pytest.raises(MultiAssetLiveConfigError, match="mode is observe"):
        observe.require_live_start(credentials_present=True)

    disabled = load_multi_asset_live_config(
        _PROFILE,
        mode="live",
        accepts_live_risk=True,
    )
    with pytest.raises(MultiAssetLiveConfigError, match="--enabled"):
        disabled.require_live_start(credentials_present=True)

    unaccepted = load_multi_asset_live_config(
        _PROFILE,
        mode="live",
        enabled=True,
    )
    with pytest.raises(MultiAssetLiveConfigError, match="--i-accept-live-risk"):
        unaccepted.require_live_start(credentials_present=True)


def test_fully_armed_profile_still_requires_credentials() -> None:
    """Flags cannot create authority without configured account identity."""
    config = load_multi_asset_live_config(
        _PROFILE,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )

    with pytest.raises(MultiAssetLiveConfigError, match="credentials"):
        config.require_live_start(credentials_present=False)
    config.require_live_start(credentials_present=True)


def test_one_sided_asset_is_rejected(tmp_path: Path) -> None:
    """A configuration edit cannot reintroduce the rejected one-sided design."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        'sides = ["long", "short"]',
        'sides = ["short"]',
        1,
    )
    profile = tmp_path / "one-sided.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="both long and short"):
        load_multi_asset_live_config(profile, mode="observe")


def test_position_capacity_must_cover_enabled_asset_count(
    tmp_path: Path,
) -> None:
    """Every enabled asset must have a potential concurrent portfolio slot."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        "maximum_positions = 4",
        "maximum_positions = 3",
    )
    profile = tmp_path / "three-slots.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(
        MultiAssetLiveConfigError,
        match="must be at least enabled asset count",
    ):
        load_multi_asset_live_config(profile, mode="observe")


def test_position_capacity_can_reserve_a_future_asset_slot(tmp_path: Path) -> None:
    """Capacity above the current roster is valid without adding a fake asset."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        "maximum_positions = 4",
        "maximum_positions = 5",
    )
    profile = tmp_path / "five-slots.toml"
    profile.write_text(text, encoding="utf-8")

    config = load_multi_asset_live_config(profile, mode="observe")

    assert config.maximum_positions == 5
    assert len(config.assets) == 4


def test_provider_execution_symbols_must_be_observed_by_that_provider(
    tmp_path: Path,
) -> None:
    """A live scope cannot silently include an unobserved provider-symbol pair."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        'execution_symbols = ["BTC", "ETH", "SOL", "HYPE"]',
        'execution_symbols = ["BTC", "ETH", "SOL", "HYPE", "DOGE"]',
        1,
    )
    profile = tmp_path / "unknown-execution-symbol.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="execution_symbols"):
        load_multi_asset_live_config(profile, mode="observe")


def test_provider_execution_side_override_is_direction_specific(
    tmp_path: Path,
) -> None:
    """One provider-symbol side can observe without receiving auto authority."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        'strategy_id = "range_onset_bidirectional_v1"\n',
        'strategy_id = "range_onset_bidirectional_v1"\n'
        'execution_side_overrides = { ETH = ["long"] }\n',
        1,
    )
    profile = tmp_path / "eth-long-range.toml"
    profile.write_text(text, encoding="utf-8")

    config = load_multi_asset_live_config(profile, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == "range_onset_bidirectional_v1"
    )

    assert provider.execution_side_overrides == (("ETH", frozenset({"long"})),)
    assert (
        "range_onset_bidirectional_v1",
        "ETH",
        "long",
    ) in config.executable_provider_directions
    assert (
        "range_onset_bidirectional_v1",
        "ETH",
        "short",
    ) not in config.executable_provider_directions
    assert (
        "range_onset_bidirectional_v1",
        "SOL",
        "short",
    ) in config.executable_provider_directions


def test_provider_execution_side_override_must_be_executable(
    tmp_path: Path,
) -> None:
    """A direction override cannot silently grant a new provider-symbol pair."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        'strategy_id = "hypervelocity_source_follow_bidirectional_5m_v1"\n',
        'strategy_id = "hypervelocity_source_follow_bidirectional_5m_v1"\n'
        'execution_side_overrides = { ETH = ["long"] }\n',
        1,
    )
    profile = tmp_path / "unknown-direction-scope.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(
        MultiAssetLiveConfigError,
        match="execution_side_overrides",
    ):
        load_multi_asset_live_config(profile, mode="observe")


def test_provider_symbol_sizing_override_is_explicit_and_typed(
    tmp_path: Path,
) -> None:
    """A provider can use a narrower policy than the asset adapter ceiling."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        "sizing_overrides = { SOL = { margin_fraction = 0.10, "
        "max_notional_usd = 75.0 } }",
        "sizing_overrides = { SOL = { margin_fraction = 0.06, "
        "max_notional_usd = 20.0 } }",
        1,
    )
    profile = tmp_path / "provider-sizing.toml"
    profile.write_text(text, encoding="utf-8")

    config = load_multi_asset_live_config(profile, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == "range_onset_bidirectional_v1"
    )
    sizing = provider.entry_sizing("SOL")

    assert sizing is not None
    assert sizing.margin_fraction == pytest.approx(0.06)
    assert sizing.max_notional_usd == pytest.approx(20.0)
    assert (
        config.provider_entry_sizing[("range_onset_bidirectional_v1", "SOL")] == sizing
    )


def test_provider_directional_sizing_is_explicit_and_typed(tmp_path: Path) -> None:
    """Both sides stay executable while receiving independent notional policies."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        "sizing_overrides = { SOL = { margin_fraction = 0.10, "
        "max_notional_usd = 75.0 } }",
        "sizing_overrides = { SOL = { margin_fraction = 0.10, "
        "max_notional_usd = 75.0 } }\n"
        "directional_sizing_overrides = { SOL = { "
        "long = { margin_fraction = 0.08, max_notional_usd = 60.0 }, "
        "short = { margin_fraction = 0.02, max_notional_usd = 15.0 } } }",
        1,
    )
    profile = tmp_path / "provider-directional-sizing.toml"
    profile.write_text(text, encoding="utf-8")

    config = load_multi_asset_live_config(profile, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == "range_onset_bidirectional_v1"
    )

    assert provider.entry_sizing("SOL").max_notional_usd == pytest.approx(75.0)
    assert provider.entry_sizing("SOL", "long").max_notional_usd == pytest.approx(60.0)
    assert provider.entry_sizing("SOL", "short").max_notional_usd == pytest.approx(15.0)
    assert config.provider_directional_entry_sizing[
        ("range_onset_bidirectional_v1", "SOL", "long")
    ].margin_fraction == pytest.approx(0.08)
    assert ("range_onset_bidirectional_v1", "SOL", "short") in (
        config.executable_provider_directions
    )


def test_directional_sizing_cannot_exceed_asset_ceiling(tmp_path: Path) -> None:
    """A side-specific policy cannot bypass the venue adapter's hard cap."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        "sizing_overrides = { SOL = { margin_fraction = 0.10, "
        "max_notional_usd = 75.0 } }",
        "sizing_overrides = { SOL = { margin_fraction = 0.10, "
        "max_notional_usd = 75.0 } }\n"
        "directional_sizing_overrides = { SOL = { "
        "long = { margin_fraction = 0.08, max_notional_usd = 80.0 } } }",
        1,
    )
    profile = tmp_path / "unsafe-directional-sizing.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="directional sizing"):
        load_multi_asset_live_config(profile, mode="observe")


def test_provider_sizing_override_must_reference_execution_scope(
    tmp_path: Path,
) -> None:
    """Sizing cannot silently widen a provider's executable symbol set."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        'strategy_id = "hypervelocity_source_follow_bidirectional_5m_v1"\n',
        'strategy_id = "hypervelocity_source_follow_bidirectional_5m_v1"\n'
        "sizing_overrides = { ETH = { margin_fraction = 0.06, "
        "max_notional_usd = 20.0 } }\n",
        1,
    )
    profile = tmp_path / "sizing-outside-scope.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="sizing_overrides"):
        load_multi_asset_live_config(profile, mode="observe")


def test_provider_sizing_cap_cannot_exceed_asset_adapter_ceiling(
    tmp_path: Path,
) -> None:
    """The venue adapter remains the final configured notional authority."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        "sizing_overrides = { SOL = { margin_fraction = 0.10, "
        "max_notional_usd = 75.0 } }",
        "sizing_overrides = { SOL = { margin_fraction = 0.06, "
        "max_notional_usd = 80.0 } }",
        1,
    )
    profile = tmp_path / "sizing-over-ceiling.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="adapter ceiling"):
        load_multi_asset_live_config(profile, mode="observe")


def test_entry_context_override_rejects_unknown_policy(tmp_path: Path) -> None:
    """A misspelled entry-context rule cannot silently become permissive."""
    text = _PROFILE.read_text(encoding="utf-8").replace(
        'entry_context_overrides = { ETH = "dual_mtf_not_opposed" }',
        'entry_context_overrides = { ETH = "maybe_trending" }',
        1,
    )
    profile = tmp_path / "unknown-entry-context.toml"
    profile.write_text(text, encoding="utf-8")

    with pytest.raises(MultiAssetLiveConfigError, match="entry_context_overrides"):
        load_multi_asset_live_config(profile, mode="observe")


def test_profile_fingerprint_is_stable_across_python_hash_seeds() -> None:
    """Independent supervisor and backend processes must agree on identity."""
    program = (
        "from hypervector.live.multi_asset_live_config import "
        "load_multi_asset_live_config as load; "
        "print(load('configs/multi_asset_bidirectional_canary.toml', "
        "mode='observe').profile_fingerprint)"
    )
    fingerprints = {
        subprocess.check_output(
            [sys.executable, "-c", program],
            cwd=_PROFILE.parents[1],
            env={**os.environ, "PYTHONHASHSEED": seed},
            text=True,
        ).strip()
        for seed in ("1", "2", "3", "4")
    }

    assert len(fingerprints) == 1


def test_profile_fingerprint_is_independent_of_runtime_authority() -> None:
    """One TOML generation keeps one identity across observe and live modes."""
    observe = load_multi_asset_live_config(_PROFILE, mode="observe")
    live = load_multi_asset_live_config(
        _PROFILE,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )

    assert observe.profile_fingerprint == live.profile_fingerprint
    assert observe.run_fingerprint != live.run_fingerprint
