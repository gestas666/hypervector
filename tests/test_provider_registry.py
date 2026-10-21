"""The live provider registry: registration, capability checks and lookup."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)
from hypervector.live.provider_registration import (
    POLLER_SIGNAL_TIMEFRAMES,
    ProviderCapability,
    ProviderRegistration,
    binds_signal_anchors,
    validate_provider_capability,
)
from hypervector.live.provider_registry import (
    UnknownProviderError,
    build_provider_collector,
    provider_readiness_lookback_minutes,
    provider_registration,
    provider_signal_timeframe,
    register_provider,
    registered_provider_ids,
    validate_registered_provider,
)
from hypervector.live.research_pending_market_observer import (
    RESEARCH_PENDING_MARKET_OBSERVER,
    RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
)
from synthetic_live_providers import SYNTHETIC_REGISTRATIONS, SyntheticBodyCollector

_PROFILE = Path("tests/fixtures/profiles/cohort_base.toml")


def _factory(_provider: object, _config: object) -> SyntheticBodyCollector:
    return SyntheticBodyCollector(strategy_id="test_registry_15m", timeframe="15m")


def _registration(
    strategy_id: str = "test_registry_15m", **capability: object
) -> ProviderRegistration:
    return ProviderRegistration(
        strategy_id=strategy_id,
        signal_timeframe="15m",
        readiness_lookback_minutes=16,
        collector_factory=_factory,
        capability=ProviderCapability(**capability),  # type: ignore[arg-type]
    )


def _provider(strategy_id: str = "test_breakout_1m"):
    config = load_multi_asset_live_config(_PROFILE, mode="observe")
    return config, next(p for p in config.providers if p.strategy_id == strategy_id)


def test_src_registers_only_the_strategy_free_market_observer() -> None:
    """Without the test suite's providers (all ``test_*``), src declares one observer."""
    assert set(SYNTHETIC_REGISTRATIONS) <= set(registered_provider_ids())
    builtin = {
        strategy_id
        for strategy_id in registered_provider_ids()
        if not strategy_id.startswith("test_")
    }
    assert builtin == {RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY}
    observer = provider_registration(RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY)
    assert observer is RESEARCH_PENDING_MARKET_OBSERVER
    assert observer.capability.observer_only is True


def test_a_registered_provider_exposes_its_clock_lookback_and_collector() -> None:
    """The poller and readiness seed read only what the registration declares."""
    register_provider(_registration())
    assert "test_registry_15m" in registered_provider_ids()
    assert provider_signal_timeframe("test_registry_15m") == "15m"
    assert provider_readiness_lookback_minutes("test_registry_15m") == 16
    config, provider = _provider()
    built = build_provider_collector(provider, config)
    assert isinstance(built, SyntheticBodyCollector)
    assert built.strategy_id == "test_breakout_1m"


def test_registering_the_same_registration_twice_is_harmless() -> None:
    registration = _registration("test_registry_twice_15m")
    register_provider(registration)
    register_provider(registration)
    assert provider_registration("test_registry_twice_15m") is registration


def test_a_second_registration_for_one_id_is_refused() -> None:
    register_provider(_registration("test_registry_clash_15m"))
    with pytest.raises(ValueError, match="already registered"):
        register_provider(
            _registration("test_registry_clash_15m", sides=frozenset({"long"}))
        )


def test_register_provider_requires_a_registration() -> None:
    with pytest.raises(TypeError, match="ProviderRegistration"):
        register_provider("test_breakout_1m")  # type: ignore[arg-type]


def test_an_unknown_strategy_id_is_refused_with_its_name() -> None:
    with pytest.raises(UnknownProviderError, match="not registered: test_missing_1m"):
        provider_registration("test_missing_1m")
    assert issubclass(UnknownProviderError, MultiAssetLiveConfigError)


