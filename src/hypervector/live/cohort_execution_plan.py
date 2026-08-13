"""Typed provider-specific execution and exit contracts for the live cohort."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import math
from typing import Literal

EntryLiquidity = Literal["taker_ioc", "maker_post_only"]
StopPolicy = Literal["fixed_bps", "structural_clamped_bps"]
TargetPolicy = Literal["none", "fixed_bps", "reward_risk"]
MaximumHoldPolicy = Literal["fixed", "extend_while_regime_supported"]
ProviderRecipeExitPolicy = Literal["ignore", "honor"]
ProfitLockPolicy = Literal["none", "completed_bar_trailing"]

_ENTRY_LIQUIDITIES = frozenset({"taker_ioc", "maker_post_only"})
_STOP_POLICIES = frozenset({"fixed_bps", "structural_clamped_bps"})
_TARGET_POLICIES = frozenset({"none", "fixed_bps", "reward_risk"})
_MAXIMUM_HOLD_POLICIES = frozenset({"fixed", "extend_while_regime_supported"})
_PROVIDER_RECIPE_EXIT_POLICIES = frozenset({"ignore", "honor"})
_PROFIT_LOCK_POLICIES = frozenset({"none", "completed_bar_trailing"})


class CohortExecutionPlanError(ValueError):
    """A provider execution contract is incomplete or internally inconsistent."""


@dataclass(frozen=True)
class ProviderExecutionContract:
    """Configured mechanics that must follow a selected strategy entry."""

    entry_liquidity: EntryLiquidity
    stop_policy: StopPolicy
    target_policy: TargetPolicy
    maximum_hold_seconds: int
    stop_bps: float | None = None
    minimum_stop_bps: float | None = None
    maximum_stop_bps: float | None = None
    target_bps: float | None = None
    target_r_multiple: float | None = None
    safety_stop_overlay: bool = False
    maximum_hold_policy: MaximumHoldPolicy = "fixed"
    hard_maximum_hold_seconds: int | None = None
    provider_recipe_exit_policy: ProviderRecipeExitPolicy = "ignore"
    profit_lock_policy: ProfitLockPolicy = "none"
    profit_lock_activation_bps: float | None = None
    profit_lock_floor_bps: float | None = None
    profit_lock_giveback_bps: float | None = None

    def __post_init__(self) -> None:
        """Reject missing parameters and ambiguous policy combinations."""
        if self.entry_liquidity not in _ENTRY_LIQUIDITIES:
            raise CohortExecutionPlanError("unsupported entry liquidity")
        if self.stop_policy not in _STOP_POLICIES:
            raise CohortExecutionPlanError("unsupported stop policy")
        if self.target_policy not in _TARGET_POLICIES:
            raise CohortExecutionPlanError("unsupported target policy")
        _positive_integer(self.maximum_hold_seconds, "maximum_hold_seconds")
        _validate_stop_contract(self)
        _validate_target_contract(self)
        _validate_maximum_hold_contract(self)
        if self.provider_recipe_exit_policy not in _PROVIDER_RECIPE_EXIT_POLICIES:
            raise CohortExecutionPlanError("unsupported provider recipe exit policy")
        _validate_profit_lock_contract(self)
        if not isinstance(self.safety_stop_overlay, bool):
            raise CohortExecutionPlanError("safety_stop_overlay must be boolean")

    def bind(
        self,
        *,
        strategy_id: str,
        stop_anchor: float | None,
    ) -> BoundExecutionPlan:
        """Bind dynamic decision evidence to one restart-safe execution plan."""
        strategy = strategy_id.strip()
        if not strategy:
            raise CohortExecutionPlanError("strategy_id must be non-empty")
        if self.stop_policy == "structural_clamped_bps":
            anchor = _positive(stop_anchor, "stop_anchor")
        else:
            anchor = None
        return BoundExecutionPlan(
            strategy_id=strategy, stop_anchor=anchor, **asdict(self)
        )

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-safe configuration projection."""
        return asdict(self)

    @classmethod
    def from_payload(cls, value: object) -> ProviderExecutionContract:
        """Parse one strict provider configuration object."""
        row = _mapping(value, "provider execution contract")
        return cls(
            entry_liquidity=_entry_liquidity(row.get("entry_liquidity")),
            stop_policy=_stop_policy(row.get("stop_policy")),
            target_policy=_target_policy(row.get("target_policy")),
            maximum_hold_seconds=_integer(
                row.get("maximum_hold_seconds"), "maximum_hold_seconds"
            ),
            stop_bps=_optional_number(row.get("stop_bps"), "stop_bps"),
            minimum_stop_bps=_optional_number(
                row.get("minimum_stop_bps"), "minimum_stop_bps"
            ),
            maximum_stop_bps=_optional_number(
                row.get("maximum_stop_bps"), "maximum_stop_bps"
            ),
            target_bps=_optional_number(row.get("target_bps"), "target_bps"),
            target_r_multiple=_optional_number(
                row.get("target_r_multiple"), "target_r_multiple"
            ),
            safety_stop_overlay=_boolean(
                row.get("safety_stop_overlay", False), "safety_stop_overlay"
            ),
            maximum_hold_policy=_maximum_hold_policy(
                row.get("maximum_hold_policy", "fixed")
            ),
            hard_maximum_hold_seconds=_optional_integer(
                row.get("hard_maximum_hold_seconds"),
                "hard_maximum_hold_seconds",
            ),
            provider_recipe_exit_policy=_provider_recipe_exit_policy(
                row.get("provider_recipe_exit_policy", "ignore")
            ),
            profit_lock_policy=_profit_lock_policy(
                row.get("profit_lock_policy", "none")
            ),
            profit_lock_activation_bps=_optional_number(
                row.get("profit_lock_activation_bps"),
                "profit_lock_activation_bps",
            ),
            profit_lock_floor_bps=_optional_number(
                row.get("profit_lock_floor_bps"), "profit_lock_floor_bps"
            ),
            profit_lock_giveback_bps=_optional_number(
                row.get("profit_lock_giveback_bps"), "profit_lock_giveback_bps"
            ),
        )


