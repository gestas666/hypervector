"""Pure filtering and controller assembly for one cohort routing cycle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    IntentRoutingReport,
    RoutingAction,
    StrategyIntent,
    WithheldIntent,
)
from hypervector.live.cohort_entry_sizing import CohortEntrySizing
from hypervector.live.cohort_execution_contract_selection import (
    select_execution_contract,
)
from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_maximum_hold_controller import (
    CohortMaximumHoldController,
)
from hypervector.live.cohort_maximum_hold_policy import EvaluationMap
from hypervector.live.cohort_provider_exit_controller import (
    CohortProviderExitController,
)
from hypervector.live.cohort_profit_lock_controller import CohortProfitLockController
from hypervector.live.multi_asset_live_protocols import (
    CohortTelemetryProtocol,
    MultiAssetEngineProtocol,
)
from hypervector.live.hyperliquid_protocol import HyperliquidReconciliationSnapshot
from hypervector.live.multi_asset_intent_poller import CohortIntentPoll
from hypervector.live.bidirectional_intents import PositionState
from hypervector.live.multi_asset_live_runner_support import (
    MultiAssetLiveRunnerError,
    engine_position_states,
    validate_runtime,
)
from hypervector.live.cohort_transition_drain import CohortTransitionDrain


@dataclass(frozen=True)
class CohortExitBatch:
    """Configured close actions and their exact intent-suppression scopes."""

    closing_symbols: set[str]
    timeout_symbols: set[str]
    recipe_exit_symbols: set[str]
    profit_lock_exit_symbols: set[str]
    actions: tuple[RoutingAction, ...]


def validate_and_build_exit_controllers(
    *,
    symbols: tuple[str, ...],
    engines: Mapping[str, MultiAssetEngineProtocol],
    router: BidirectionalIntentRouter,
    poll_seconds: float,
    fallback_hold_ms: Mapping[str, int],
    contracts: Mapping[str, ProviderExecutionContract],
    executable_pairs: frozenset[tuple[str, str]],
    executable_directions: frozenset[tuple[str, str, str]],
    sizing: Mapping[tuple[str, str], CohortEntrySizing],
    directional_sizing: Mapping[tuple[str, str, str], CohortEntrySizing],
    telemetry: CohortTelemetryProtocol,
) -> tuple[
    CohortMaximumHoldController,
    CohortProviderExitController,
    CohortProfitLockController,
]:
    """Validate runner ownership, then build both exit controllers."""
    validate_runtime(
        symbols,
        engines,
        router,
        poll_seconds,
        fallback_hold_ms,
        contracts,
        executable_pairs,
        executable_directions,
        sizing,
        directional_sizing,
    )
    bounded_fallbacks = provider_bounded_fallback_hold_ms(
        fallback_hold_ms,
        contracts,
        executable_pairs,
    )
    return build_exit_controllers(
        symbols=symbols,
        engines=engines,
        fallback_hold_ms=bounded_fallbacks,
        telemetry=telemetry,
        required_plan_symbols=_profit_lock_symbols(
            contracts, executable_pairs, executable_directions
        ),
    )


def provider_bounded_fallback_hold_ms(
    fallback_hold_ms: Mapping[str, int],
    contracts: Mapping[str, ProviderExecutionContract],
    executable_pairs: frozenset[tuple[str, str]],
) -> dict[str, int]:
    """Cap planless recovery at the longest executable provider horizon."""
    provider_caps: dict[str, int] = {}
    for strategy_id, symbol in executable_pairs:
        contract = contracts.get(strategy_id)
        if contract is None:
            raise MultiAssetLiveRunnerError(
                f"executable provider {strategy_id} lacks an execution contract"
            )
        terminal_seconds = (
            contract.hard_maximum_hold_seconds
            if contract.maximum_hold_policy == "extend_while_regime_supported"
            else contract.maximum_hold_seconds
        )
        if terminal_seconds is None:
            raise MultiAssetLiveRunnerError(
                f"executable provider {strategy_id} lacks a terminal hold"
            )
        provider_caps[symbol] = max(
            provider_caps.get(symbol, 0),
            terminal_seconds * 1_000,
        )
    return {
        symbol: min(configured, provider_caps.get(symbol, configured))
        for symbol, configured in fallback_hold_ms.items()
    }


def build_exit_controllers(
    *,
    symbols: tuple[str, ...],
    engines: Mapping[str, MultiAssetEngineProtocol],
    fallback_hold_ms: Mapping[str, int],
    telemetry: CohortTelemetryProtocol,
    required_plan_symbols: frozenset[str] = frozenset(),
) -> tuple[
    CohortMaximumHoldController,
    CohortProviderExitController,
    CohortProfitLockController,
]:
    """Build the timer and lifecycle-bound recipe exit controllers."""
    maximum_hold = CohortMaximumHoldController(
        symbols=symbols,
        engines=engines,
        fallback_hold_ms=fallback_hold_ms,
        telemetry=telemetry,
    )
    recipe = CohortProviderExitController(
        symbols=symbols,
        engines=engines,
        telemetry=telemetry,
    )
    profit_lock = CohortProfitLockController(
        symbols=symbols,
        engines=engines,
        telemetry=telemetry,
        required_plan_symbols=required_plan_symbols,
    )
    return maximum_hold, recipe, profit_lock


def _profit_lock_symbols(
    contracts: Mapping[str, ProviderExecutionContract],
    executable_pairs: frozenset[tuple[str, str]],
    executable_directions: frozenset[tuple[str, str, str]],
) -> frozenset[str]:
    """Return every symbol whose resolved contract binds a profit lock.

    Resolution must use the same direction-then-symbol-then-provider precedence the
    execution path uses. Reading the provider entry alone let a lock bound per
    (provider, symbol, side) go unrecorded, so a planless restart never tripped the
    controller's fail-closed check for a lost execution plan.
    """
    locked: set[str] = set()
    for provider, symbol in executable_pairs:
        sides = [
            side
            for candidate, market, side in executable_directions
            if candidate == provider and market == symbol
        ]
        for side in sides or [None]:
            contract = select_execution_contract(contracts, provider, symbol, side)
            if contract is not None and (contract.profit_lock_policy != "none" or contract.adaptive_exit_policy != "none"):
                locked.add(symbol)
                break
    return frozenset(locked)


def configured_exit_batch(
    *,
    symbols: tuple[str, ...],
    observed_ms: int,
    poll: CohortIntentPoll,
    venues: tuple[HyperliquidReconciliationSnapshot, ...],
    evaluations: EvaluationMap,
    maximum_hold: CohortMaximumHoldController,
    recipe_exit: CohortProviderExitController,
    profit_lock: CohortProfitLockController,
) -> CohortExitBatch:
    """Evaluate timer, provider recipe, then profit-lock exit precedence."""
    expired, timeout_actions = maximum_hold.actions(
        observed_ms, poll.reference_prices, evaluations
    )
    recipe_symbols, recipe_actions = recipe_exit.actions(
        observed_ms=observed_ms,
        reference_prices=poll.reference_prices,
        evaluations=evaluations,
        excluded_symbols=expired,
    )
    entry_prices = {
        symbol: venue.position.entry_price
        for symbol, venue in zip(symbols, venues, strict=True)
        if venue.position.entry_price is not None
    }
    lock_symbols, lock_actions = profit_lock.actions(
        observed_ms=observed_ms,
        reference_prices=poll.reference_prices,
        entry_prices=entry_prices,
        market_bars=poll.exit_bars,
        excluded_symbols=expired | recipe_symbols,
        evaluations=tuple(evaluations.values()),
    )
    return CohortExitBatch(
        expired | recipe_symbols | lock_symbols,
        expired,
        recipe_symbols,
        lock_symbols,
        timeout_actions + recipe_actions + lock_actions,
    )


def route_cycle(
    *,
    symbols: tuple[str, ...],
    engines: Mapping[str, MultiAssetEngineProtocol],
    router: BidirectionalIntentRouter,
    poll: CohortIntentPoll,
    observed_ms: int,
    operator_symbols: set[str],
    venues: tuple[HyperliquidReconciliationSnapshot, ...],
    evaluations: EvaluationMap,
    maximum_hold: CohortMaximumHoldController,
    recipe_exit: CohortProviderExitController,
    profit_lock: CohortProfitLockController,
    executable_pairs: frozenset[tuple[str, str]],
    executable_directions: frozenset[tuple[str, str, str]],
    transition_drain: CohortTransitionDrain | None,
) -> IntentRoutingReport:
    """Apply configured exits, authority filters, and deterministic routing."""
    exits = configured_exit_batch(
        symbols=symbols,
        observed_ms=observed_ms,
        poll=poll,
        venues=venues,
        evaluations=evaluations,
        maximum_hold=maximum_hold,
        recipe_exit=recipe_exit,
        profit_lock=profit_lock,
    )
    return _route_after_exits(
        symbols=symbols,
        engines=engines,
        router=router,
        poll=poll,
        operator_symbols=operator_symbols,
        exits=exits,
        executable_pairs=executable_pairs,
        executable_directions=executable_directions,
        transition_drain=transition_drain,
    )


def _route_after_exits(
    *,
    symbols: tuple[str, ...],
    engines: Mapping[str, MultiAssetEngineProtocol],
    router: BidirectionalIntentRouter,
    poll: CohortIntentPoll,
    operator_symbols: set[str],
    exits: CohortExitBatch,
    executable_pairs: frozenset[tuple[str, str]],
    executable_directions: frozenset[tuple[str, str, str]],
    transition_drain: CohortTransitionDrain | None,
) -> IntentRoutingReport:
    positions = engine_position_states(symbols, engines)
    drain_active = transition_drain is not None and transition_drain.active
    admitted = admitted_intents(
        poll.intents,
        closing_symbols=exits.closing_symbols,
        operator_symbols=operator_symbols,
        positions=positions,
        executable_pairs=executable_pairs,
        executable_directions=executable_directions,
        transition_drain_active=drain_active,
    )
    routed = router.route(admitted, positions=positions)
    held = withheld_intents(
        poll.intents,
        timeout_symbols=exits.timeout_symbols,
        recipe_exit_symbols=exits.recipe_exit_symbols,
        profit_lock_exit_symbols=exits.profit_lock_exit_symbols,
        operator_symbols=operator_symbols,
        positions=positions,
        executable_pairs=executable_pairs,
        executable_directions=executable_directions,
        transition_drain_active=drain_active,
    )
    return IntentRoutingReport(
        exits.actions + routed.actions,
        poll.source_withheld + held + routed.withheld,
    )


def admitted_intents(
    intents: tuple[StrategyIntent, ...],
    *,
    closing_symbols: set[str],
    operator_symbols: set[str],
    positions: Mapping[str, PositionState],
    executable_pairs: frozenset[tuple[str, str]],
    executable_directions: frozenset[tuple[str, str, str]],
    transition_drain_active: bool,
) -> tuple[StrategyIntent, ...]:
    """Return intents eligible for the deterministic portfolio router."""
    return tuple(
        intent
        for intent in intents
        if intent.symbol not in closing_symbols
        and intent.symbol not in operator_symbols
        and authority_reason(intent, executable_pairs, executable_directions) is None
        and not transition_drain_holds(intent, positions, transition_drain_active)
    )


def withheld_intents(
    intents: tuple[StrategyIntent, ...],
    *,
    timeout_symbols: set[str],
    recipe_exit_symbols: set[str],
    profit_lock_exit_symbols: set[str],
    operator_symbols: set[str],
    positions: Mapping[str, PositionState],
    executable_pairs: frozenset[tuple[str, str]],
    executable_directions: frozenset[tuple[str, str, str]],
    transition_drain_active: bool,
) -> tuple[WithheldIntent, ...]:
    """Attribute every pre-router exclusion without hiding signal evidence."""
    rows: list[WithheldIntent] = []
    for intent in intents:
        if intent.symbol in timeout_symbols:
            rows.append(WithheldIntent(intent, "maximum_hold_exit_this_cycle"))
            continue
        if intent.symbol in recipe_exit_symbols:
            rows.append(WithheldIntent(intent, "provider_recipe_exit_this_cycle"))
            continue
        if intent.symbol in profit_lock_exit_symbols:
            rows.append(WithheldIntent(intent, "profit_lock_exit_this_cycle"))
            continue
        reason = authority_reason(intent, executable_pairs, executable_directions)
        if reason is not None:
            rows.append(WithheldIntent(intent, reason))
            continue
        if intent.symbol in operator_symbols:
            rows.append(WithheldIntent(intent, "operator_action_this_cycle"))
            continue
        if transition_drain_holds(intent, positions, transition_drain_active):
            rows.append(WithheldIntent(intent, "operator_transition_drain"))
    return tuple(rows)


def authority_reason(
    intent: StrategyIntent,
    executable_pairs: frozenset[tuple[str, str]],
    executable_directions: frozenset[tuple[str, str, str]],
) -> str | None:
    """Return the explicit execution-scope reason for one intent."""
    pair = (intent.strategy_id, intent.symbol)
    if pair not in executable_pairs:
        return "provider_symbol_observe_only"
    direction = (intent.strategy_id, intent.symbol, intent.side)
    if direction not in executable_directions:
        return "provider_direction_observe_only"
    return None


def transition_drain_holds(
    intent: StrategyIntent,
    positions: Mapping[str, PositionState],
    active: bool,
) -> bool:
    """Return whether an active drain blocks this flat-symbol opening."""
    return active and positions[intent.symbol].side is None
