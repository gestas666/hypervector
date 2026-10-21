"""Typed provider-specific execution and exit contracts for the live cohort."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from hypervector.live.cohort_execution_plan_parsing import (
    _mapping,
    _text,
    _positive,
    _optional_number,
    _integer_field,
    _optional_integer_field,
    _positive_integer,
    _boolean,
)

from hypervector.live.cohort_adaptive_exit_policy import (
    ADAPTIVE_EXIT_POLICIES,
    ADAPTIVE_EXIT_POLICY,
    RETENTION_EXIT_POLICY,
    AdaptiveExitParameters,
    RetentionExitParameters,
)
from hypervector.live.cohort_stop_risk_sizing import StopRiskBudget
from hypervector.live.cohort_execution_plan_validation import (
    CohortExecutionPlanError,
    validate_profit_lock_contract,
)

EntryLiquidity = Literal["taker_ioc", "maker_post_only"]
StopPolicy = Literal["fixed_bps", "structural_clamped_bps"]
TargetPolicy = Literal["none", "fixed_bps", "reward_risk", "absolute_anchor"]
MaximumHoldPolicy = Literal["fixed", "extend_while_regime_supported"]
ProviderRecipeExitPolicy = Literal["ignore", "honor"]
ProfitLockPolicy = Literal["none", "completed_bar_trailing"]
# Where the retention-exit floor moves the resting venue stop: entry +/- 25 bps, or
# the more protective of that and the +/- 0.5R software floor.
BreakevenStopTarget = Literal["entry_offset", "floor"]

_ENTRY_LIQUIDITIES = frozenset({"taker_ioc", "maker_post_only"})
_STOP_POLICIES = frozenset({"fixed_bps", "structural_clamped_bps"})
_TARGET_POLICIES = frozenset({"none", "fixed_bps", "reward_risk", "absolute_anchor"})
_MAXIMUM_HOLD_POLICIES = frozenset({"fixed", "extend_while_regime_supported"})
_PROVIDER_RECIPE_EXIT_POLICIES = frozenset({"ignore", "honor"})
_BREAKEVEN_STOP_TARGETS = frozenset({"entry_offset", "floor"})
_PROFIT_LOCK_POLICIES = frozenset({"none", "completed_bar_trailing"})


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
    maximum_hold_evidence_maximum_age_seconds: int | None = None
    provider_recipe_exit_policy: ProviderRecipeExitPolicy = "ignore"
    adaptive_exit_policy: str = "none"
    profit_lock_policy: ProfitLockPolicy = "none"
    profit_lock_activation_bps: float | None = None
    profit_lock_floor_bps: float | None = None
    profit_lock_giveback_bps: float | None = None
    stop_risk_budget: StopRiskBudget | None = None
    breakeven_stop_target: BreakevenStopTarget = "entry_offset"
    adaptive_exit: AdaptiveExitParameters | None = None
    retention_exit: RetentionExitParameters | None = None

    def __post_init__(self) -> None:
        """Reject missing parameters and ambiguous policy combinations."""
        if self.stop_risk_budget is not None and not isinstance(
            self.stop_risk_budget, StopRiskBudget
        ):
            raise CohortExecutionPlanError(
                "stop_risk_budget must be a typed risk budget"
            )
        if self.entry_liquidity not in _ENTRY_LIQUIDITIES:
            raise CohortExecutionPlanError("unsupported entry liquidity")
        if self.stop_policy not in _STOP_POLICIES:
            raise CohortExecutionPlanError("unsupported stop policy")
        if self.target_policy not in _TARGET_POLICIES:
            raise CohortExecutionPlanError("unsupported target policy")
        _positive_integer(self.maximum_hold_seconds, "maximum_hold_seconds")
        if self.adaptive_exit_policy not in ADAPTIVE_EXIT_POLICIES:
            raise CohortExecutionPlanError("unsupported adaptive exit policy")
        _validate_adaptive_parameters(self)
        if self.adaptive_exit_policy != "none" and self.profit_lock_policy != "none":
            raise CohortExecutionPlanError(
                "adaptive and legacy profit locks cannot overlap"
            )
        if self.breakeven_stop_target not in _BREAKEVEN_STOP_TARGETS:
            raise CohortExecutionPlanError("unsupported breakeven stop target")
        if (
            self.breakeven_stop_target == "floor"
            and self.adaptive_exit_policy != RETENTION_EXIT_POLICY
        ):
            raise CohortExecutionPlanError(
                f"breakeven_stop_target floor requires {RETENTION_EXIT_POLICY}"
            )
        _validate_stop_contract(self)
        _validate_target_contract(self)
        _validate_maximum_hold_contract(self)
        if self.provider_recipe_exit_policy not in _PROVIDER_RECIPE_EXIT_POLICIES:
            raise CohortExecutionPlanError("unsupported provider recipe exit policy")
        validate_profit_lock_contract(
            self.profit_lock_policy,
            self.profit_lock_activation_bps,
            self.profit_lock_floor_bps,
            self.profit_lock_giveback_bps,
        )
        if not isinstance(self.safety_stop_overlay, bool):
            raise CohortExecutionPlanError("safety_stop_overlay must be boolean")

    def bind(
        self,
        *,
        strategy_id: str,
        stop_anchor: float | None,
        target_anchor: float | None = None,
    ) -> BoundExecutionPlan:
        """Bind dynamic decision evidence to one restart-safe execution plan."""
        strategy = strategy_id.strip()
        if not strategy:
            raise CohortExecutionPlanError("strategy_id must be non-empty")
        if self.stop_policy == "structural_clamped_bps":
            anchor = _positive(stop_anchor, "stop_anchor")
        else:
            anchor = None
        target = (
            _positive(target_anchor, "target_anchor")
            if self.target_policy == "absolute_anchor"
            else None
        )
        if self.target_policy != "absolute_anchor" and target_anchor is not None:
            raise CohortExecutionPlanError("static target cannot carry target_anchor")
        return BoundExecutionPlan(
            strategy_id=strategy,
            stop_anchor=anchor,
            target_anchor=target,
            **{
                **asdict(self),
                "stop_risk_budget": self.stop_risk_budget,
                "adaptive_exit": self.adaptive_exit,
                "retention_exit": self.retention_exit,
            },
        )

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-safe configuration projection."""
        return _contract_payload(self, asdict(self))

    @classmethod
    def from_payload(cls, value: object) -> ProviderExecutionContract:
        """Parse one strict provider configuration object."""
        row = _mapping(value, "provider execution contract")
        return cls(
            stop_risk_budget=StopRiskBudget.from_payload(row.get("stop_risk_budget")),
            entry_liquidity=_entry_liquidity(row.get("entry_liquidity")),
            stop_policy=_stop_policy(row.get("stop_policy")),
            target_policy=_target_policy(row.get("target_policy")),
            maximum_hold_seconds=_integer_field(row, "maximum_hold_seconds"),
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
            hard_maximum_hold_seconds=_optional_integer_field(
                row, "hard_maximum_hold_seconds"
            ),
            maximum_hold_evidence_maximum_age_seconds=_optional_integer_field(
                row, "maximum_hold_evidence_maximum_age_seconds"
            ),
            provider_recipe_exit_policy=_provider_recipe_exit_policy(
                row.get("provider_recipe_exit_policy", "ignore")
            ),
            adaptive_exit_policy=_text(
                row.get("adaptive_exit_policy", "none"), "adaptive_exit_policy"
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
            breakeven_stop_target=_breakeven_stop_target(
                row.get("breakeven_stop_target", "entry_offset")
            ),
            adaptive_exit=_adaptive_parameters(row.get("adaptive_exit")),
            retention_exit=_retention_parameters(row.get("retention_exit")),
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
    target_anchor: float | None = None
    maximum_hold_policy: MaximumHoldPolicy = "fixed"
    hard_maximum_hold_seconds: int | None = None
    maximum_hold_evidence_maximum_age_seconds: int | None = None
    provider_recipe_exit_policy: ProviderRecipeExitPolicy = "ignore"
    adaptive_exit_policy: str = "none"
    profit_lock_policy: ProfitLockPolicy = "none"
    profit_lock_activation_bps: float | None = None
    profit_lock_floor_bps: float | None = None
    profit_lock_giveback_bps: float | None = None
    stop_risk_budget: StopRiskBudget | None = None
    breakeven_stop_target: BreakevenStopTarget = "entry_offset"
    adaptive_exit: AdaptiveExitParameters | None = None
    retention_exit: RetentionExitParameters | None = None

    def __post_init__(self) -> None:
        """Reuse contract validation and require dynamic structural evidence."""
        ProviderExecutionContract(
            stop_risk_budget=self.stop_risk_budget,
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
            maximum_hold_evidence_maximum_age_seconds=(
                self.maximum_hold_evidence_maximum_age_seconds
            ),
            provider_recipe_exit_policy=self.provider_recipe_exit_policy,
            adaptive_exit_policy=self.adaptive_exit_policy,
            profit_lock_policy=self.profit_lock_policy,
            profit_lock_activation_bps=self.profit_lock_activation_bps,
            profit_lock_floor_bps=self.profit_lock_floor_bps,
            profit_lock_giveback_bps=self.profit_lock_giveback_bps,
            breakeven_stop_target=self.breakeven_stop_target,
            adaptive_exit=self.adaptive_exit,
            retention_exit=self.retention_exit,
        )
        if not self.strategy_id.strip():
            raise CohortExecutionPlanError("strategy_id must be non-empty")
        if self.stop_policy == "structural_clamped_bps":
            _positive(self.stop_anchor, "stop_anchor")
        elif self.stop_anchor is not None:
            raise CohortExecutionPlanError("fixed stop cannot carry stop_anchor")
        if self.target_policy == "absolute_anchor":
            _positive(self.target_anchor, "target_anchor")
        elif self.target_anchor is not None:
            raise CohortExecutionPlanError("static target cannot carry target_anchor")

    def as_payload(self) -> dict[str, object]:
        """Return the complete plan for durable state transitions."""
        return _contract_payload(self, asdict(self))

    @classmethod
    def from_payload(cls, value: object) -> BoundExecutionPlan:
        """Restore one exact execution plan from a ledger payload."""
        row = _mapping(value, "execution_plan")
        return cls(
            stop_risk_budget=StopRiskBudget.from_payload(row.get("stop_risk_budget")),
            strategy_id=_text(row.get("strategy_id"), "strategy_id"),
            entry_liquidity=_entry_liquidity(row.get("entry_liquidity")),
            stop_policy=_stop_policy(row.get("stop_policy")),
            target_policy=_target_policy(row.get("target_policy")),
            maximum_hold_seconds=_integer_field(row, "maximum_hold_seconds"),
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
            target_anchor=_optional_number(row.get("target_anchor"), "target_anchor"),
            maximum_hold_policy=_maximum_hold_policy(
                row.get("maximum_hold_policy", "fixed")
            ),
            hard_maximum_hold_seconds=_optional_integer_field(
                row, "hard_maximum_hold_seconds"
            ),
            maximum_hold_evidence_maximum_age_seconds=_optional_integer_field(
                row, "maximum_hold_evidence_maximum_age_seconds"
            ),
            provider_recipe_exit_policy=_provider_recipe_exit_policy(
                row.get("provider_recipe_exit_policy", "ignore")
            ),
            adaptive_exit_policy=_text(
                row.get("adaptive_exit_policy", "none"), "adaptive_exit_policy"
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
            breakeven_stop_target=_breakeven_stop_target(
                row.get("breakeven_stop_target", "entry_offset")
            ),
            adaptive_exit=_adaptive_parameters(row.get("adaptive_exit")),
            retention_exit=_retention_parameters(row.get("retention_exit")),
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
        if self.target_policy == "absolute_anchor":
            target = _positive(self.target_anchor, "target_anchor")
            favorable = target > entry if side == "long" else target < entry
            if not favorable:
                raise CohortExecutionPlanError("absolute target must remain favorable")
            return target
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
        minimum = _positive(self.minimum_stop_bps, "minimum_stop_bps")
        maximum = _positive(self.maximum_stop_bps, "maximum_stop_bps")
        if self.structural_anchor_overrun(entry_price, side):
            # A fill more favorable than the anchor cannot use it as a stop; the
            # clamp floor is the tightest protection the contract allows.
            return minimum
        raw = abs(anchor - entry_price) / entry_price * 10_000.0
        return min(maximum, max(minimum, raw))

    def structural_anchor_overrun(self, entry_price: float, side: str) -> bool:
        """Report whether the structural anchor is not adverse to this price."""
        if self.stop_policy != "structural_clamped_bps":
            return False
        entry = _positive(entry_price, "entry_price")
        _side(side)
        anchor = _positive(self.stop_anchor, "stop_anchor")
        return anchor >= entry if side == "long" else anchor <= entry


def _contract_payload(
    contract: ProviderExecutionContract | BoundExecutionPlan,
    payload: dict[str, object],
) -> dict[str, object]:
    """Omit unset optional sections so a plain contract keeps its identity."""
    for key, value in (
        ("stop_risk_budget", contract.stop_risk_budget),
        ("adaptive_exit", contract.adaptive_exit),
        ("retention_exit", contract.retention_exit),
    ):
        if value is None:
            payload.pop(key)
        else:
            payload[key] = value.as_payload()
    if contract.adaptive_exit_policy == "none":
        payload.pop("adaptive_exit_policy")
    if contract.breakeven_stop_target == "entry_offset":
        payload.pop("breakeven_stop_target")
    return payload


def _validate_adaptive_parameters(contract: ProviderExecutionContract) -> None:
    """Require exactly the parameter table the bound adaptive policy reads."""
    policy = contract.adaptive_exit_policy
    if contract.adaptive_exit is not None and not isinstance(
        contract.adaptive_exit, AdaptiveExitParameters
    ):
        raise CohortExecutionPlanError("adaptive_exit must be a typed parameter table")
    if contract.retention_exit is not None and not isinstance(
        contract.retention_exit, RetentionExitParameters
    ):
        raise CohortExecutionPlanError("retention_exit must be a typed parameter table")
    if (contract.adaptive_exit is not None) != (policy == ADAPTIVE_EXIT_POLICY):
        raise CohortExecutionPlanError(
            f"adaptive_exit parameters are required for, and only for, {ADAPTIVE_EXIT_POLICY}"
        )
    if (contract.retention_exit is not None) != (policy == RETENTION_EXIT_POLICY):
        raise CohortExecutionPlanError(
            f"retention_exit parameters are required for, and only for, {RETENTION_EXIT_POLICY}"
        )


def _adaptive_parameters(value: object) -> AdaptiveExitParameters | None:
    try:
        return AdaptiveExitParameters.from_payload(value)
    except (TypeError, ValueError) as exc:
        raise CohortExecutionPlanError(str(exc)) from exc


def _retention_parameters(value: object) -> RetentionExitParameters | None:
    try:
        return RetentionExitParameters.from_payload(value)
    except (TypeError, ValueError) as exc:
        raise CohortExecutionPlanError(str(exc)) from exc


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
    if contract.target_policy in {"none", "absolute_anchor"}:
        if contract.target_bps is not None or contract.target_r_multiple is not None:
            raise CohortExecutionPlanError(
                "dynamic or no-target policy cannot define static target values"
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
    evidence_age = contract.maximum_hold_evidence_maximum_age_seconds
    if contract.maximum_hold_policy == "fixed":
        if hard is not None:
            raise CohortExecutionPlanError(
                "fixed maximum hold cannot define a hard maximum hold"
            )
        if evidence_age is not None:
            raise CohortExecutionPlanError(
                "fixed maximum hold cannot define an evidence age"
            )
        return
    if hard is None or hard <= contract.maximum_hold_seconds:
        raise CohortExecutionPlanError(
            "hard maximum hold must be later than maximum_hold_seconds"
        )
    if evidence_age is not None:
        _positive_integer(
            evidence_age,
            "maximum_hold_evidence_maximum_age_seconds",
        )


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


def _breakeven_stop_target(value: object) -> BreakevenStopTarget:
    text = _text(value, "breakeven_stop_target")
    if text not in _BREAKEVEN_STOP_TARGETS:
        raise CohortExecutionPlanError("unsupported breakeven stop target")
    return text  # type: ignore[return-value]


def _side(value: str) -> None:
    if value not in {"long", "short"}:
        raise CohortExecutionPlanError("side must be long or short")
