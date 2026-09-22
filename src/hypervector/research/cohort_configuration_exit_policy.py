"""Validated checkpoint evidence for staged provider exit policies."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
import math

from hypervector.live.cohort_adaptive_exit_policy import ADAPTIVE_EXIT_POLICIES
from hypervector.live.btc_hulk_delayed_component_floor import (
    BTC_HULK_DELAYED_COMPONENT_POLICY_IDS,
)
from hypervector.live.btc_hulk_robust_short_provider import (
    HULK_ROBUST_SHORT_STRATEGY,
)
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.cohort_stop_risk_sizing import StopRiskBudget


@dataclass(frozen=True)
class ProviderExitExpectation:
    """Non-secret provider exit settings expected from one staged profile."""

    strategy_id: str
    maximum_hold_seconds: int
    maximum_hold_policy: str
    hard_maximum_hold_seconds: int | None
    maximum_hold_evidence_maximum_age_seconds: int | None
    provider_recipe_exit_policy: str
    profit_lock_policy: str
    profit_lock_activation_bps: float | None = None
    profit_lock_floor_bps: float | None = None
    profit_lock_giveback_bps: float | None = None
    adaptive_exit_policy: str = "none"
    stop_risk_budget: StopRiskBudget | None = None


@dataclass(frozen=True)
class ProviderDirectionalExitExpectation:
    """Effective provider exit settings for one exact symbol and side."""

    strategy_id: str
    symbol: str
    side: str
    policy: ProviderExitExpectation


def provider_exit_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[ProviderExitExpectation, ...]:
    """Project every provider's exact staged exit configuration."""
    rows = (
        _expectation(provider.strategy_id, provider.execution)
        for provider in config.providers
    )
    return tuple(sorted(rows, key=lambda row: row.strategy_id))


def provider_directional_exit_expectation(
    config: MultiAssetLiveConfig,
) -> tuple[ProviderDirectionalExitExpectation, ...]:
    """Project only explicitly overridden provider-symbol-side contracts."""
    rows = (
        ProviderDirectionalExitExpectation(
            provider.strategy_id,
            override.symbol,
            override.side,
            _expectation(
                provider.strategy_id,
                provider.execution_for(override.symbol, override.side),
            ),
        )
        for provider in config.providers
        for override in provider.profit_lock_overrides
    )
    return tuple(sorted(rows, key=lambda row: (row.strategy_id, row.symbol, row.side)))


def provider_exit_policy_evidence(
    policies: tuple[ProviderExitExpectation, ...],
) -> dict[str, dict[str, object]]:
    """Validate and serialize staged exit policies without execution authority."""
    evidence: dict[str, dict[str, object]] = {}
    for row in policies:
        _validate_exit_policy(row, evidence)
        evidence[row.strategy_id] = _policy_payload(row)
    return evidence


def provider_directional_exit_policy_evidence(
    policies: tuple[ProviderDirectionalExitExpectation, ...],
) -> dict[str, dict[str, object]]:
    """Serialize exact directional policies under unambiguous scope keys."""
    evidence: dict[str, dict[str, object]] = {}
    for row in policies:
        if (
            not row.strategy_id.strip()
            or not row.symbol.strip()
            or row.side not in {"long", "short"}
            or any("|" in value for value in (row.strategy_id, row.symbol, row.side))
        ):
            raise ValueError("provider directional exit scope is invalid")
        key = f"{row.strategy_id}|{row.symbol}|{row.side}"
        if key in evidence:
            raise ValueError("provider directional exit scope is duplicated")
        _validate_exit_policy(row.policy, evidence)
        evidence[key] = _policy_payload(row.policy)
    return evidence


def _expectation(strategy_id: str, contract: object) -> ProviderExitExpectation:
    from hypervector.live.cohort_execution_plan import ProviderExecutionContract

    if not isinstance(contract, ProviderExecutionContract):
        raise TypeError("provider execution contract is invalid")
    return ProviderExitExpectation(
        strategy_id,
        contract.maximum_hold_seconds,
        contract.maximum_hold_policy,
        contract.hard_maximum_hold_seconds,
        contract.maximum_hold_evidence_maximum_age_seconds,
        contract.provider_recipe_exit_policy,
        contract.profit_lock_policy,
        contract.profit_lock_activation_bps,
        contract.profit_lock_floor_bps,
        contract.profit_lock_giveback_bps,
        contract.adaptive_exit_policy,
        contract.stop_risk_budget,
    )


def _policy_payload(row: ProviderExitExpectation) -> dict[str, object]:
    return {
        **(
            {"stop_risk_budget": asdict(row.stop_risk_budget)}
            if row.stop_risk_budget is not None
            else {}
        ),
        **(
            {"adaptive_exit_policy": row.adaptive_exit_policy}
            if row.adaptive_exit_policy != "none"
            else {}
        ),
        "maximum_hold_seconds": row.maximum_hold_seconds,
        "maximum_hold_policy": row.maximum_hold_policy,
        "hard_maximum_hold_seconds": row.hard_maximum_hold_seconds,
        "maximum_hold_evidence_maximum_age_seconds": (
            row.maximum_hold_evidence_maximum_age_seconds
        ),
        "provider_recipe_exit_policy": row.provider_recipe_exit_policy,
        "profit_lock_policy": row.profit_lock_policy,
        "profit_lock_activation_bps": row.profit_lock_activation_bps,
        "profit_lock_floor_bps": row.profit_lock_floor_bps,
        "profit_lock_giveback_bps": row.profit_lock_giveback_bps,
    }


def _validate_exit_policy(
    row: ProviderExitExpectation,
    evidence: dict[str, dict[str, object]],
) -> None:
    strategy = row.strategy_id.strip()
    valid_hold = (
        not isinstance(row.maximum_hold_seconds, bool) and row.maximum_hold_seconds > 0
    )
    hard = row.hard_maximum_hold_seconds
    valid_hard = hard is None or (
        not isinstance(hard, bool) and hard > row.maximum_hold_seconds
    )
    evidence_age = row.maximum_hold_evidence_maximum_age_seconds
    valid_evidence_age = evidence_age is None or (
        not isinstance(evidence_age, bool) and evidence_age > 0
    )
    fixed = row.maximum_hold_policy == "fixed" and hard is None
    extended = row.maximum_hold_policy == "extend_while_regime_supported" and hard
    if (
        not strategy
        or "|" in strategy
        or strategy in evidence
        or not valid_hold
        or not valid_hard
        or not valid_evidence_age
        or not (fixed or bool(extended))
        or row.provider_recipe_exit_policy not in {"ignore", "honor"}
        or not _profit_lock_valid(row)
        or row.adaptive_exit_policy not in ADAPTIVE_EXIT_POLICIES
    ):
        raise ValueError("provider exit policy is invalid")


def _profit_lock_valid(row: ProviderExitExpectation) -> bool:
    values = (
        row.profit_lock_activation_bps,
        row.profit_lock_floor_bps,
        row.profit_lock_giveback_bps,
    )
    if row.profit_lock_policy == "none":
        return all(value is None for value in values)
    if row.profit_lock_policy in BTC_HULK_DELAYED_COMPONENT_POLICY_IDS:
        return row.strategy_id == HULK_ROBUST_SHORT_STRATEGY and all(
            value is None for value in values
        )
    if row.profit_lock_policy != "completed_bar_trailing":
        return False
    if any(value is None for value in values):
        return False
    activation, floor, giveback = (
        float(value) for value in values if value is not None
    )
    return (
        all(math.isfinite(value) and value > 0.0 for value in values)
        and floor <= activation
        and giveback > 0.0
    )
