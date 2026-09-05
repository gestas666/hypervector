#!/usr/bin/env python3
"""Continuously consolidate the execution-incapable V58 research lane."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import time
from typing import Protocol

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import RequestException

from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
    load_v58_successor_observer_status,
)
from hypervector.research.report_only_lifecycle_watch import (
    report_transient_watch_failure,
    run_watch_loop,
)
from hypervector.research.v58_continuous_improvement import (
    LifecycleEvidence,
    RouteOpportunityCollection,
    V58LifecycleSources,
    build_v58_continuous_improvement,
    load_v58_lifecycle_evidence,
    load_v58_route_opportunities,
)
from hypervector.research.v58_continuous_cli import build_v58_continuous_parser
from hypervector.research.v58_btc_long_coverage_context import (
    attach_v58_btc_long_coverage_result,
)
from hypervector.research.v58_brentoil_continuous_context import (
    BrentoilContinuousContext,
    attach_v58_brentoil_continuous_context,
    load_v58_brentoil_continuous_context,
)
from hypervector.research.v58_active_route_lifecycle_context import (
    V58ActiveRouteContext,
    attach_v58_active_route_lifecycle_context,
    load_v58_active_route_lifecycle_context,
)
from hypervector.research.v58_current_funding_context import (
    CurrentFundingContext,
    current_funding_context_payload,
    load_resilient_live_v58_current_funding_context,
)
from hypervector.research.v58_continuous_generator_paths import (
    require_unchanged_v58_generators as _require_unchanged,
    v58_continuous_generator_payload as _generator_payload,
    v58_continuous_generator_paths,
    v58_continuous_generator_references as _generator_references_for_paths,
)
from hypervector.research.v58_current_investigation import (
    attach_live_closed_lifecycles_to_ledger,
    attach_live_open_lifecycles_to_ledger,
    refresh_current_investigation as _refresh_investigation,
)
from hypervector.research.v58_eth_open_path_context import (
    EthOpenPathContext,
    attach_eth_source_history_to_ledger,
    eth_open_path_context_payload,
    load_v58_eth_open_path_context_with_history,
)
from hypervector.research.v58_eth_exit_research_context import (
    EthExitResearchContext,
    eth_exit_research_payload,
    load_v58_eth_exit_research_context,
)
from hypervector.research.v58_eth_profit_lock_context import (
    EthProfitLockContext,
    eth_profit_lock_context_payload,
    load_v58_eth_profit_lock_context,
)
from hypervector.research.v58_eth_risk_normalized_lock_context import (
    EthRiskNormalizedLockContext,
    eth_risk_normalized_lock_context_payload,
    load_v58_eth_risk_normalized_lock_context,
)
from hypervector.research.v58_eth_risk_lock_evidence import (
    attach_eth_risk_lock_evidence_to_ledger,
)
from hypervector.research.v58_eth_duration_evidence import (
    attach_v58_eth_duration_evidence,
)
from hypervector.research.v58_eth_historical_funding_context import (
    attach_v58_eth_historical_funding_context,
)
from hypervector.research.v58_sp500_gap_recovery_context import (
    Sp500GapRecoveryContext,
    load_v58_sp500_gap_context_with_history,
    sp500_gap_recovery_context_payload,
)
from hypervector.research.v58_sp500_recovery_ledger import (
    attach_sp500_recovery_to_ledger,
)
from hypervector.research.v58_continuous_liquidity_context import (
    LiquidityContext,
    liquidity_context_payload,
    load_v58_liquidity_context,
)
from hypervector.research.v58_live_backend_context import (
    LiveBackendContext,
    load_v58_live_backend_context,
)
from hypervector.research.v58_execution_mandate_context import (
    ExecutionMandateContext,
    load_v58_execution_mandate_context,
)
from hypervector.research.v58_continuous_live_attachment import (
    attach_v58_continuous_live_contexts,
)
from hypervector.research.v58_venue_state_context import (
    VenueStateContext,
    load_v58_venue_state_context,
)
from hypervector.research.v58_continuous_portfolio_context import (
    PortfolioOpportunityContext,
    load_v58_portfolio_context,
    portfolio_context_payload,
)
from hypervector.research.v58_continuous_regime_context import (
    RegimeContextCollection,
    load_v58_regime_context,
    regime_context_payload,
)
from hypervector.research.v58_continuous_runtime_context import (
    RuntimeContext,
    load_v58_runtime_context,
    runtime_context_payload,
)
from hypervector.research.v58_continuous_return_context import (
    ReturnInteractionContext,
    load_v58_return_context,
    return_context_payload,
)
from hypervector.research.v58_continuous_risk_context import (
    RiskContext,
    current_equity_risk_context_payload,
    load_v58_risk_context,
)
from hypervector.research.v58_continuous_transient import (
    CONTINUOUS_TRANSIENT_RETRY_SECONDS,
    continuous_transient_failure_reason,
)
from hypervector.runtime_lock import cohort_checkpoint_runtime_lock

ObserverLoader = Callable[..., SuccessorObserverEvidence]
LifecycleLoader = Callable[..., tuple[LifecycleEvidence, ...]]
OpportunityLoader = Callable[..., RouteOpportunityCollection]
EthPathLoader = Callable[..., EthOpenPathContext]
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _AuthorityContext(Protocol):
    execution_authority: str
    evidence: Mapping[str, object]


Contexts = tuple[_AuthorityContext, ...]
LiveContexts = tuple[
    LiveBackendContext,
    ExecutionMandateContext,
    V58ActiveRouteContext,
    BrentoilContinuousContext,
    VenueStateContext,
]


@dataclass(frozen=True)
class _ContinuousLoaders:
    observer: ObserverLoader = load_v58_successor_observer_status
    lifecycle: LifecycleLoader = load_v58_lifecycle_evidence
    opportunity: OpportunityLoader = load_v58_route_opportunities
    active_routes: Callable[..., V58ActiveRouteContext] = (
        load_v58_active_route_lifecycle_context
    )
    regime: Callable[..., RegimeContextCollection] = load_v58_regime_context
    portfolio: Callable[..., PortfolioOpportunityContext] = load_v58_portfolio_context
    runtime: Callable[..., RuntimeContext] = load_v58_runtime_context
    backend: Callable[..., LiveBackendContext] = load_v58_live_backend_context
    mandate: Callable[..., ExecutionMandateContext] = load_v58_execution_mandate_context
    brentoil: Callable[..., BrentoilContinuousContext] = (
        load_v58_brentoil_continuous_context
    )
    venue: Callable[..., VenueStateContext] = load_v58_venue_state_context
    returns: Callable[..., ReturnInteractionContext] = load_v58_return_context
    risk: Callable[..., RiskContext] = load_v58_risk_context
    liquidity: Callable[..., LiquidityContext] = load_v58_liquidity_context
    eth_path: EthPathLoader = load_v58_eth_open_path_context_with_history
    funding: Callable[..., CurrentFundingContext] = (
        load_resilient_live_v58_current_funding_context
    )
    eth_exit: Callable[..., EthExitResearchContext] = load_v58_eth_exit_research_context
    eth_profit_lock: Callable[..., EthProfitLockContext] = (
        load_v58_eth_profit_lock_context
    )
    eth_risk_lock: Callable[..., EthRiskNormalizedLockContext] = (
        load_v58_eth_risk_normalized_lock_context
    )
    sp500_recovery: Callable[..., Sp500GapRecoveryContext] = (
        load_v58_sp500_gap_context_with_history
    )


_CONTEXT_LABELS = (
    "regime_context portfolio_opportunity_context runtime_context "
    "return_interaction_context risk_context liquidity_context "
    "eth_open_path_context current_funding_context eth_exit_research_context "
    "eth_profit_lock_context eth_risk_normalized_lock_context sp500_gap_recovery_context"
).split()


def build_parser() -> argparse.ArgumentParser:
    """Return the V58 authority-none consolidation parser."""
    return build_v58_continuous_parser(__doc__)


def refresh(
    args: argparse.Namespace,
    *,
    loaders: _ContinuousLoaders = _ContinuousLoaders(),
    generators: Mapping[Path, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Validate and atomically publish one current V58 research state."""
    generated_at = datetime.now(UTC)
    frozen_generators = _generator_references() if generators is None else generators
    observer = loaders.observer(
        args.observer,
        observed_at=generated_at,
        maximum_age_seconds=args.maximum_age_seconds,
        config_path=args.config,
    )
    lifecycles = _load_lifecycles(args, observer, generated_at, loaders.lifecycle)
    opportunities = loaders.opportunity(args.observer, observer_status=observer.status)
    backend, mandate, active_routes, brentoil, venue = _load_live_contexts(
        args, observer, generated_at, loaders
    )
    contexts = _load_contexts(args, observer, generated_at, loaders)
    report = _create_report(
        observer,
        lifecycles,
        opportunities,
        generated_at,
        contexts,
        backend,
        mandate,
        venue,
        active_routes,
    )
    attach_v58_brentoil_continuous_context(report, brentoil)
    attach_v58_eth_duration_evidence(report, args.eth_duration_checkpoint)
    attach_v58_eth_historical_funding_context(
        report, args.eth_historical_funding_stress
    )
    attach_v58_btc_long_coverage_result(
        report,
        args.btc_long_coverage_result,
        project_root=_PROJECT_ROOT,
    )
    return _publish(args.out, report, frozen_generators)