def test_a_profile_naming_an_unregistered_provider_does_not_load(
    tmp_path: Path,
) -> None:
    """The loader refuses an unknown id before any runtime is built."""
    text = _PROFILE.read_text(encoding="utf-8")
    assert 'strategy_id = "test_fade_1m"' in text
    profile = tmp_path / "unknown.toml"
    profile.write_text(
        text.replace('strategy_id = "test_fade_1m"', 'strategy_id = "test_fade_2m"'),
        encoding="utf-8",
    )
    with pytest.raises(MultiAssetLiveConfigError, match="not registered: test_fade_2m"):
        load_multi_asset_live_config(profile, mode="observe")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("strategy_id", " padded ", "trimmed text"),
        ("strategy_id", "", "trimmed text"),
        ("signal_timeframe", "30m", "signal_timeframe must be one of"),
        ("readiness_lookback_minutes", 0, "must be positive"),
        ("readiness_lookback_minutes", True, "must be positive"),
        ("collector_factory", None, "must be callable"),
        ("capability", "any", "ProviderCapability"),
    ],
)
def test_a_registration_the_poller_cannot_serve_is_refused(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_registration(), **{field: value})


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"symbols": frozenset()}, "symbols"),
        ({"sides": frozenset()}, "sides"),
        ({"sides": frozenset({"flat"})}, "sides"),
        ({"position_policies": frozenset({"pyramid"})}, "position policies"),
        ({"observer_only": 1}, "observer_only must be boolean"),
    ],
)
def test_an_unsatisfiable_capability_is_refused(
    values: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ProviderCapability(**values)  # type: ignore[arg-type]


def test_the_poller_serves_exactly_the_completed_bar_clocks() -> None:
    assert POLLER_SIGNAL_TIMEFRAMES == ("1m", "5m", "15m")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"timeframe": "1m"}, "reads the 15m signal clock"),
        ({"symbols": ("SOL",), "execution_symbols": ("SOL",)}, "evaluates only"),
        ({"sides": frozenset({"long", "short"})}, "emits only"),
        ({"position_policy": "flat_entry_only"}, "implements position policies"),
    ],
)
def test_capability_refuses_what_the_signal_cannot_compute(
    change: dict[str, object], message: str
) -> None:
    registration = _registration(
        "test_registry_narrow_15m",
        symbols=frozenset({"BTC"}),
        sides=frozenset({"long"}),
        position_policies=frozenset({"enter_and_close"}),
    )
    _config, provider = _provider()
    narrow = replace(
        provider,
        strategy_id="test_registry_narrow_15m",
        timeframe="15m",
        symbols=("BTC",),
        execution_symbols=("BTC",),
        sides=frozenset({"long"}),
        position_policy="enter_and_close",
        execution_side_overrides=(),
        stop_bps_overrides=(),
        sizing_overrides=(),
        directional_sizing_overrides=(),
        profit_lock_overrides=(),
    )
    validate_provider_capability(narrow, registration)
    with pytest.raises(MultiAssetLiveConfigError, match=message):
        validate_provider_capability(replace(narrow, **change), registration)


def test_an_observer_only_provider_cannot_hold_execution_symbols() -> None:
    _config, provider = _provider()
    observer = replace(
        provider,
        strategy_id=RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
        timeframe="15m",
        execution_symbols=provider.symbols[:1],
    )
    with pytest.raises(MultiAssetLiveConfigError, match="observe-only"):
        validate_registered_provider(observer)


@pytest.mark.parametrize(
    ("stop_policy", "target_policy", "stop_anchor", "target_anchor", "bound"),
    [
        ("fixed_bps", "none", False, False, True),
        ("structural_clamped_bps", "none", False, False, False),
        ("structural_clamped_bps", "none", True, False, True),
        ("fixed_bps", "absolute_anchor", False, False, False),
        ("fixed_bps", "absolute_anchor", False, True, True),
        ("fixed_bps", "fixed_bps", False, True, False),
    ],
)
def test_exits_bind_only_the_anchors_a_signal_carries(
    stop_policy: str,
    target_policy: str,
    stop_anchor: bool,
    target_anchor: bool,
    bound: bool,
) -> None:
    stops = (
        {"stop_bps": 60.0}
        if stop_policy == "fixed_bps"
        else {"minimum_stop_bps": 20.0, "maximum_stop_bps": 80.0}
    )
    targets = {"target_bps": 120.0} if target_policy == "fixed_bps" else {}
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy=stop_policy,
        target_policy=target_policy,
        maximum_hold_seconds=3_600,
        **stops,
        **targets,
    )
    assert (
        binds_signal_anchors(
            contract, stop_anchor=stop_anchor, target_anchor=target_anchor
        )
        is bound
    )
