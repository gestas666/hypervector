"""Nautilus simulated-venue configuration for Hypervelocity event tapes.

This module only enables features exposed by the installed ``BacktestEngine``.
Hyperliquid-specific isolated liquidation is deliberately handled separately.
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import (
    FillModel,
    LatencyModel,
    MakerTakerFeeModel,
    StandardMarginModel,
)
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import (
    AccountType,
    BookType,
    OmsType,
    OtoTriggerMode,
)
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

_NANOS_PER_MILLISECOND = 1_000_000
_VENUE = "HYPERLIQUID"


class VenueRegistrar(Protocol):
    """Small structural boundary needed to register a simulated venue."""

    def add_venue(self, **kwargs: object) -> None:
        """Register one venue using Nautilus-compatible keyword arguments."""


@dataclass(frozen=True)
class HypervelocitySimulationConfig:
    """Deterministic execution-friction settings for an L2 event replay."""

    submit_latency_ms: int = 50
    cancel_latency_ms: int = 50
    update_latency_ms: int = 50
    maker_fill_probability: float = 1.0
    slippage_probability: float = 0.0
    random_seed: int = 7
    default_leverage: int = 30

    def __post_init__(self) -> None:
        """Reject settings Nautilus cannot interpret safely."""
        _nonnegative_int(self.submit_latency_ms, "submit_latency_ms")
        _nonnegative_int(self.cancel_latency_ms, "cancel_latency_ms")
        _nonnegative_int(self.update_latency_ms, "update_latency_ms")
        _probability(self.maker_fill_probability, "maker_fill_probability")
        _probability(self.slippage_probability, "slippage_probability")
        if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
            raise TypeError("random_seed must be an integer")
        if self.default_leverage <= 0:
            raise ValueError("default_leverage must be positive")


@dataclass(frozen=True)
class NautilusSimulationCapabilities:
    """Features empirically exposed by the installed Nautilus engine API."""

    post_only_rejection: bool
    submit_cancel_latency: bool
    per_level_liquidity: bool
    queue_position: bool
    partial_oto_release: bool
    proportional_target_resize: bool
    native_liquidation: bool
    proportional_target_detail: str
    native_liquidation_detail: str


def build_hypervelocity_venue(
    engine: VenueRegistrar,
    *,
    init_cash: float,
    config: HypervelocitySimulationConfig | None = None,
    venue: str = _VENUE,
) -> None:
    """Register a deterministic L2 simulated venue for Hypervelocity.

    Bar execution stays off because this path requires archived Hyperliquid
    L2/trade events. The existing bar-only runner remains a separate,
    lower-fidelity diagnostic.
    """
    if not math.isfinite(init_cash) or init_cash <= 0.0:
        raise ValueError("init_cash must be finite and positive")
    settings = config or HypervelocitySimulationConfig()
    latency = _latency_model(settings)
    fill = FillModel(
        prob_fill_on_limit=settings.maker_fill_probability,
        prob_slippage=settings.slippage_probability,
        random_seed=settings.random_seed,
    )
    engine.add_venue(
        venue=Venue(venue),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(init_cash, USDT)],
        base_currency=USDT,
        default_leverage=Decimal(settings.default_leverage),
        margin_model=StandardMarginModel(),
        fill_model=fill,
        fee_model=MakerTakerFeeModel(),
        latency_model=latency,
        book_type=BookType.L2_MBP,
        support_contingent_orders=True,
        oto_trigger_mode=OtoTriggerMode.PARTIAL,
        use_position_ids=False,
        use_random_ids=False,
        use_reduce_only=True,
        use_message_queue=True,
        bar_execution=False,
        trade_execution=True,
        liquidity_consumption=True,
        queue_position=True,
    )


def detect_nautilus_simulation_capabilities() -> NautilusSimulationCapabilities:
    """Inspect the installed engine surface and report unsupported features."""
    parameters = inspect.signature(BacktestEngine.add_venue).parameters
    native_liquidation = all(
        name in parameters
        for name in (
            "liquidation_enabled",
            "liquidation_trigger_ratio",
            "liquidation_cancel_open_orders",
        )
    )
    detail = (
        "BacktestEngine.add_venue exposes native liquidation controls."
        if native_liquidation
        else "BacktestVenueConfig liquidation fields are not forwarded by "
        "BacktestEngine.add_venue in the installed Nautilus build."
    )
    return NautilusSimulationCapabilities(
        post_only_rejection=True,
        submit_cancel_latency="latency_model" in parameters,
        per_level_liquidity="liquidity_consumption" in parameters,
        queue_position="queue_position" in parameters,
        partial_oto_release="oto_trigger_mode" in parameters,
        proportional_target_resize=False,
        native_liquidation=native_liquidation,
        proportional_target_detail=(
            "OTO PARTIAL releases children after a partial parent fill but the "
            "installed engine does not resize their original quantity."
        ),
        native_liquidation_detail=detail,
    )


def _latency_model(config: HypervelocitySimulationConfig) -> LatencyModel:
    return LatencyModel(
        base_latency_nanos=0,
        insert_latency_nanos=config.submit_latency_ms * _NANOS_PER_MILLISECOND,
        update_latency_nanos=config.update_latency_ms * _NANOS_PER_MILLISECOND,
        cancel_latency_nanos=config.cancel_latency_ms * _NANOS_PER_MILLISECOND,
    )


def _nonnegative_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _probability(value: float, name: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be within [0, 1]")