def _load_live_contexts(
    args: argparse.Namespace,
    observer: SuccessorObserverEvidence,
    generated_at: datetime,
    loaders: _ContinuousLoaders,
) -> LiveContexts:
    backend = loaders.backend(
        args.live_checkpoint,
        observed_at=generated_at,
        maximum_age_seconds=args.maximum_age_seconds,
    )
    mandate = loaders.mandate(args.live_checkpoint)
    active_routes = loaders.active_routes(
        args.active_route_overrides,
        args.live_checkpoint,
        project_root=_PROJECT_ROOT,
        observed_at=generated_at,
        maximum_age_seconds=args.maximum_age_seconds,
    )
    brentoil = loaders.brentoil(
        args.brentoil,
        observed_at=generated_at,
        maximum_age_seconds=args.maximum_age_seconds,
        profile_id=backend.profile_id,
        profile_fingerprint=backend.profile_fingerprint,
        run_id=backend.run_id,
    )
    venue = loaders.venue(
        args.venue_preflight,
        observed_at=generated_at,
        maximum_age_seconds=args.maximum_age_seconds,
        active_profile_id=backend.profile_id,
        active_profile_fingerprint=backend.profile_fingerprint,
        candidate_profile_id=observer.status["profile_id"],
        candidate_profile_fingerprint=observer.status["base_profile_fingerprint"],
        candidate_symbols=tuple(observer.status["symbols"]),
    )
    return backend, mandate, active_routes, brentoil, venue