@dataclass(frozen=True)
class BoundExecutionPlan:
    """Provider contract plus causal decision-time structural evidence."""

    strategy_id: str
    entry_liquidity: EntryLiquidity
    stop_policy: StopPolicy
    target_policy: TargetPolicy
    maximum_hold_seconds: int
    stop_bps: float | None = None
    minimum_stop_bps: float | None = None
    maximum_stop_bps: float | None = None
    target_bps: float | None = None
    target_r_multiple: float | None = None
    safety_stop_overlay: bool = False
    stop_anchor: float | None = None
    maximum_hold_policy: MaximumHoldPolicy = "fixed"
    hard_maximum_hold_seconds: int | None = None
    provider_recipe_exit_policy: ProviderRecipeExitPolicy = "ignore"
    profit_lock_policy: ProfitLockPolicy = "none"
    profit_lock_activation_bps: float | None = None
    profit_lock_floor_bps: float | None = None
    profit_lock_giveback_bps: float | None = None

    def __post_init__(self) -> None:
        """Reuse contract validation and require dynamic structural evidence."""
        ProviderExecutionContract(
            entry_liquidity=self.entry_liquidity,
            stop_policy=self.stop_policy,
            target_policy=self.target_policy,
            maximum_hold_seconds=self.maximum_hold_seconds,
            stop_bps=self.stop_bps,
            minimum_stop_bps=self.minimum_stop_bps,
            maximum_stop_bps=self.maximum_stop_bps,
            target_bps=self.target_bps,
            target_r_multiple=self.target_r_multiple,
            safety_stop_overlay=self.safety_stop_overlay,
            maximum_hold_policy=self.maximum_hold_policy,
            hard_maximum_hold_seconds=self.hard_maximum_hold_seconds,
            provider_recipe_exit_policy=self.provider_recipe_exit_policy,
            profit_lock_policy=self.profit_lock_policy,
            profit_lock_activation_bps=self.profit_lock_activation_bps,
            profit_lock_floor_bps=self.profit_lock_floor_bps,
            profit_lock_giveback_bps=self.profit_lock_giveback_bps,
        )
        if not self.strategy_id.strip():
            raise CohortExecutionPlanError("strategy_id must be non-empty")
        if self.stop_policy == "structural_clamped_bps":
            _positive(self.stop_anchor, "stop_anchor")
        elif self.stop_anchor is not None:
            raise CohortExecutionPlanError("fixed stop cannot carry stop_anchor")

    def as_payload(self) -> dict[str, object]:
        """Return the complete plan for durable state transitions."""
        return asdict(self)

    @classmethod
    def from_payload(cls, value: object) -> BoundExecutionPlan:
        """Restore one exact execution plan from a ledger payload."""
        row = _mapping(value, "execution_plan")
        return cls(
            strategy_id=_text(row.get("strategy_id"), "strategy_id"),
            entry_liquidity=_entry_liquidity(row.get("entry_liquidity")),
            stop_policy=_stop_policy(row.get("stop_policy")),
            target_policy=_target_policy(row.get("target_policy")),
            maximum_hold_seconds=_integer(
                row.get("maximum_hold_seconds"), "maximum_hold_seconds"
            ),
            stop_bps=_optional_number(row.get("stop_bps"), "stop_bps"),
            minimum_stop_bps=_optional_number(
                row.get("minimum_stop_bps"), "minimum_stop_bps"
            ),
            maximum_stop_bps=_optional_number(
                row.get("maximum_stop_bps"), "maximum_stop_bps"
            ),
            target_bps=_optional_number(row.get("target_bps"), "target_bps"),
            target_r_multiple=_optional_number(
                row.get("target_r_multiple"), "target_r_multiple"
            ),
            safety_stop_overlay=_boolean(
                row.get("safety_stop_overlay", False), "safety_stop_overlay"
            ),
            stop_anchor=_optional_number(row.get("stop_anchor"), "stop_anchor"),
            maximum_hold_policy=_maximum_hold_policy(
                row.get("maximum_hold_policy", "fixed")
            ),
            hard_maximum_hold_seconds=_optional_integer(
                row.get("hard_maximum_hold_seconds"),
                "hard_maximum_hold_seconds",
            ),
            provider_recipe_exit_policy=_provider_recipe_exit_policy(
                row.get("provider_recipe_exit_policy", "ignore")
            ),
            profit_lock_policy=_profit_lock_policy(
                row.get("profit_lock_policy", "none")
            ),
            profit_lock_activation_bps=_optional_number(
                row.get("profit_lock_activation_bps"),
                "profit_lock_activation_bps",
            ),
            profit_lock_floor_bps=_optional_number(
                row.get("profit_lock_floor_bps"), "profit_lock_floor_bps"
            ),
            profit_lock_giveback_bps=_optional_number(
                row.get("profit_lock_giveback_bps"), "profit_lock_giveback_bps"
            ),
        )

    def stop_price(self, *, entry_price: float, side: str) -> float:
        """Resolve the venue stop from actual fill price and bound policy."""
        entry = _positive(entry_price, "entry_price")
        distance = self._stop_distance_bps(entry, side)
        multiplier = (
            1.0 - distance / 10_000.0 if side == "long" else 1.0 + distance / 10_000.0
        )
        return _positive(entry * multiplier, "stop_price")

    def target_price(self, *, entry_price: float, side: str) -> float | None:
        """Resolve an optional fixed or reward-risk target from actual fill."""
        entry = _positive(entry_price, "entry_price")
        _side(side)
        if self.target_policy == "none":
            return None
        distance = (
            _positive(self.target_bps, "target_bps")
            if self.target_policy == "fixed_bps"
            else self._stop_distance_bps(entry, side)
            * _positive(self.target_r_multiple, "target_r_multiple")
        )
        multiplier = (
            1.0 + distance / 10_000.0 if side == "long" else 1.0 - distance / 10_000.0
        )
        return _positive(entry * multiplier, "target_price")

    def _stop_distance_bps(self, entry_price: float, side: str) -> float:
        _side(side)
        if self.stop_policy == "fixed_bps":
            return _positive(self.stop_bps, "stop_bps")
        anchor = _positive(self.stop_anchor, "stop_anchor")
        adverse = anchor < entry_price if side == "long" else anchor > entry_price
        if not adverse:
            raise CohortExecutionPlanError("structural stop anchor must remain adverse")
        raw = abs(anchor - entry_price) / entry_price * 10_000.0
        minimum = _positive(self.minimum_stop_bps, "minimum_stop_bps")
        maximum = _positive(self.maximum_stop_bps, "maximum_stop_bps")
        return min(maximum, max(minimum, raw))


