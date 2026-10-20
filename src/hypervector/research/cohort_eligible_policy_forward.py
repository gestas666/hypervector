"""Prospective exact-policy evidence for eligible report-only signals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import TypeVar

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.live.eth_breakout_transfer_provider import (
    ETH_BREAKOUT_TRANSFER_STRATEGY,
)
from hypervector.research.cohort_candidate_portfolio_journal import (
    CandidatePortfolioJournalSpec,
    build_candidate_portfolio_journal,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    covered_funding_bps,
)
from hypervector.research.cohort_forward_paths import (
    MINUTE_MS,
    Candle,
    build_candle_index,
)
from hypervector.research.cohort_live_audit_values import (
    event_rows,
    payload,
    timestamp,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)

Record = Mapping[str, object]
T = TypeVar("T")
ETH_TRANSFER_FORWARD_CANDIDATE = f"{ETH_BREAKOUT_TRANSFER_STRATEGY}_eligible_forward"
_ETH_MODELED_ROUND_TRIP_FRICTION_BPS = 13.0


@dataclass(frozen=True)
class EligiblePolicyForwardSpec:
    """Freeze one eligible provider's report-only stop and hold contract."""

    source_strategy_id: str
    candidate_strategy_id: str
    symbol: str
    source_run_id: str
    cutoff_time_ms: int
    stop_bps: float
    maximum_hold_minutes: int
    modeled_round_trip_friction_bps: float
    notional_usd: float
    maximum_positions: int

    def __post_init__(self) -> None:
        """Reject a mutable, incomplete, or success-shaped policy contract."""
        for value, label in (
            (self.source_strategy_id, "source strategy id"),
            (self.candidate_strategy_id, "candidate strategy id"),
            (self.symbol, "symbol"),
            (self.source_run_id, "source run id"),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if self.source_strategy_id == self.candidate_strategy_id:
            raise ValueError("candidate strategy id must differ from source")
        _positive_int(self.cutoff_time_ms, "cutoff time")
        _positive_int(self.maximum_hold_minutes, "maximum hold minutes")
        _positive_int(self.maximum_positions, "maximum positions")
        for value, label in (
            (self.stop_bps, "stop bps"),
            (self.modeled_round_trip_friction_bps, "modeled friction"),
            (self.notional_usd, "notional"),
        ):
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{label} must be positive and finite")


def eth_transfer_forward_spec(
    config: MultiAssetLiveConfig,
    records: Sequence[Record],
    *,
    run_id: str,
) -> EligiblePolicyForwardSpec:
    """Bind the frozen ETH transfer observer to one runtime generation."""
    provider = _single(
        [
            value
            for value in config.providers
            if value.strategy_id == ETH_BREAKOUT_TRANSFER_STRATEGY
        ],
        "ETH transfer provider",
    )
    asset = _single(
        [value for value in config.assets if value.symbol == "ETH"],
        "ETH asset",
    )
    execution = provider.execution
    if (
        provider.symbols != ("ETH",)
        or provider.sides != frozenset({"long", "short"})
        or provider.execution_symbols not in {(), ("ETH",)}
        or execution.entry_liquidity != "taker_ioc"
        or execution.stop_policy != "fixed_bps"
        or execution.target_policy != "none"
        or execution.maximum_hold_policy != "fixed"
        or execution.stop_bps is None
        or execution.maximum_hold_seconds % 60
    ):
        raise ValueError("ETH transfer execution contract no longer matches observer")
    identity = _runtime_identity(records, config, run_id)
    sizing = provider.entry_sizing("ETH")
    return EligiblePolicyForwardSpec(
        source_strategy_id=ETH_BREAKOUT_TRANSFER_STRATEGY,
        candidate_strategy_id=ETH_TRANSFER_FORWARD_CANDIDATE,
        symbol="ETH",
        source_run_id=run_id,
        cutoff_time_ms=int(timestamp(identity).timestamp() * 1_000),
        stop_bps=execution.stop_bps,
        maximum_hold_minutes=execution.maximum_hold_seconds // 60,
        modeled_round_trip_friction_bps=_ETH_MODELED_ROUND_TRIP_FRICTION_BPS,
        notional_usd=sizing.max_notional_usd if sizing else asset.max_notional_usd,
        maximum_positions=config.maximum_positions,
    )


def _runtime_identity(
    records: Sequence[Record], config: MultiAssetLiveConfig, run_id: str
) -> Record:
    matches = [
        row
        for row in event_rows(records, "configuration_identity")
        if row.get("run_id") == run_id
    ]
    identity = _single(matches, "runtime configuration identity")
    if payload(identity).get("profile_fingerprint") != config.profile_fingerprint:
        raise ValueError("runtime and observer profile fingerprints differ")
    return identity


def _single(values: Sequence[T], label: str) -> T:
    if len(values) != 1:
        raise ValueError(f"{label} must be unique")
    return values[0]


def build_eligible_policy_forward_report(
    records: Sequence[Record],
    *,
    spec: EligiblePolicyForwardSpec,
    funding_evidence: EligiblePolicyFundingEvidence | None = None,
) -> dict[str, object]:
    """Build a report-only exact-policy prospective lifecycle journal."""
    replay = _build_replay(records, spec, funding_evidence)
    executions = _records(replay["executions"], "executions")
    summary = _summary(replay, executions)
    return {
        "schema_version": 1,
        "mode": "cohort_eligible_policy_forward_report",
        "state": _state(summary),
        "contract": _contract(spec, funding_evidence),
        "summary": summary,
        "latest_attempts": replay["attempts"],
        "latest_executions": replay["executions"],
        "portfolio_journal": build_candidate_portfolio_journal(
            records,
            replay,
            spec=CandidatePortfolioJournalSpec(
                source_strategy_id=spec.source_strategy_id,
                candidate_strategy_id=spec.candidate_strategy_id,
                symbol=spec.symbol,
                maximum_positions=spec.maximum_positions,
            ),
        ),
        "limitations": _limitations(funding_evidence),
    }


def _build_replay(
    records: Sequence[Record],
    spec: EligiblePolicyForwardSpec,
    funding_evidence: EligiblePolicyFundingEvidence | None,
) -> dict[str, object]:
    candidates, _, _ = evaluation_candidates(records)
    selected = _matching_candidates(candidates, spec)
    candles = build_candle_index(records).get(spec.symbol, {})
    attempts: list[dict[str, object]] = []
    executions: list[dict[str, object]] = []
    next_available_ms = -1
    overlapping = 0
    for candidate in selected:
        if candidate.available_time_ms < next_available_ms:
            overlapping += 1
            continue
        attempt, execution, next_available_ms = _evaluate(
            candidate,
            candles,
            spec,
            funding_evidence,
        )
        attempts.append(attempt)
        if execution is not None:
            executions.append(execution)
    return {
        "schema_version": 1,
        "mode": "eligible_policy_forward_observer",
        "contract": _contract(spec, funding_evidence),
        "eligible_signals": len(selected),
        "overlapping_excluded": overlapping,
        "attempts": attempts,
        "executions": executions,
    }


def _matching_candidates(
    candidates: Sequence[SignalCandidate], spec: EligiblePolicyForwardSpec
) -> tuple[SignalCandidate, ...]:
    selected = tuple(
        candidate
        for candidate in candidates
        if candidate.source_run_id == spec.source_run_id
        and candidate.strategy_id == spec.source_strategy_id
        and candidate.symbol == spec.symbol
        and candidate.eligible
        and candidate.available_time_ms >= spec.cutoff_time_ms
    )
    for candidate in selected:
        _validate_candidate_contract(candidate, spec)
    return tuple(sorted(selected, key=lambda item: item.available_time_ms))


def _validate_candidate_contract(
    candidate: SignalCandidate, spec: EligiblePolicyForwardSpec
) -> None:
    stop = _number(candidate.metrics.get("stop_bps"), "candidate stop bps")
    hold = _number(
        candidate.metrics.get("maximum_hold_seconds"),
        "candidate maximum hold seconds",
    )
    if stop != spec.stop_bps or hold != spec.maximum_hold_minutes * 60:
        raise ValueError("candidate telemetry does not match frozen stop/hold contract")


def _evaluate(
    candidate: SignalCandidate,
    candles: Mapping[int, Candle],
    spec: EligiblePolicyForwardSpec,
    funding_evidence: EligiblePolicyFundingEvidence | None,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    base = _attempt_base(candidate, spec)
    path, complete = _contiguous_path(candidate.decision_time_ms, candles, spec)
    if path is None:
        return base | {"status": "missing_data"}, None, _deadline(candidate, spec)
    stop = _first_stop(path, candidate, spec)
    if stop is not None:
        execution = _execution(
            candidate,
            path,
            stop,
            "protective_stop",
            spec,
            funding_evidence,
        )
        return base | {"status": "resolved"}, execution, int(execution["exit_time_ms"])
    if complete:
        exit_candle = path[-1]
        execution = _execution(
            candidate,
            path,
            exit_candle,
            "maximum_hold",
            spec,
            funding_evidence,
        )
        return base | {"status": "resolved"}, execution, int(execution["exit_time_ms"])
    return (
        base | _pending(candidate, path, spec, funding_evidence),
        None,
        _deadline(candidate, spec),
    )


def _contiguous_path(
    decision_time_ms: int,
    candles: Mapping[int, Candle],
    spec: EligiblePolicyForwardSpec,
) -> tuple[tuple[Candle, ...] | None, bool]:
    expected = tuple(
        decision_time_ms + offset * MINUTE_MS
        for offset in range(spec.maximum_hold_minutes)
    )
    if not candles or expected[0] not in candles:
        return None, False
    path: list[Candle] = []
    for timestamp_ms in expected:
        candle = candles.get(timestamp_ms)
        if candle is None:
            if max(candles) >= timestamp_ms:
                return None, False
            break
        path.append(candle)
    return tuple(path), len(path) == len(expected)


def _first_stop(
    path: Sequence[Candle], candidate: SignalCandidate, spec: EligiblePolicyForwardSpec
) -> Candle | None:
    stop_price = _stop_price(candidate, spec)
    for candle in path:
        if candidate.side == "long" and candle.low <= stop_price:
            return candle
        if candidate.side == "short" and candle.high >= stop_price:
            return candle
    return None


def _execution(
    candidate: SignalCandidate,
    path: Sequence[Candle],
    exit_candle: Candle,
    exit_reason: str,
    spec: EligiblePolicyForwardSpec,
    funding_evidence: EligiblePolicyFundingEvidence | None,
) -> dict[str, object]:
    realized_path = tuple(
        candle for candle in path if candle.timestamp_ms <= exit_candle.timestamp_ms
    )
    gross = (
        -spec.stop_bps
        if exit_reason == "protective_stop"
        else _direction(candidate)
        * (exit_candle.close / candidate.reference_price - 1.0)
        * 10_000.0
    )
    before_funding = gross - spec.modeled_round_trip_friction_bps
    exit_time_ms = exit_candle.timestamp_ms + MINUTE_MS
    funding = covered_funding_bps(
        funding_evidence,
        symbol=candidate.symbol,
        side=candidate.side or "",
        start_ms=candidate.available_time_ms,
        end_ms=exit_time_ms,
    )
    net = before_funding + (funding or 0.0)
    favorable, adverse = _excursions(realized_path, candidate)
    return _attempt_base(candidate, spec) | {
        "status": "resolved",
        "entry_time_ms": candidate.available_time_ms,
        "entry_price": candidate.reference_price,
        "exit_time_ms": exit_time_ms,
        "exit_price": _stop_price(candidate, spec)
        if exit_reason == "protective_stop"
        else exit_candle.close,
        "exit_reason": exit_reason,
        "gross_return_bps": gross,
        "modeled_round_trip_friction_bps": spec.modeled_round_trip_friction_bps,
        "funding_bps": funding,
        "net_return_before_funding_bps": before_funding,
        "net_return_bps": net,
        "net_return_scope": (
            "modeled_friction_and_official_funding"
            if funding is not None
            else "modeled_friction_before_funding"
        ),
        "simulated_net_pnl_usd": spec.notional_usd * net / 10_000.0,
        "mfe_bps": favorable,
        "mae_bps": adverse,
    }


def _pending(
    candidate: SignalCandidate,
    path: Sequence[Candle],
    spec: EligiblePolicyForwardSpec,
    funding_evidence: EligiblePolicyFundingEvidence | None,
) -> dict[str, object]:
    favorable, adverse = _excursions(path, candidate)
    current = (
        _direction(candidate)
        * (path[-1].close / candidate.reference_price - 1.0)
        * 10_000.0
    )
    observed_end_ms = path[-1].timestamp_ms + MINUTE_MS
    funding = covered_funding_bps(
        funding_evidence,
        symbol=candidate.symbol,
        side=candidate.side or "",
        start_ms=candidate.available_time_ms,
        end_ms=observed_end_ms,
    )
    before_funding = current - spec.modeled_round_trip_friction_bps
    return {
        "status": "exit_pending",
        "entry_time_ms": candidate.available_time_ms,
        "entry_price": candidate.reference_price,
        "deadline_time_ms": _deadline(candidate, spec),
        "observed_candles": len(path),
        "remaining_ms": max(
            0,
            _deadline(candidate, spec) - path[-1].timestamp_ms - MINUTE_MS,
        ),
        "current_gross_return_bps": current,
        "current_estimated_net_before_funding_bps": before_funding,
        "current_estimated_net_after_funding_bps": (
            before_funding + funding if funding is not None else None
        ),
        "funding_bps": funding,
        "mfe_bps": favorable,
        "mae_bps": adverse,
    }


def _attempt_base(
    candidate: SignalCandidate, spec: EligiblePolicyForwardSpec
) -> dict[str, object]:
    if candidate.side not in {"long", "short"}:
        raise ValueError("eligible policy candidate requires a direction")
    return {
        "source_run_id": candidate.source_run_id,
        "strategy_id": candidate.strategy_id,
        "candidate_strategy_id": spec.candidate_strategy_id,
        "symbol": candidate.symbol,
        "side": candidate.side,
        "decision_time_ms": candidate.decision_time_ms,
        "available_time_ms": candidate.available_time_ms,
        "reference_price": candidate.reference_price,
    }


def _summary(
    replay: Mapping[str, object], executions: Sequence[Record]
) -> dict[str, object]:
    attempts = _records(replay.get("attempts"), "attempts")
    before_values = [
        _number(row.get("net_return_before_funding_bps"), "pre-funding net return")
        for row in executions
    ]
    after_values = [
        _number(row.get("net_return_bps"), "net return") for row in executions
    ]
    before_gains = sum(value for value in before_values if value > 0.0)
    before_losses = -sum(value for value in before_values if value < 0.0)
    after_gains = sum(value for value in after_values if value > 0.0)
    after_losses = -sum(value for value in after_values if value < 0.0)
    funded = bool(executions) and all(
        row.get("funding_bps") is not None for row in executions
    )
    return {
        "eligible_signals": int(replay["eligible_signals"]),
        "selected_non_overlapping": len(attempts),
        "overlapping_excluded": int(replay["overlapping_excluded"]),
        "resolved": len(executions),
        "pending": sum(row.get("status") == "exit_pending" for row in attempts),
        "missing_data": sum(row.get("status") == "missing_data" for row in attempts),
        "wins": sum(value > 0.0 for value in before_values),
        "losses": sum(value < 0.0 for value in before_values),
        "total_estimated_net_before_funding_bps": sum(before_values),
        "profit_factor_before_funding": (
            before_gains / before_losses if before_losses else None
        ),
        "total_estimated_net_after_funding_bps": (
            sum(after_values) if funded else None
        ),
        "profit_factor_after_funding": (
            after_gains / after_losses if funded and after_losses else None
        ),
    }


def _contract(
    spec: EligiblePolicyForwardSpec,
    funding_evidence: EligiblePolicyFundingEvidence | None,
) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "live_strategy_changed": False,
        "automatic_promotion": False,
        "portfolio_pnl_claimed": False,
        "source_strategy_id": spec.source_strategy_id,
        "candidate_strategy_id": spec.candidate_strategy_id,
        "symbol": spec.symbol,
        "source_run_id": spec.source_run_id,
        "cutoff_time_ms": spec.cutoff_time_ms,
        "stop_bps": spec.stop_bps,
        "maximum_hold_minutes": spec.maximum_hold_minutes,
        "modeled_round_trip_friction_bps": spec.modeled_round_trip_friction_bps,
        "funding_included": funding_evidence is not None,
        "funding_source": (
            "hl_funding_history" if funding_evidence is not None else None
        ),
        "notional_usd": spec.notional_usd,
        "one_position_per_coin": True,
    }


def _state(summary: Mapping[str, object]) -> str:
    if summary["eligible_signals"] == 0:
        return "awaiting_fresh_eligible_signal"
    if summary["resolved"]:
        return "descriptive_resolved_forward_evidence"
    if summary["missing_data"]:
        return "technical_evidence_incomplete"
    return "awaiting_exact_policy_resolution"


def _excursions(
    path: Sequence[Candle], candidate: SignalCandidate
) -> tuple[float, float]:
    direction = _direction(candidate)
    reference = candidate.reference_price
    favorable_prices = [value.high if direction > 0.0 else value.low for value in path]
    adverse_prices = [value.low if direction > 0.0 else value.high for value in path]
    favorable = max(
        direction * (price / reference - 1.0) * 10_000.0 for price in favorable_prices
    )
    adverse = min(
        direction * (price / reference - 1.0) * 10_000.0 for price in adverse_prices
    )
    return max(0.0, favorable), min(0.0, adverse)


def _stop_price(candidate: SignalCandidate, spec: EligiblePolicyForwardSpec) -> float:
    return candidate.reference_price * (
        1.0 - _direction(candidate) * spec.stop_bps / 10_000.0
    )


def _deadline(candidate: SignalCandidate, spec: EligiblePolicyForwardSpec) -> int:
    return candidate.decision_time_ms + spec.maximum_hold_minutes * MINUTE_MS


def _direction(candidate: SignalCandidate) -> float:
    if candidate.side == "long":
        return 1.0
    if candidate.side == "short":
        return -1.0
    raise ValueError("eligible policy candidate requires a direction")


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} rows must be mappings")
    return tuple(row for row in value if isinstance(row, Mapping))


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _limitations(
    funding_evidence: EligiblePolicyFundingEvidence | None,
) -> list[str]:
    funding = (
        "official funding settlements are included only for fully covered paths"
        if funding_evidence is not None
        else "the 13-bps friction assumption excludes subsequently realized funding"
    )
    return [
        "decision reference is not proof of an IOC fill or realized slippage",
        "one-minute candles cannot establish intrabar stop ordering or stop fill price",
        funding,
        "simulated outcomes are non-additive and have no execution or promotion authority",
    ]
