"""Report-only dual-timeframe reversal exits for live cohort lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.live.canonical_regime_telemetry import CANONICAL_REGIME_STRATEGIES
from hypervector.research.cohort_dual_mtf_reversal_exit_policy import (
    DualMtfReversalExitResult,
    DualMtfReversalObservation,
    evaluate_dual_mtf_reversal_exit,
)
from hypervector.research.cohort_lifecycle_evidence import (
    FillAggregate,
    build_fill_index,
    build_funding_index,
    funding_sum,
)
from hypervector.research.cohort_live_audit_values import mapping, number, text
from hypervector.research.cohort_dual_mtf_reversal_exit_reporting import (
    build_dual_mtf_reversal_report,
    summarize_dual_mtf_reversal_results as _summarize_results,
)
from hypervector.research.cohort_profit_lock_lifecycle_values import (
    lifecycle_economics,
    lifecycle_identity,
)
from hypervector.research.cohort_profit_lock_results import ProfitLockEconomics
from hypervector.research.cohort_trade_reflection_index import (
    Candle,
    ReflectionEvidenceIndex,
    build_reflection_evidence_index,
)
from hypervector.research.v39_effective_episodes import (
    build_effective_episode_evidence,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000
_ZERO_TOLERANCE = 1e-12
_DEFAULT_PERSISTENCE = (1, 3, 5)


@dataclass(frozen=True)
class DualMtfReversalCoverage:
    """Causal observations and explicit missing-price decisions."""

    observations: tuple[DualMtfReversalObservation, ...]
    evaluated_decisions: int
    missing_price_decisions: int


def build_dual_mtf_reversal_exit_challenger(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    *,
    closed_trades: Sequence[Record],
    current_run_id: str,
    current_profile_fingerprint: str,
    open_trades: Sequence[Record] = (),
    persistence_surface: Sequence[int] = _DEFAULT_PERSISTENCE,
) -> dict[str, object]:
    """Compare actual closes with every frozen dual-MTF persistence cell."""
    run_id = text(current_run_id, "dual-MTF current run")
    profile = text(current_profile_fingerprint, "dual-MTF current profile")
    surface = _persistence_surface(persistence_surface)
    evidence = build_reflection_evidence_index(cohort_records)
    fills = build_fill_index(asset_records)
    funding = build_funding_index(asset_records)
    results = _closed_results(closed_trades, evidence, fills, funding, surface)
    episodes = build_effective_episode_evidence(closed_trades, open_trades, run_id)
    policies = tuple(dual_mtf_policy_id(value) for value in surface)
    return build_dual_mtf_reversal_report(
        results, episodes, policies, surface, run_id, profile
    )


def build_dual_mtf_reversal_observations(
    *,
    side: str,
    evaluations: Mapping[int, Record],
    candles: Mapping[int, Candle],
    funding: Mapping[int, float],
    entry_timestamp_ms: int,
    end_timestamp_ms: int,
    entry_price: float,
    size: float,
    entry_fee_usd: float,
) -> DualMtfReversalCoverage:
    """Join completed regimes to next opens and prior cost-clearance state."""
    _validate_observation_inputs(
        side, entry_timestamp_ms, end_timestamp_ms, entry_price, size, entry_fee_usd
    )
    decisions = sorted(
        value for value in evaluations if entry_timestamp_ms < value < end_timestamp_ms
    )
    rows: list[DualMtfReversalObservation] = []
    missing = 0
    cleared = False
    for decision_ms in decisions:
        completed = candles.get(decision_ms - _MINUTE_MS)
        next_bar = candles.get(decision_ms)
        if completed is None or next_bar is None:
            missing += 1
            continue
        estimated_net = _completed_close_net(
            side,
            completed.close,
            entry_timestamp_ms,
            decision_ms,
            entry_price,
            size,
            entry_fee_usd,
            funding,
        )
        rows.append(
            _observation(
                evaluations[decision_ms], completed, next_bar, cleared, estimated_net
            )
        )
        cleared = cleared or estimated_net > _ZERO_TOLERANCE
    return DualMtfReversalCoverage(tuple(rows), len(decisions), missing)


def summarize_dual_mtf_reversal_results(
    rows: Sequence[Record], *, policy_id: str
) -> dict[str, object]:
    """Expose the stable public summary API from the reporting module."""
    return _summarize_results(rows, policy_id=policy_id)


def _closed_results(
    trades: Sequence[Record],
    evidence: ReflectionEvidenceIndex,
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
    surface: tuple[int, ...],
) -> list[dict[str, object]]:
    rows = [
        _closed_result(trade, evidence, fills, funding, surface) for trade in trades
    ]
    return sorted(rows, key=lambda row: number(row["exit_timestamp_ms"], "exit"))


def _closed_result(
    trade: Record,
    evidence: ReflectionEvidenceIndex,
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
    surface: tuple[int, ...],
) -> dict[str, object]:
    identity = lifecycle_identity(trade)
    symbol_funding = funding.get(identity[1], {})
    economics = lifecycle_economics(trade, fills, symbol_funding)
    evaluations = _exact_canonical_evaluations(evidence, identity[4], identity[1])
    coverage = build_dual_mtf_reversal_observations(
        side=identity[3],
        evaluations=evaluations,
        candles=evidence.candles.get(identity[1], {}),
        funding=symbol_funding,
        entry_timestamp_ms=economics.entry_timestamp_ms,
        end_timestamp_ms=economics.exit_timestamp_ms,
        entry_price=economics.entry_price,
        size=economics.size,
        entry_fee_usd=economics.entry_fee_usd,
    )
    policies = _closed_policies(trade, economics, symbol_funding, coverage, surface)
    return {
        "status": "eligible"
        if coverage.observations
        else "withheld_no_causal_observations",
        "lifecycle_id": identity[0],
        "symbol": identity[1],
        "strategy_id": identity[2],
        "side": identity[3],
        "source_run_id": identity[4],
        "source_profile_fingerprint": identity[5],
        "exit_timestamp_ms": economics.exit_timestamp_ms,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "evaluated_decisions": coverage.evaluated_decisions,
        "observed_decisions": len(coverage.observations),
        "missing_price_decisions": coverage.missing_price_decisions,
        "policies": policies,
    }


def _closed_policies(
    trade: Record,
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    coverage: DualMtfReversalCoverage,
    surface: Sequence[int],
) -> dict[str, object]:
    if not coverage.observations:
        return {
            dual_mtf_policy_id(value): _withheld_policy(economics, value)
            for value in surface
        }
    return {
        dual_mtf_policy_id(value): _closed_policy(
            trade, economics, funding, coverage.observations, value
        )
        for value in surface
    }


def _closed_policy(
    trade: Record,
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    observations: Sequence[DualMtfReversalObservation],
    persistence: int,
) -> dict[str, object]:
    result = evaluate_dual_mtf_reversal_exit(
        side=text(trade.get("side"), "dual-MTF side"),
        observations=observations,
        persistence_decisions=persistence,
    )
    if result.state != "triggered":
        return _retained_policy(economics, persistence, result)
    reference = number(result.exit_reference_price, "dual-MTF exit reference")
    exit_price = _estimated_exit_price(trade, reference)
    timestamp = _required_timestamp(result.trigger_decision_time_ms)
    candidate = _counterfactual_net(trade, economics, funding, timestamp, exit_price)
    return {
        **_policy_declaration(persistence),
        **_result_fields(result),
        "status": "triggered",
        "estimated_exit_price": exit_price,
        "estimated_net_pnl_usd": candidate,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "estimated_minus_actual_net_usd": candidate - economics.actual_net_pnl_usd,
    }


def _observation(
    evaluation: Record,
    completed: Candle,
    next_bar: Candle,
    cleared: bool,
    estimated_net: float,
) -> DualMtfReversalObservation:
    metrics = mapping(
        mapping(evaluation.get("readiness"), "readiness").get("metrics"), "metrics"
    )
    return DualMtfReversalObservation(
        decision_time_ms=_required_timestamp(evaluation.get("decision_time_ms")),
        completed_close_price=completed.close,
        next_open_price=next_bar.open,
        direction_1m=_state_direction(
            evaluation.get("state_1m"), metrics.get("regime_1m_ema_gap_bps")
        ),
        direction_5m=_state_direction(
            evaluation.get("state_5m"), metrics.get("regime_5m_ema_gap_bps")
        ),
        cost_cleared_before_decision=cleared,
        estimated_net_at_completed_close_usd=estimated_net,
    )


def _exact_canonical_evaluations(
    evidence: ReflectionEvidenceIndex, run_id: str, symbol: str
) -> dict[int, Record]:
    output: dict[int, Record] = {}
    for strategy in CANONICAL_REGIME_STRATEGIES:
        values = [
            (decision, value)
            for (run, source, asset, decision), value in evidence.evaluations.items()
            if run == run_id and source == strategy and asset == symbol
        ]
        for decision, value in sorted(values):
            output.setdefault(decision, value)
    return output


def dual_mtf_policy_id(persistence: int) -> str:
    """Return the stable identifier for one declared persistence cell."""
    return f"dual_mtf_p{_positive_integer(persistence)}"


def _completed_close_net(
    side: str,
    close: float,
    entry_ms: int,
    decision_ms: int,
    entry: float,
    size: float,
    entry_fee: float,
    funding: Mapping[int, float],
) -> float:
    direction = 1.0 if side == "long" else -1.0
    fee_rate = entry_fee / (entry * size)
    gross = direction * (close - entry) * size
    cashflow = funding_sum(funding, entry_ms, decision_ms)
    return gross - entry_fee - close * size * fee_rate + cashflow


def _counterfactual_net(
    trade: Record,
    economics: ProfitLockEconomics,
    funding: Mapping[int, float],
    timestamp_ms: int,
    exit_price: float,
) -> float:
    side = text(trade.get("side"), "dual-MTF side")
    direction = 1.0 if side == "long" else -1.0
    gross = direction * (exit_price - economics.entry_price) * economics.size
    fee_rate = economics.entry_fee_usd / (economics.entry_price * economics.size)
    exit_fee = exit_price * economics.size * fee_rate
    cashflow = funding_sum(funding, economics.entry_timestamp_ms, timestamp_ms)
    return gross - economics.entry_fee_usd - exit_fee + cashflow


def _estimated_exit_price(trade: Record, reference: float) -> float:
    entry = mapping(trade.get("entry"), "dual-MTF entry")
    slippage = abs(number(entry.get("slippage_bps"), "entry slippage")) / 10_000.0
    if slippage >= 1.0:
        raise ValueError("entry slippage cannot reach 100 percent")
    return reference * (
        1.0 - slippage if trade.get("side") == "long" else 1.0 + slippage
    )


def _retained_policy(
    economics: ProfitLockEconomics,
    persistence: int,
    result: DualMtfReversalExitResult,
) -> dict[str, object]:
    return {
        **_policy_declaration(persistence),
        **_result_fields(result),
        "status": "retained_actual_exit",
        "estimated_exit_price": economics.actual_exit_price,
        "estimated_net_pnl_usd": economics.actual_net_pnl_usd,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "estimated_minus_actual_net_usd": 0.0,
    }


def _withheld_policy(
    economics: ProfitLockEconomics, persistence: int
) -> dict[str, object]:
    return {
        **_policy_declaration(persistence),
        "status": "withheld_no_causal_observations",
        "trigger_decision_time_ms": None,
        "estimated_exit_price": None,
        "estimated_net_pnl_usd": None,
        "actual_net_pnl_usd": economics.actual_net_pnl_usd,
        "estimated_minus_actual_net_usd": None,
    }


def _policy_declaration(persistence: int) -> dict[str, object]:
    return {
        "policy_id": dual_mtf_policy_id(persistence),
        "persistence_decisions": persistence,
        "signal_clock": "completed_1m_and_completed_5m_state_at_1m_decision",
        "execution_reference": "next_1m_open",
        "cost_clearance": "prior_decision_estimated_close_net_positive",
    }


def _result_fields(result: DualMtfReversalExitResult) -> dict[str, object]:
    return {
        "reason": result.reason,
        "trigger_decision_time_ms": result.trigger_decision_time_ms,
        "exit_reference_price": result.exit_reference_price,
        "consecutive_opposed_at_trigger": result.consecutive_opposed_at_trigger,
        "maximum_consecutive_opposed": result.maximum_consecutive_opposed,
        "unavailable_decisions": result.unavailable_decisions,
        "coverage_gap_decisions": result.coverage_gap_decisions,
        "cost_cleared_decisions": result.cost_cleared_decisions,
    }


def _state_direction(state: object, breakout_gap: object) -> int | None:
    if state == "TREND_UP":
        return 1
    if state == "TREND_DOWN":
        return -1
    if state in {"RANGE", "TRANSITION"}:
        return 0
    if state in {None, "UNKNOWN"}:
        return None
    if state == "BREAKOUT":
        gap = _optional_number(breakout_gap)
        return None if gap is None else 1 if gap > 0.0 else -1 if gap < 0.0 else 0
    raise ValueError(f"unsupported canonical regime state: {state}")


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _persistence_surface(values: Sequence[int]) -> tuple[int, ...]:
    parsed = tuple(_positive_integer(value) for value in values)
    if not parsed or len(parsed) != len(set(parsed)):
        raise ValueError("dual-MTF persistence surface must be nonempty and unique")
    return parsed


def _positive_integer(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("dual-MTF persistence must be a positive integer")
    return value


def _required_timestamp(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("dual-MTF timestamp must be a nonnegative integer")
    if value % _MINUTE_MS:
        raise ValueError("dual-MTF decision timestamp must align to a minute")
    return value


def _validate_observation_inputs(
    side: str, entry_ms: int, end_ms: int, entry: float, size: float, entry_fee: float
) -> None:
    if side not in {"long", "short"}:
        raise ValueError("dual-MTF side must be long or short")
    if not all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (entry_ms, end_ms)
    ):
        raise ValueError("dual-MTF lifecycle timestamps must be integers")
    if entry_ms < 0 or end_ms <= entry_ms:
        raise ValueError("dual-MTF lifecycle interval is invalid")
    if any(not math.isfinite(value) for value in (entry, size, entry_fee)):
        raise ValueError("dual-MTF economics must be finite")
    if entry <= 0.0 or size <= 0.0 or entry_fee < 0.0:
        raise ValueError("dual-MTF economics have invalid signs")