def _validate_stop_contract(contract: ProviderExecutionContract) -> None:
    if contract.stop_policy == "fixed_bps":
        _positive(contract.stop_bps, "stop_bps")
        if (
            contract.minimum_stop_bps is not None
            or contract.maximum_stop_bps is not None
        ):
            raise CohortExecutionPlanError("fixed stop cannot define clamp bounds")
        return
    minimum = _positive(contract.minimum_stop_bps, "minimum_stop_bps")
    maximum = _positive(contract.maximum_stop_bps, "maximum_stop_bps")
    if contract.stop_bps is not None or minimum > maximum:
        raise CohortExecutionPlanError("structural stop bounds are inconsistent")


def _validate_target_contract(contract: ProviderExecutionContract) -> None:
    if contract.target_policy == "none":
        if contract.target_bps is not None or contract.target_r_multiple is not None:
            raise CohortExecutionPlanError(
                "no-target policy cannot define target values"
            )
        return
    if contract.target_policy == "fixed_bps":
        _positive(contract.target_bps, "target_bps")
        if contract.target_r_multiple is not None:
            raise CohortExecutionPlanError("fixed target cannot define reward multiple")
        return
    _positive(contract.target_r_multiple, "target_r_multiple")
    if contract.target_bps is not None:
        raise CohortExecutionPlanError("reward-risk target cannot define target_bps")


