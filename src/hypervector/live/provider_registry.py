"""The live provider registry: the one place a strategy plugs into the cohort.

Every ``[[providers]]`` row of a cohort profile names a ``strategy_id`` that
must be registered here. The registration is the provider's whole contract with
the generic engine:

* the profile loader and ``live validate`` refuse an unknown id and check the
  row against the provider's declared capability;
* the cohort poller reads the declared signal clock and builds the collector
  from the declared factory;
* startup readiness seeding replays the declared lookback.

Adding a strategy provider
--------------------------
1. Write a module (for example ``hypervector/live/<name>_provider.py``) with a
   collector that returns an ``IntentBatch`` for unseen completed bars, and a
   module-level ``ProviderRegistration`` naming its id, signal timeframe,
   readiness lookback, collector factory and ``ProviderCapability``.
2. Import that registration below and add it to ``_BUILTIN_REGISTRATIONS``.
   Every edit under ``src/`` changes the live implementation identity, so the
   next armed start needs an explicit operator go-ahead.

``register_provider`` adds a registration at runtime for code that runs before
a profile is loaded (tests register synthetic providers this way).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError
from hypervector.live.provider_registration import (
    ProviderIntentCollectorProtocol,
    ProviderRegistration,
    validate_provider_capability,
)
from hypervector.live.research_pending_market_observer import (
    RESEARCH_PENDING_MARKET_OBSERVER,
)

if TYPE_CHECKING:
    from hypervector.live.multi_asset_live_config import (
        MultiAssetLiveConfig,
        StrategyProviderConfig,
    )

# Built-in providers. A new strategy provider adds its registration here.
_BUILTIN_REGISTRATIONS: tuple[ProviderRegistration, ...] = (
    RESEARCH_PENDING_MARKET_OBSERVER,
)

_REGISTRY: dict[str, ProviderRegistration] = {
    registration.strategy_id: registration
    for registration in _BUILTIN_REGISTRATIONS
}


class UnknownProviderError(MultiAssetLiveConfigError):
    """A profile names a strategy_id that no provider registration declares."""


def register_provider(registration: ProviderRegistration) -> None:
    """Add one provider; an id already registered to another provider is refused."""
    if not isinstance(registration, ProviderRegistration):
        raise TypeError("register_provider requires a ProviderRegistration")
    existing = _REGISTRY.get(registration.strategy_id)
    if existing is not None and existing != registration:
        raise ValueError(
            f"provider strategy_id is already registered: {registration.strategy_id}"
        )
    _REGISTRY[registration.strategy_id] = registration


def registered_provider_ids() -> tuple[str, ...]:
    """Return every registered strategy_id in sorted order."""
    return tuple(sorted(_REGISTRY))


def provider_registration(strategy_id: str) -> ProviderRegistration:
    """Return one registration or refuse the unknown id."""
    registration = _REGISTRY.get(strategy_id)
    if registration is None:
        raise UnknownProviderError(
            f"provider strategy_id is not registered: {strategy_id}; add its "
            "ProviderRegistration in hypervector.live.provider_registry"
        )
    return registration


def validate_registered_provider(provider: StrategyProviderConfig) -> None:
    """Require a registered id and a profile row its capability can serve."""
    validate_provider_capability(provider, provider_registration(provider.strategy_id))


def provider_signal_timeframe(strategy_id: str) -> str:
    """Return the completed-bar clock the poller passes to this provider."""
    return provider_registration(strategy_id).signal_timeframe


def provider_readiness_lookback_minutes(strategy_id: str) -> int:
    """Return how far before activation readiness seeding replays this provider."""
    return provider_registration(strategy_id).readiness_lookback_minutes


def build_provider_collector(
    provider: StrategyProviderConfig,
    config: MultiAssetLiveConfig,
) -> ProviderIntentCollectorProtocol:
    """Build the collector declared by one validated provider row."""
    registration = provider_registration(provider.strategy_id)
    validate_provider_capability(provider, registration)
    return registration.collector_factory(provider, config)
