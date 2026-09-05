"""Assemble report-only regime-opposition loss-exit evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_lifecycle_evidence import (
    FillAggregate,
    build_fill_index,
    build_funding_index,
)
from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    text,
)
from hypervector.research.cohort_profit_lock_lifecycle_values import lifecycle_identity
from hypervector.research.cohort_regime_loss_exit_economics import (
    build_closed_loss_exit_payload,
    build_open_loss_exit_payload,
    regime_loss_exit_policy_id,
)
from hypervector.research.cohort_regime_assessment import build_regime_assessment
from hypervector.research.cohort_signal_candidates import is_technical_unavailability
from hypervector.research.cohort_regime_loss_exit_policy import (
    RegimeLossExitObservation,
)
from hypervector.research.cohort_trade_reflection_index import (
    Candle,
    ReflectionEvidenceIndex,
    build_reflection_evidence_index,
    canonical_timeline,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000
_ZERO_TOLERANCE = 1e-12
_DEFAULT_THRESHOLDS_BPS = (20.0, 30.0, 40.0, 50.0)
_DEFAULT_PERSISTENCE = 5


@dataclass(frozen=True)
class RegimeLossExitObservationCoverage:
    """Causal observations and explicit price-coverage gaps for one lifecycle."""

    observations: tuple[RegimeLossExitObservation, ...]
    evaluated_decisions: int
    missing_price_decisions: int


def build_regime_loss_exit_challenger(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    *,
    closed_trades: Sequence[Record],
    open_trades: Sequence[Record],
    current_run_id: str,
    current_profile_fingerprint: str,
    thresholds_bps: Sequence[float] = _DEFAULT_THRESHOLDS_BPS,
    persistence_decisions: int = _DEFAULT_PERSISTENCE,
) -> dict[str, object]:
    """Compare actual exits with a bounded causal loss-exit surface."""
    run_id = text(current_run_id, "loss-exit current run")
    profile = text(current_profile_fingerprint, "loss-exit current profile")
    thresholds = _thresholds(thresholds_bps)
    persistence = _positive_integer(
        persistence_decisions, "loss-exit persistence decisions"
    )
    evidence = build_reflection_evidence_index(cohort_records)
    fills = build_fill_index(asset_records)
    funding = build_funding_index(asset_records)
    closed, opened = _lifecycle_results(
        closed_trades,
        open_trades,
        evidence,
        fills,
        funding,
        thresholds,
        persistence,
    )
    policy_ids = [
        regime_loss_exit_policy_id(persistence, value) for value in thresholds
    ]
    summaries = _summary_sections(closed, policy_ids, run_id, profile)
    return {
        "schema_version": 1,
        "mode": "cohort_regime_opposition_adverse_close_exit_challenger_v1",
        "contract": _contract(),
        "persistence_decisions": persistence,
        "opposition_threshold": -0.5,
        "loss_thresholds_bps": list(thresholds),
        **summaries,
        "closed_lifecycles": closed,
        "open_lifecycles": opened,
        "limitations": _limitations(),
    }


def _lifecycle_results(
    closed_trades: Sequence[Record],
    open_trades: Sequence[Record],
    evidence: ReflectionEvidenceIndex,
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
    thresholds: Sequence[float],
    persistence: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    closed = [
        _closed_result(trade, evidence, fills, funding, thresholds, persistence)
        for trade in closed_trades
    ]
    opened = [
        _open_result(trade, evidence, funding, thresholds, persistence)
        for trade in open_trades
    ]
    return closed, opened


def _summary_sections(
    closed: Sequence[Record],
    policy_ids: Sequence[str],
    run_id: str,
    profile: str,
) -> dict[str, object]:
    profile_rows = [
        row for row in closed if row.get("source_profile_fingerprint") == profile
    ]
    run_rows = [row for row in closed if row.get("source_run_id") == run_id]
    return {
        "all_live": _policy_summaries(closed, policy_ids),
        "current_profile": {
            "profile_fingerprint": profile,
            "policies": _policy_summaries(profile_rows, policy_ids),
        },
        "current_run": {
            "run_id": run_id,
            "policies": _policy_summaries(run_rows, policy_ids),
        },
        "by_provider_symbol": _provider_symbol_summaries(closed, policy_ids),
    }


def _policy_summaries(
    rows: Sequence[Record], policy_ids: Sequence[str]
) -> dict[str, object]:
    return {
        policy_id: summarize_regime_loss_exit_results(rows, policy_id=policy_id)
        for policy_id in policy_ids
    }


def _provider_symbol_summaries(
    rows: Sequence[Record], policy_ids: Sequence[str]
) -> dict[str, object]:
    return {
        f"{strategy}|{symbol}": _policy_summaries(group, policy_ids)
        for (strategy, symbol), group in _groups(rows).items()
    }


def build_regime_loss_exit_observations(
    *,
    side: str,
    provider_evaluations: Mapping[int, Record],
    canonical_evaluations: Mapping[int, Record],
    candles: Mapping[int, Candle],
    entry_timestamp_ms: int,
    end_timestamp_ms: int,
) -> RegimeLossExitObservationCoverage:
    """Join each decision to its completed close and causal next-bar open."""
    _validate_side(side)
    entry_ms = _nonnegative_int(entry_timestamp_ms, "loss-exit entry timestamp")
    end_ms = _nonnegative_int(end_timestamp_ms, "loss-exit end timestamp")
    if end_ms <= entry_ms:
        raise ValueError("loss-exit lifecycle must end after entry")
    provider = _available_evaluations(provider_evaluations)
    canonical = _available_evaluations(canonical_evaluations)
    decisions = sorted(
        decision
        for decision in set(provider).union(canonical)
        if entry_ms < decision < end_ms
    )
    observations: list[RegimeLossExitObservation] = []
    missing_prices = 0
    for decision_ms in decisions:
        _minute(decision_ms, "loss-exit decision timestamp")
        completed = candles.get(decision_ms - _MINUTE_MS)
        next_bar = candles.get(decision_ms)
        if completed is None or next_bar is None:
            missing_prices += 1
            continue
        score = _support_score(
            side,
            provider.get(decision_ms),
            canonical.get(decision_ms),
        )
        observations.append(
            RegimeLossExitObservation(
                decision_time_ms=decision_ms,
                completed_close_price=completed.close,
                next_open_price=next_bar.open,
                structure_support_score=score,
            )
        )
    return RegimeLossExitObservationCoverage(
        tuple(observations), len(decisions), missing_prices
    )


def _available_evaluations(values: Mapping[int, Record]) -> dict[int, Record]:
    return {
        decision_ms: row
        for decision_ms, row in values.items()
        if not is_technical_unavailability(row)
    }


def summarize_regime_loss_exit_results(
    rows: Sequence[Record], *, policy_id: str
) -> dict[str, object]:
    """Summarize eligible candidate economics without dropping non-triggers."""
    policy = text(policy_id, "loss-exit policy id")
    eligible = [row for row in rows if row.get("status") == "eligible"]
    candidates: list[float] = []
    actuals: list[float] = []
    triggered = 0
    for row in eligible:
        policies = mapping(row.get("policies"), "loss-exit policies")
        result = mapping(policies.get(policy), f"loss-exit policy {policy}")
        actuals.append(number(row.get("actual_net_pnl_usd"), "actual net PnL"))
        candidates.append(
            number(result.get("estimated_net_pnl_usd"), "candidate net PnL")
        )
        triggered += int(result.get("status") == "triggered")
    candidate_total = sum(candidates)
    actual_total = sum(actuals)
    wins = sum(value > _ZERO_TOLERANCE for value in candidates)
    losses = sum(value < -_ZERO_TOLERANCE for value in candidates)
    gross_wins = sum(max(0.0, value) for value in candidates)
    gross_losses = abs(sum(min(0.0, value) for value in candidates))
    return {
        "policy_id": policy,
        "eligible_lifecycles": len(eligible),
        "withheld_lifecycles": len(rows) - len(eligible),
        "triggered_lifecycles": triggered,
        "retained_actual_lifecycles": len(eligible) - triggered,
        "actual_net_pnl_usd": actual_total,
        "candidate_net_pnl_usd": candidate_total,
        "candidate_minus_actual_net_usd": candidate_total - actual_total,
        "candidate_wins": wins,
        "candidate_losses": losses,
        "candidate_breakeven": len(candidates) - wins - losses,
        "candidate_profit_factor": _profit_factor(gross_wins, gross_losses, candidates),
    }


def _closed_result(
    trade: Record,
    evidence: ReflectionEvidenceIndex,
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
    thresholds: Sequence[float],
    persistence: int,
) -> dict[str, object]:
    identity = lifecycle_identity(trade)
    symbol_funding = funding.get(identity[1], {})
    entry = mapping(trade.get("entry"), "closed loss-exit entry")
    exit_record = mapping(trade.get("exit"), "closed loss-exit exit")
    coverage = _lifecycle_coverage(
        evidence,
        strategy_id=identity[2],
        symbol=identity[1],
        side=identity[3],
        entry_timestamp_ms=nonnegative_int(
            entry.get("venue_timestamp_ms"), "closed loss-exit entry time"
        ),
        end_timestamp_ms=nonnegative_int(
            exit_record.get("venue_timestamp_ms"), "closed loss-exit exit time"
        ),
    )
    return build_closed_loss_exit_payload(
        trade,
        fills,
        symbol_funding,
        coverage.observations,
        evaluated_decisions=coverage.evaluated_decisions,
        missing_price_decisions=coverage.missing_price_decisions,
        thresholds_bps=thresholds,
        persistence_decisions=persistence,
    )


def _open_result(
    trade: Record,
    evidence: ReflectionEvidenceIndex,
    funding: Mapping[str, Mapping[int, float]],
    thresholds: Sequence[float],
    persistence: int,
) -> dict[str, object]:
    symbol = text(trade.get("symbol"), "open loss-exit symbol")
    strategy = text(trade.get("strategy_id"), "open loss-exit strategy")
    side = text(trade.get("side"), "open loss-exit side")
    _validate_side(side)
    entry = mapping(trade.get("entry"), "open loss-exit entry")
    episode = mapping(trade.get("regime_opposition_episode"), "open opposition episode")
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "open entry time")
    end_ms = nonnegative_int(episode.get("end_timestamp_ms"), "open evidence end")
    coverage = _lifecycle_coverage(
        evidence,
        strategy_id=strategy,
        symbol=symbol,
        side=side,
        entry_timestamp_ms=entry_ms,
        end_timestamp_ms=end_ms,
    )
    symbol_funding = funding.get(symbol, {})
    return build_open_loss_exit_payload(
        trade,
        symbol_funding,
        coverage.observations,
        evaluated_decisions=coverage.evaluated_decisions,
        missing_price_decisions=coverage.missing_price_decisions,
        thresholds_bps=thresholds,
        persistence_decisions=persistence,
    )


def _support_score(
    side: str, provider: Record | None, canonical: Record | None
) -> float | None:
    if provider is None or canonical is None:
        return None
    contexts = {
        "signal_provider": {**provider, "status": "observed"},
        "canonical_regime": {**canonical, "status": "observed"},
    }
    value = build_regime_assessment(side, contexts).get("structure_support_score")
    return None if value is None else number(value, "loss-exit support score")


def _lifecycle_coverage(
    evidence: ReflectionEvidenceIndex,
    *,
    strategy_id: str,
    symbol: str,
    side: str,
    entry_timestamp_ms: int,
    end_timestamp_ms: int,
) -> RegimeLossExitObservationCoverage:
    provider = _timeline_evaluations(evidence, strategy_id, symbol)
    canonical = {
        nonnegative_int(row.get("decision_time_ms"), "canonical decision time"): row
        for row in canonical_timeline(evidence, symbol)
    }
    return build_regime_loss_exit_observations(
        side=side,
        provider_evaluations=provider,
        canonical_evaluations=canonical,
        candles=evidence.candles.get(symbol, {}),
        entry_timestamp_ms=entry_timestamp_ms,
        end_timestamp_ms=end_timestamp_ms,
    )


def _timeline_evaluations(
    evidence: ReflectionEvidenceIndex, strategy_id: str, symbol: str
) -> dict[int, Record]:
    return {
        nonnegative_int(row.get("decision_time_ms"), "evaluation decision time"): row
        for row in evidence.timelines.get((strategy_id, symbol), ())
    }


def _groups(rows: Sequence[Record]) -> dict[tuple[str, str], list[Record]]:
    output: dict[tuple[str, str], list[Record]] = {}
    for row in rows:
        key = (
            text(row.get("strategy_id"), "loss-exit strategy"),
            text(row.get("symbol"), "loss-exit symbol"),
        )
        output.setdefault(key, []).append(row)
    return output


def _thresholds(values: Sequence[float]) -> tuple[float, ...]:
    thresholds = tuple(
        _positive_number(value, "loss-exit threshold bps") for value in values
    )
    if not thresholds or len(thresholds) != len(set(thresholds)):
        raise ValueError("loss-exit thresholds must be nonempty and unique")
    if tuple(sorted(thresholds)) != thresholds:
        raise ValueError("loss-exit thresholds must be increasing")
    return thresholds


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "portfolio_pnl_claimed": False,
    }


def _limitations() -> list[str]:
    return [
        "the policy was formed after observing persistent opposition in an open v14 cluster",
        "signals use completed one-minute closes and model exit at the next bar open",
        "closed paths reuse each actual exit fill-to-reference ratio and fee rate",
        "open paths use adverse entry-slippage magnitude as an exit-slippage proxy",
        "missing decisions reset persistence and missing price pairs remain explicit",
        "overlapping lifecycles are not an independent shared-portfolio equity path",
        "small or one-sided samples cannot establish exit edge or execution authority",
        "the challenger cannot place, close, resize, rank, gate, or promote a trade",
    ]


def _profit_factor(
    gross_wins: float, gross_losses: float, candidates: Sequence[float]
) -> float | None:
    if not candidates:
        return None
    if gross_losses <= _ZERO_TOLERANCE:
        return None
    return gross_wins / gross_losses


def _validate_side(side: str) -> None:
    if side not in {"long", "short"}:
        raise ValueError("loss-exit side must be long or short")


def _positive_integer(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be positive")
    return value


def _positive_number(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed


def _nonnegative_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _minute(value: int, label: str) -> int:
    parsed = _nonnegative_int(value, label)
    if parsed % _MINUTE_MS:
        raise ValueError(f"{label} must align to a minute")
    return parsed
