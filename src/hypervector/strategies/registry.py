"""Name → builder + param schema + role + declared execution (SRS_HV1_STRAT_MULTI).

A strategy family registers one :class:`StrategySpec` per name with
:func:`register`. The spec's :class:`ExecutionProfile` declares how the
strategy is sized, exited and filled; every consumer (sweep, autotune,
export validation, Nautilus, paper) reads those declared options instead of
switching on strategy names. The defaults are the standard path.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal

Role = Literal["uptrend", "downtrend", "regime", "other"]
TradeDirection = Literal["long", "short"]

if TYPE_CHECKING:
    import pandas as pd

    SignalBuilder = Callable[..., tuple[pd.Series, pd.Series, str]]
else:  # the registry stays importable without pandas (CLI discovery, status)
    SignalBuilder = Callable[..., tuple[Any, Any, str]]

#: Exit mode of a strategy whose own exit signals are its only exits.
STRATEGY_MANAGED_EXIT_MODE = "strategy_managed"
#: Resting time of a post-only entry before it is cancelled, unless declared.
DEFAULT_ENTRY_TTL_SECONDS = 300.0


def normalize_direction(tag: str) -> TradeDirection:
    """Map a builder's direction tag ('long', 'breakout_short', ...) to long|short.

    Strict: anything that is not exactly long/short or ``*_long``/``*_short``
    is a ValueError (no substring guessing).
    """
    text = str(tag).strip().lower() if isinstance(tag, str) else ""
    if text in ("long", "short"):
        return text  # type: ignore[return-value]
    if text.endswith("_long"):
        return "long"
    if text.endswith("_short"):
        return "short"
    raise ValueError(f"direction must be long|short, got {tag!r}")


@dataclass(frozen=True)
class ExecutionProfile:
    """Execution, sizing and exit options a strategy declares.

    Every default is the standard path: market IOC (taker) orders,
    conviction-scaled risk sizing capped by the configured size fraction,
    configured stop/target/trail exits, the requested fee model, and 1x
    simulation leverage.

    * ``post_only_entries``: entries are post-only limit (maker) orders at the
      same-side touch. Paper rests them for ``entry_ttl_seconds`` and fills
      them only on through-the-limit evidence at the maker fee; shadow intents
      are recorded as limit post-only; the generic market-IOC live runner
      refuses such a strategy.
    * ``fixed_margin_fraction`` (with ``leverage``): fixed sizing. Every entry
      commits this fraction of equity as margin, so the notional fraction is
      ``fixed_margin_fraction * leverage`` regardless of conviction or stop
      distance; models may annotate entries but never scale or filter them.
    * ``leverage``: the leverage the strategy runs at (simulation margin and
      the venue-cap check); it never exceeds the symbol's venue cap.
    * ``strategy_managed_exits``: the builder's exit signals are the only
      exits; no stop, target bracket or trail is applied and bundles export
      the ``strategy_managed`` exit mode. Risk sizing needs a stop distance,
      so it requires fixed sizing.
    * ``fee_model``: the cost model research measures the strategy with,
      whatever fee model was requested (e.g. ``hl_maker`` for maker-only
      execution).
    """

    post_only_entries: bool = False
    entry_ttl_seconds: float = DEFAULT_ENTRY_TTL_SECONDS
    fixed_margin_fraction: float | None = None
    leverage: float | None = None
    strategy_managed_exits: bool = False
    fee_model: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.post_only_entries, bool):
            raise ValueError("post_only_entries must be a bool")
        if not isinstance(self.strategy_managed_exits, bool):
            raise ValueError("strategy_managed_exits must be a bool")
        _require_positive("entry_ttl_seconds", self.entry_ttl_seconds)
        if self.leverage is not None:
            _require_positive("leverage", self.leverage)
        if self.fixed_margin_fraction is not None:
            _require_positive("fixed_margin_fraction", self.fixed_margin_fraction)
            if float(self.fixed_margin_fraction) > 1.0:
                raise ValueError("fixed_margin_fraction must be <= 1")
            if self.leverage is None:
                raise ValueError("fixed_margin_fraction requires a declared leverage")
        if self.strategy_managed_exits and self.fixed_margin_fraction is None:
            raise ValueError(
                "strategy_managed_exits requires fixed sizing (risk sizing needs "
                "a stop distance); declare fixed_margin_fraction and leverage"
            )
        if self.fee_model is not None and not str(self.fee_model).strip():
            raise ValueError("fee_model must be a non-empty cost model name")

    @property
    def fixed_sizing(self) -> bool:
        """Whether entries use the fixed margin allocation."""
        return self.fixed_margin_fraction is not None

    @property
    def fixed_notional_fraction(self) -> float | None:
        """Notional divided by equity for fixed sizing, else ``None``."""
        if self.fixed_margin_fraction is None or self.leverage is None:
            return None
        return float(self.fixed_margin_fraction) * float(self.leverage)

    @property
    def standard(self) -> bool:
        """Whether every option is the standard path."""
        return self == STANDARD_EXECUTION

    def exit_dict(self) -> dict[str, Any] | None:
        """The exported exit lifecycle for strategy-managed exits, else ``None``."""
        if not self.strategy_managed_exits:
            return None
        return {"mode": STRATEGY_MANAGED_EXIT_MODE, "stop": None}

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe declared options (board, bundle and identity provenance)."""
        return {**asdict(self), "fixed_notional_fraction": self.fixed_notional_fraction}


