"""Closed-lifecycle evidence assembly for frozen profit-lock policies."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import math

from hypervector.research.cohort_lifecycle_evidence import (
    FillAggregate,
    build_fill_index,
    build_funding_index,
)
from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
)
from hypervector.research.cohort_profit_lock_lifecycle_values import (
    Identity,
    completed_bars,
    lifecycle_economics,
    lifecycle_identity,
    lifecycle_payload,
    regime_contract,
)
from hypervector.research.cohort_profit_lock_policy import (
    POLICIES,
    CandleLike,
    ProfitLockPolicy,
)
from hypervector.research.cohort_profit_lock_results import (
    ProfitLockEconomics,
    build_conditioned_policy_result,
    build_policy_result,
    build_support_decay_policy_result,
    conditioned_unchanged_policy,
    conditioned_withheld_policy,
    support_decay_unchanged_policy,
    support_decay_withheld_policy,
    withheld_policy,
)
from hypervector.research.cohort_regime_opposition import (
    build_regime_support_decay_episode,
)
from hypervector.research.cohort_trade_reflection_index import (
    Candle,
    ReflectionEvidenceIndex,
    build_reflection_evidence_index,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000
_REGIME_PERSISTENCE_DECISIONS = 5
_REGIME_OPPOSITION_THRESHOLD = -0.5
_CANONICAL_STRATEGY = "range_onset_bidirectional_v1"

PolicyResultBuilder = Callable[
    [
        ProfitLockPolicy,
        str,
        Sequence[CandleLike],
        ProfitLockEconomics,
        Mapping[int, float],
        int,
    ],
    dict[str, object],
]
WithheldPolicyBuilder = Callable[
    [ProfitLockPolicy, ProfitLockEconomics, str, int | None], dict[str, object]
]


def build_profit_lock_lifecycle_results(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
    *,
    policies: Sequence[ProfitLockPolicy] = POLICIES,
) -> list[dict[str, object]]:
    """Build unconditioned policy evidence for compatible closed lifecycles."""
    candles = build_reflection_evidence_index(cohort_records).candles
    fills = build_fill_index(asset_records)
    funding = build_funding_index(asset_records)
    results = [
        _lifecycle_result(trade, candles, fills, funding, policies)
        for trade in reflected_trades
    ]
    results.sort(key=lambda row: nonnegative_int(row["exit_timestamp_ms"], "exit"))
    return results


def build_regime_conditioned_lifecycle_results(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> list[dict[str, object]]:
    """Build policies whose activation waits for causal regime opposition."""
    candles = build_reflection_evidence_index(cohort_records).candles
    fills = build_fill_index(asset_records)
    funding = build_funding_index(asset_records)
    results = [
        _regime_conditioned_result(trade, candles, fills, funding)
        for trade in reflected_trades
    ]
    results.sort(key=lambda row: nonnegative_int(row["exit_timestamp_ms"], "exit"))
    return results


def build_support_decay_lifecycle_results(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    reflected_trades: Sequence[Record],
) -> list[dict[str, object]]:
    """Build policies whose activation waits for persistent weak regime support."""
    evidence = build_reflection_evidence_index(cohort_records)
    fills = build_fill_index(asset_records)
    funding = build_funding_index(asset_records)
    results = [
        _support_decay_result(trade, evidence, fills, funding)
        for trade in reflected_trades
    ]
    results.sort(key=lambda row: nonnegative_int(row["exit_timestamp_ms"], "exit"))
    return results


def _lifecycle_result(
    trade: Record,
    candles: Mapping[str, Mapping[int, Candle]],
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
    policy_set: Sequence[ProfitLockPolicy],
) -> dict[str, object]:
    identity = lifecycle_identity(trade)
    symbol_funding = funding.get(identity[1], {})
    economics = lifecycle_economics(trade, fills, symbol_funding)
    expected, observed = completed_bars(
        candles.get(identity[1], {}),
        economics.entry_timestamp_ms,
        economics.exit_timestamp_ms,
    )
    complete = len(expected) == len(observed)
    outcomes = {
        policy.policy_id: (
            build_policy_result(
                policy, identity[3], observed, economics, symbol_funding
            )
            if complete
            else withheld_policy(policy, economics)
        )
        for policy in policy_set
    }
    return lifecycle_payload(
        identity,
        economics,
        "eligible" if complete else "insufficient_candle_coverage",
        outcomes,
        expected=len(expected),
        observed=len(observed),
    )


def _regime_conditioned_result(
    trade: Record,
    candles: Mapping[str, Mapping[int, Candle]],
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
) -> dict[str, object]:
    identity = lifecycle_identity(trade)
    symbol_funding = funding.get(identity[1], {})
    economics = lifecycle_economics(trade, fills, symbol_funding)
    gate_available, gate_ms = _regime_opposition_gate(trade, economics)
    if not gate_available:
        return _missing_opposition_result(identity, economics)
    if gate_ms is None:
        return _inactive_opposition_result(identity, economics)
    return _active_opposition_result(
        identity,
        economics,
        candles.get(identity[1], {}),
        symbol_funding,
        gate_ms,
    )


def _missing_opposition_result(
    identity: Identity,
    economics: ProfitLockEconomics,
) -> dict[str, object]:
    policies = {
        policy.policy_id: conditioned_withheld_policy(
            policy, economics, "withheld_missing_regime_opposition_evidence"
        )
        for policy in POLICIES
    }
    return lifecycle_payload(
        identity, economics, "missing_regime_opposition_evidence", policies
    )


def _inactive_opposition_result(
    identity: Identity,
    economics: ProfitLockEconomics,
) -> dict[str, object]:
    policies = {
        policy.policy_id: conditioned_unchanged_policy(
            policy, economics, "not_activated_no_persistent_opposition", None
        )
        for policy in POLICIES
    }
    return lifecycle_payload(
        identity, economics, "eligible_no_persistent_opposition", policies
    )


def _active_opposition_result(
    identity: Identity,
    economics: ProfitLockEconomics,
    candles: Mapping[int, Candle],
    symbol_funding: Mapping[int, float],
    gate_ms: int,
) -> dict[str, object]:
    return _active_conditioned_result(
        identity,
        economics,
        candles,
        symbol_funding,
        gate_ms,
        build_conditioned_policy_result,
        conditioned_withheld_policy,
        "eligible_persistent_opposition",
    )


def _active_conditioned_result(
    identity: Identity,
    economics: ProfitLockEconomics,
    candles: Mapping[int, Candle],
    symbol_funding: Mapping[int, float],
    gate_ms: int,
    policy_builder: PolicyResultBuilder,
    withheld_builder: WithheldPolicyBuilder,
    eligible_status: str,
) -> dict[str, object]:
    expected, observed = completed_bars(
        candles, economics.entry_timestamp_ms, economics.exit_timestamp_ms
    )
    complete = len(expected) == len(observed)
    policies = {
        policy.policy_id: (
            policy_builder(
                policy,
                identity[3],
                observed,
                economics,
                symbol_funding,
                gate_ms,
            )
            if complete
            else withheld_builder(
                policy,
                economics,
                "withheld_incomplete_candle_coverage",
                gate_ms,
            )
        )
        for policy in POLICIES
    }
    return lifecycle_payload(
        identity,
        economics,
        eligible_status if complete else "insufficient_candle_coverage",
        policies,
        expected=len(expected),
        observed=len(observed),
    )


def _support_decay_result(
    trade: Record,
    evidence: ReflectionEvidenceIndex,
    fills: Mapping[tuple[str, int], FillAggregate],
    funding: Mapping[str, Mapping[int, float]],
) -> dict[str, object]:
    identity = lifecycle_identity(trade)
    symbol_funding = funding.get(identity[1], {})
    economics = lifecycle_economics(trade, fills, symbol_funding)
    episode = build_regime_support_decay_episode(
        identity[3],
        evidence.timelines.get((identity[2], identity[1]), ()),
        evidence.timelines.get((_CANONICAL_STRATEGY, identity[1]), ()),
        entry_timestamp_ms=economics.entry_timestamp_ms,
        end_timestamp_ms=economics.exit_timestamp_ms,
    )
    available, gate_ms = support_decay_gate(episode, economics)
    if not available:
        policies = {
            policy.policy_id: support_decay_withheld_policy(
                policy, economics, "withheld_missing_support_decay_evidence"
            )
            for policy in POLICIES
        }
        return lifecycle_payload(
            identity, economics, "missing_support_decay_evidence", policies
        )
    if gate_ms is None:
        policies = {
            policy.policy_id: support_decay_unchanged_policy(
                policy, economics, "not_activated_no_persistent_support_decay", None
            )
            for policy in POLICIES
        }
        return lifecycle_payload(
            identity, economics, "eligible_no_persistent_support_decay", policies
        )
    return _active_conditioned_result(
        identity,
        economics,
        evidence.candles.get(identity[1], {}),
        symbol_funding,
        gate_ms,
        build_support_decay_policy_result,
        support_decay_withheld_policy,
        "eligible_persistent_support_decay",
    )


def support_decay_gate(
    episode: Record,
    economics: ProfitLockEconomics,
) -> tuple[bool, int | None]:
    """Validate support-decay evidence and return its five-decision boundary."""
    completed = nonnegative_int(episode.get("completed_decisions"), "decay decisions")
    unavailable = nonnegative_int(
        episode.get("unavailable_decisions"), "unavailable decay decisions"
    )
    if completed <= unavailable:
        return False, None
    triggers = mapping(episode.get("persistence_triggers"), "decay triggers")
    value = triggers.get(str(_REGIME_PERSISTENCE_DECISIONS))
    if value is None:
        return True, None
    timestamp_ms = nonnegative_int(value, "support-decay trigger")
    if (
        timestamp_ms % _MINUTE_MS
        or timestamp_ms <= economics.entry_timestamp_ms
        or timestamp_ms > economics.exit_timestamp_ms
    ):
        raise ValueError("support-decay trigger is outside the lifecycle")
    return True, timestamp_ms


def _regime_opposition_gate(
    trade: Record,
    economics: ProfitLockEconomics,
) -> tuple[bool, int | None]:
    raw_episode = trade.get("regime_opposition_episode")
    if raw_episode is None:
        return False, None
    episode = mapping(raw_episode, "regime opposition episode")
    contract = mapping(episode.get("contract"), "regime opposition contract")
    checks = (
        episode.get("mode") == "causal_regime_opposition_persistence_v1",
        contract == regime_contract(),
        episode.get("persistence_decisions") == [1, 3, 5],
        math.isclose(
            number(episode.get("opposition_threshold"), "opposition threshold"),
            _REGIME_OPPOSITION_THRESHOLD,
        ),
        nonnegative_int(episode.get("entry_timestamp_ms"), "opposition entry")
        == economics.entry_timestamp_ms,
        nonnegative_int(episode.get("end_timestamp_ms"), "opposition end")
        == economics.exit_timestamp_ms,
    )
    if not all(checks):
        raise ValueError("regime opposition evidence contract is inconsistent")
    return True, _opposition_trigger(episode, economics)


def _opposition_trigger(
    episode: Record,
    economics: ProfitLockEconomics,
) -> int | None:
    triggers = mapping(episode.get("persistence_triggers"), "opposition triggers")
    key = str(_REGIME_PERSISTENCE_DECISIONS)
    if key not in triggers:
        raise ValueError("five-decision opposition trigger is unavailable")
    if triggers[key] is None:
        return None
    timestamp_ms = nonnegative_int(triggers[key], "five-decision opposition trigger")
    if (
        timestamp_ms % _MINUTE_MS
        or timestamp_ms <= economics.entry_timestamp_ms
        or timestamp_ms > economics.exit_timestamp_ms
    ):
        raise ValueError("five-decision opposition trigger is outside the lifecycle")
    return timestamp_ms