def _load_lifecycles(
    args: argparse.Namespace,
    observer: SuccessorObserverEvidence,
    generated_at: datetime,
    loader: LifecycleLoader,
) -> tuple[LifecycleEvidence, ...]:
    return loader(
        V58LifecycleSources(args.btc, args.eth, args.hype, args.sp500),
        observer_status=observer.status,
        observed_at=generated_at,
        maximum_age_seconds=args.maximum_age_seconds,
    )


def _load_contexts(
    args: argparse.Namespace,
    observer: SuccessorObserverEvidence,
    generated_at: datetime,
    loaders: _ContinuousLoaders,
) -> Contexts:
    exit_research = loaders.eth_exit(args.eth_exit_journal, args.eth_exit_duration)
    return (
        loaders.regime(args.observer, observer_status=observer.status),
        loaders.portfolio(args.config, observer=observer),
        loaders.runtime(args.observer, args.config, observer=observer),
        loaders.returns(observer=observer),
        loaders.risk(args.config, args.stress),
        loaders.liquidity(args.config, observer=observer),
        loaders.eth_path(args.eth),
        loaders.funding(args.config, args.stress, observed_at=generated_at),
        exit_research,
        loaders.eth_profit_lock(args.eth, exit_research),
        loaders.eth_risk_lock(args.live_checkpoint, args.eth_risk_lock_disposition),
        loaders.sp500_recovery(args.sp500_recovery, args.sp500_recovery_journal),
    )


def _create_report(
    observer: SuccessorObserverEvidence,
    lifecycles: tuple[LifecycleEvidence, ...],
    opportunities: RouteOpportunityCollection,
    generated_at: datetime,
    contexts: Contexts,
    backend: LiveBackendContext,
    mandate: ExecutionMandateContext,
    venue: VenueStateContext,
    active_routes: V58ActiveRouteContext,
) -> dict[str, object]:
    report = build_v58_continuous_improvement(
        observer, *lifecycles, opportunities, generated_at=generated_at
    )
    _attach_contexts(report, *contexts, venue=venue)
    attach_v58_continuous_live_contexts(report, backend, mandate, venue)
    attach_v58_active_route_lifecycle_context(report, active_routes)
    attach_live_closed_lifecycles_to_ledger(report, backend.closed_lifecycles)
    attach_live_open_lifecycles_to_ledger(report, backend.open_lifecycles)
    _refresh_investigation(
        report, (*lifecycles, *active_routes.items), opportunities, backend
    )
    return report


def _publish(
    path: Path,
    report: dict[str, object],
    generators: Mapping[Path, Mapping[str, object]],
) -> dict[str, object]:
    report["generator_identity"] = _generator_payload(generators)
    _require_unchanged(generators)
    write_atomic_json(path, report)
    return report