def _require_positive(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be finite and > 0")


STANDARD_EXECUTION = ExecutionProfile()


@dataclass
class StrategySpec:
    name: str
    role: Role
    param_grid: dict[str, list[Any]]
    build_signals: SignalBuilder
    description: str = ""
    #: True only where the builder applies ``gate_signals_by_orderbook`` to the
    #: ``book_gate``/``max_spread_bps``/``min_obi`` keywords; searches add book
    #: dimensions only for such strategies.
    supports_book_gate: bool = False
    #: Declared execution, sizing and exit options (standard path by default).
    execution: ExecutionProfile = field(default_factory=ExecutionProfile)


_REGISTRY: dict[str, StrategySpec] = {}


class UnknownStrategy(KeyError):
    """A strategy name that no registered family declares."""

    def __init__(self, name: str | None) -> None:
        self.name = name
        super().__init__(name)

    def __str__(self) -> str:
        return unknown_strategy_message(self.name)


def unknown_strategy_message(name: str | None) -> str:
    """Explain a missing or unknown strategy and how a family registers one."""
    registered = sorted(_REGISTRY)
    known = ", ".join(registered) if registered else "none"
    head = "no strategy given" if not name else f"unknown strategy: {name}"
    return (
        f"{head} (registered: {known}); a strategy family registers its "
        "StrategySpec with hypervector.strategies.registry.register() from a "
        "module listed in hypervector.strategies.STRATEGY_FAMILY_MODULES"
    )


def register(spec: StrategySpec) -> StrategySpec:
    if not isinstance(spec.execution, ExecutionProfile):
        raise TypeError("StrategySpec.execution must be an ExecutionProfile")
    _REGISTRY[spec.name] = spec
    return spec


def get_strategy(name: str) -> StrategySpec:
    if name not in _REGISTRY:
        raise UnknownStrategy(name)
    return _REGISTRY[name]


def list_strategies(role: Role | None = None) -> list[StrategySpec]:
    specs = list(_REGISTRY.values())
    if role is not None:
        specs = [s for s in specs if s.role == role]
    return specs


def execution_profile(name: str | None) -> ExecutionProfile:
    """Declared options of a registered strategy; the standard path otherwise."""
    spec = _REGISTRY.get(str(name)) if name else None
    return spec.execution if spec is not None else STANDARD_EXECUTION


def clear_registry() -> None:
    _REGISTRY.clear()