def _validate_maximum_hold_contract(contract: ProviderExecutionContract) -> None:
    if contract.maximum_hold_policy not in _MAXIMUM_HOLD_POLICIES:
        raise CohortExecutionPlanError("unsupported maximum hold policy")
    hard = contract.hard_maximum_hold_seconds
    if contract.maximum_hold_policy == "fixed":
        if hard is not None:
            raise CohortExecutionPlanError(
                "fixed maximum hold cannot define a hard maximum hold"
            )
        return
    if hard is None or hard <= contract.maximum_hold_seconds:
        raise CohortExecutionPlanError(
            "hard maximum hold must be later than maximum_hold_seconds"
        )


def _validate_profit_lock_contract(contract: ProviderExecutionContract) -> None:
    values = (
        contract.profit_lock_activation_bps,
        contract.profit_lock_floor_bps,
        contract.profit_lock_giveback_bps,
    )
    if contract.profit_lock_policy not in _PROFIT_LOCK_POLICIES:
        raise CohortExecutionPlanError("unsupported profit lock policy")
    if contract.profit_lock_policy == "none":
        if any(value is not None for value in values):
            raise CohortExecutionPlanError(
                "disabled profit lock cannot define lock parameters"
            )
        return
    if any(value is None for value in values):
        raise CohortExecutionPlanError(
            "completed-bar profit lock requires activation, floor, and giveback"
        )
    activation = _positive(values[0], "profit_lock_activation_bps")
    floor = _positive(values[1], "profit_lock_floor_bps")
    _positive(values[2], "profit_lock_giveback_bps")
    if floor > activation:
        raise CohortExecutionPlanError(
            "profit lock floor cannot exceed activation threshold"
        )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise CohortExecutionPlanError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CohortExecutionPlanError(f"{label} must be non-empty text")
    return value.strip()


def _positive(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise CohortExecutionPlanError(f"{label} must be positive")
    return number


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _number(value, label)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CohortExecutionPlanError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise CohortExecutionPlanError(f"{label} must be finite")
    return number


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CohortExecutionPlanError(f"{label} must be an integer")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    return None if value is None else _integer(value, label)


def _positive_integer(value: object, label: str) -> int:
    number = _integer(value, label)
    if number <= 0:
        raise CohortExecutionPlanError(f"{label} must be positive")
    return number


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CohortExecutionPlanError(f"{label} must be boolean")
    return value


def _entry_liquidity(value: object) -> EntryLiquidity:
    text = _text(value, "entry_liquidity")
    if text not in _ENTRY_LIQUIDITIES:
        raise CohortExecutionPlanError("unsupported entry liquidity")
    return text  # type: ignore[return-value]


def _stop_policy(value: object) -> StopPolicy:
    text = _text(value, "stop_policy")
    if text not in _STOP_POLICIES:
        raise CohortExecutionPlanError("unsupported stop policy")
    return text  # type: ignore[return-value]


def _target_policy(value: object) -> TargetPolicy:
    text = _text(value, "target_policy")
    if text not in _TARGET_POLICIES:
        raise CohortExecutionPlanError("unsupported target policy")
    return text  # type: ignore[return-value]


def _maximum_hold_policy(value: object) -> MaximumHoldPolicy:
    text = _text(value, "maximum_hold_policy")
    if text not in _MAXIMUM_HOLD_POLICIES:
        raise CohortExecutionPlanError("unsupported maximum hold policy")
    return text  # type: ignore[return-value]


def _provider_recipe_exit_policy(value: object) -> ProviderRecipeExitPolicy:
    text = _text(value, "provider_recipe_exit_policy")
    if text not in _PROVIDER_RECIPE_EXIT_POLICIES:
        raise CohortExecutionPlanError("unsupported provider recipe exit policy")
    return text  # type: ignore[return-value]


def _profit_lock_policy(value: object) -> ProfitLockPolicy:
    text = _text(value, "profit_lock_policy")
    if text not in _PROFIT_LOCK_POLICIES:
        raise CohortExecutionPlanError("unsupported profit lock policy")
    return text  # type: ignore[return-value]


def _side(value: str) -> None:
    if value not in {"long", "short"}:
        raise CohortExecutionPlanError("side must be long or short")