def _attach_contexts(
    report: dict[str, object],
    regimes: RegimeContextCollection,
    portfolio: PortfolioOpportunityContext,
    runtime: RuntimeContext,
    returns: ReturnInteractionContext,
    risk: RiskContext,
    liquidity: LiquidityContext,
    eth_path: EthOpenPathContext,
    funding: CurrentFundingContext,
    eth_exit_research: EthExitResearchContext,
    eth_profit_lock: EthProfitLockContext,
    eth_risk_lock: EthRiskNormalizedLockContext,
    sp500_recovery: Sp500GapRecoveryContext,
    venue: VenueStateContext,
) -> None:
    contexts = (
        regimes,
        portfolio,
        runtime,
        returns,
        risk,
        liquidity,
        eth_path,
        funding,
        eth_exit_research,
        eth_profit_lock,
        eth_risk_lock,
        sp500_recovery,
    )
    _require_none_authority(_CONTEXT_LABELS, contexts)
    report["regime_context"] = regime_context_payload(regimes)
    report["portfolio_opportunity_context"] = portfolio_context_payload(portfolio)
    report["runtime_context"] = runtime_context_payload(runtime)
    report["return_interaction_context"] = return_context_payload(returns)
    report["risk_context"] = _current_equity_risk_payload(risk, venue)
    report["liquidity_context"] = liquidity_context_payload(liquidity)
    eth_path_payload = eth_open_path_context_payload(eth_path)
    report["eth_open_path_context"] = eth_path_payload
    attach_eth_source_history_to_ledger(report["hypothesis_ledger"], eth_path_payload)
    report["current_funding_context"] = current_funding_context_payload(funding)
    report["eth_exit_research_context"] = eth_exit_research_payload(eth_exit_research)
    report["eth_profit_lock_context"] = eth_profit_lock_context_payload(eth_profit_lock)
    _attach_eth_risk_lock_context(report, eth_risk_lock)
    recovery_payload = sp500_gap_recovery_context_payload(sp500_recovery)
    report["sp500_gap_recovery_context"] = recovery_payload
    attach_sp500_recovery_to_ledger(report, recovery_payload)
    _attach_context_evidence(report, contexts)


def _attach_eth_risk_lock_context(
    report: dict[str, object], context: EthRiskNormalizedLockContext
) -> None:
    payload = eth_risk_normalized_lock_context_payload(context)
    report["eth_risk_normalized_lock_context"] = payload
    attach_eth_risk_lock_evidence_to_ledger(report["hypothesis_ledger"], payload)


def _current_equity_risk_payload(
    risk: RiskContext, venue: VenueStateContext
) -> dict[str, object]:
    return current_equity_risk_context_payload(
        risk,
        actual_account_value_usd=venue.actual_account_value_usd,
        sizing_reference_equity_usd=venue.sizing_reference_equity_usd,
        observed_at_utc=venue.observed_at_utc,
        fresh=venue.preflight_fresh,
    )


def _attach_context_evidence(report: dict[str, object], contexts: Contexts) -> None:
    evidence = report.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("V58 report evidence is invalid")
    for label, context in zip(_CONTEXT_LABELS, contexts, strict=True):
        evidence[label] = dict(context.evidence)


def _require_none_authority(
    labels: Sequence[str], contexts: Sequence[_AuthorityContext]
) -> None:
    for label, context in zip(labels, contexts, strict=True):
        if context.execution_authority != "none":
            raise ValueError(f"V58 {label} context has execution authority")


def run_monitor(
    args: argparse.Namespace,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Refresh while enforcing one loaded consolidation identity."""
    frozen = _generator_references()

    def cycle() -> None:
        _require_unchanged(frozen)
        refresh(args, generators=frozen)
        _require_unchanged(frozen)

    return run_watch_loop(
        cycle,
        interval_seconds=args.interval_seconds,
        max_cycles=args.max_cycles,
        sleep_fn=sleep_fn,
        transient_exceptions=(RequestException, ClientError, ServerError, ValueError),
        transient_reason=continuous_transient_failure_reason,
        transient_reporter=report_transient_watch_failure,
        transient_retry_seconds=CONTINUOUS_TRANSIENT_RETRY_SECONDS,
    )


def _generator_references() -> dict[Path, dict[str, object]]:
    return _generator_references_for_paths(v58_continuous_generator_paths(__file__))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the singleton V58 consolidation without execution authority."""
    args = build_parser().parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with cohort_checkpoint_runtime_lock(args.out):
            return run_monitor(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
