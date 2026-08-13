"""Forward counterfactual journal for regime-aware routing conflicts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from statistics import mean

from hypervector.research.cohort_forward_paths import (
    Candle,
    DirectionalPath,
    build_candle_index,
    non_overlapping_count,
    resolve_directional_path,
    validated_horizons,
)
from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    nonnegative_int,
    number,
    object_list,
    payload,
    text,
    text_list,
    timestamp,
)

Record = Mapping[str, object]
_POLICY_MODE = "same_symbol_conflict_preference_v1"
_CONFLICT_REASONS = frozenset({"lower_regime_alignment", "lower_provider_priority"})
_DEFAULT_HORIZONS = (5, 15, 30, 60)


@dataclass(frozen=True)
class _Intent:
    strategy_id: str
    symbol: str
    side: str
    decision_time_ms: int
    reference_price: float
    regime_score: float
    regime_stance: str
    regime_decision_time_ms: int
    regime_basis: str

    @property
    def identity(self) -> tuple[str, str, int]:
        return self.strategy_id, self.symbol, self.decision_time_ms


@dataclass(frozen=True)
class _Conflict:
    selected: _Intent
    static_choice: _Intent
    alternatives: tuple[_Intent, ...]

    @property
    def selection_changed(self) -> bool:
        return self.selected.identity != self.static_choice.identity

    @property
    def comparison(self) -> str:
        if not self.selection_changed:
            return "static_choice_unchanged"
        if self.selected.side == self.static_choice.side:
            return "same_direction_provider_only"
        return "opposite_direction"


@dataclass
class _HorizonSummary:
    decision_times_ms: list[int] = field(default_factory=list)
    selected_returns: list[float] = field(default_factory=list)
    static_returns: list[float] = field(default_factory=list)
    advantages: list[float] = field(default_factory=list)
    censored: int = 0
    missing_data: int = 0


def build_regime_conflict_journal(
    records: Sequence[Record],
    identity: Record,
    *,
    horizons_minutes: Sequence[int] = _DEFAULT_HORIZONS,
) -> dict[str, object]:
    """Compare regime-selected intents with the static-priority counterfactual."""
    horizons = validated_horizons(horizons_minutes)
    policy = _policy(identity)
    if policy.get("mode") != _POLICY_MODE:
        return _inactive_report(horizons, policy.get("mode"))
    priorities = _provider_priorities(identity)
    activation_ms = int(timestamp(identity).timestamp() * 1_000)
    conflicts, excluded = _conflicts(records, priorities, activation_ms)
    candles = build_candle_index(records)
    summaries = {horizon: _HorizonSummary() for horizon in horizons}
    journal = [
        _conflict_payload(conflict, candles, summaries, horizons)
        for conflict in conflicts
    ]
    return _active_report(conflicts, excluded, journal, summaries, horizons)


def _policy(identity: Record) -> Record:
    value = payload(identity).get("routing_policy")
    if value is None:
        return {}
    policy = mapping(value, "routing policy")
    mode = text(policy.get("mode"), "routing policy mode")
    if mode == _POLICY_MODE:
        _validate_active_policy(policy)
    return policy


def _validate_active_policy(policy: Record) -> None:
    if policy.get("standalone_intents_ungated") is not True:
        raise ValueError("regime routing policy must leave standalone intents ungated")
    if policy.get("forced_regime_exit") is not False:
        raise ValueError("regime routing policy cannot force regime exits")
    if policy.get("fallback") != "provider_priority_then_decision_time":
        raise ValueError("regime routing policy fallback is unsupported")
    text(policy.get("alignment_basis"), "regime alignment basis")


def _provider_priorities(identity: Record) -> dict[tuple[str, str], int]:
    output: dict[tuple[str, str], int] = {}
    for provider in object_list(payload(identity), "providers"):
        strategy = text(provider.get("strategy_id"), "provider strategy")
        priority = nonnegative_int(provider.get("priority"), "provider priority")
        for symbol in text_list(provider.get("symbols"), "provider symbols"):
            key = (strategy, symbol)
            if key in output:
                raise ValueError(f"duplicate provider priority for {strategy}|{symbol}")
            output[key] = priority
    return output


def _conflicts(
    records: Sequence[Record],
    priorities: Mapping[tuple[str, str], int],
    activation_ms: int,
) -> tuple[tuple[_Conflict, ...], int]:
    output: list[_Conflict] = []
    excluded = 0
    for row in event_rows(records, "intent_routing"):
        cycle = payload(row)
        for conflict in _cycle_conflicts(cycle, priorities):
            if conflict.selected.decision_time_ms <= activation_ms:
                excluded += 1
            else:
                output.append(conflict)
    return tuple(output), excluded


def _cycle_conflicts(
    cycle: Record, priorities: Mapping[tuple[str, str], int]
) -> tuple[_Conflict, ...]:
    withheld = object_list(cycle, "withheld")
    symbols = sorted(
        {
            text(row.get("symbol"), "withheld symbol")
            for row in withheld
            if row.get("reason") == "lower_regime_alignment"
        }
    )
    actions = _provider_candidates(
        [row for row in object_list(cycle, "actions") if row.get("symbol") in symbols],
        priorities,
    )
    return tuple(
        _symbol_conflict(symbol, actions, withheld, priorities) for symbol in symbols
    )


def _symbol_conflict(
    symbol: str,
    actions: Sequence[_Intent],
    withheld: Sequence[Record],
    priorities: Mapping[tuple[str, str], int],
) -> _Conflict:
    selected = [value for value in actions if value.symbol == symbol]
    if not selected:
        selected = _operationally_withheld_selection(symbol, withheld, priorities)
    if len(selected) != 1:
        raise ValueError(f"regime conflict requires one selected intent for {symbol}")
    alternatives = tuple(
        _intent(row, priorities)
        for row in withheld
        if row.get("symbol") == symbol and row.get("reason") in _CONFLICT_REASONS
    )
    participants = (selected[0], *alternatives)
    static_choice = max(participants, key=lambda value: _static_rank(value, priorities))
    return _Conflict(selected[0], static_choice, alternatives)


def _provider_candidates(
    rows: Sequence[Record], priorities: Mapping[tuple[str, str], int]
) -> tuple[_Intent, ...]:
    return tuple(
        _intent(row, priorities)
        for row in rows
        if (row.get("strategy_id"), row.get("symbol")) in priorities
    )


def _operationally_withheld_selection(
    symbol: str,
    withheld: Sequence[Record],
    priorities: Mapping[tuple[str, str], int],
) -> list[_Intent]:
    return [
        _intent(row, priorities)
        for row in withheld
        if row.get("symbol") == symbol
        and row.get("reason") not in _CONFLICT_REASONS
        and (row.get("strategy_id"), row.get("symbol")) in priorities
    ]


def _intent(row: Record, priorities: Mapping[tuple[str, str], int]) -> _Intent:
    strategy = text(row.get("strategy_id"), "intent strategy")
    symbol = text(row.get("symbol"), "intent symbol")
    if (strategy, symbol) not in priorities:
        raise ValueError(f"regime conflict intent is undeclared: {strategy}|{symbol}")
    side = text(row.get("side"), "intent side")
    if side not in {"long", "short"}:
        raise ValueError("regime conflict intent side must be long or short")
    decision_time = nonnegative_int(row.get("decision_time_ms"), "intent decision time")
    regime_time = nonnegative_int(
        row.get("regime_decision_time_ms"), "regime decision time"
    )
    if regime_time > decision_time:
        raise ValueError("regime preference uses future regime evidence")
    score = number(row.get("regime_alignment_score"), "regime alignment score")
    if not -1.0 <= score <= 1.0:
        raise ValueError("regime alignment score must be within [-1, 1]")
    reference = number(row.get("reference_price"), "intent reference price")
    if reference <= 0.0:
        raise ValueError("intent reference price must be positive")
    return _Intent(
        strategy,
        symbol,
        side,
        decision_time,
        reference,
        score,
        text(row.get("regime_alignment_stance"), "regime alignment stance"),
        regime_time,
        text(row.get("regime_alignment_basis"), "regime alignment basis"),
    )


def _static_rank(
    intent: _Intent, priorities: Mapping[tuple[str, str], int]
) -> tuple[int, int]:
    return priorities[(intent.strategy_id, intent.symbol)], intent.decision_time_ms


def _conflict_payload(
    conflict: _Conflict,
    candles_by_symbol: Mapping[str, Mapping[int, Candle]],
    summaries: Mapping[int, _HorizonSummary],
    horizons: Sequence[int],
) -> dict[str, object]:
    output = {
        "symbol": conflict.selected.symbol,
        "decision_time_ms": conflict.selected.decision_time_ms,
        "selection_changed": conflict.selection_changed,
        "comparison": conflict.comparison,
        "selected": _intent_payload(conflict.selected),
        "static_priority_choice": _intent_payload(conflict.static_choice),
        "alternatives": [_intent_payload(value) for value in conflict.alternatives],
        "horizons": {},
    }
    if conflict.comparison != "opposite_direction":
        return output
    candles = candles_by_symbol.get(conflict.selected.symbol, {})
    output["horizons"] = {
        str(horizon): _comparison_path(conflict, candles, summaries[horizon], horizon)
        for horizon in horizons
    }
    return output


def _comparison_path(
    conflict: _Conflict,
    candles: Mapping[int, Candle],
    summary: _HorizonSummary,
    horizon: int,
) -> dict[str, object]:
    selected_status, selected = _resolve(conflict.selected, candles, horizon)
    static_status, static = _resolve(conflict.static_choice, candles, horizon)
    if selected_status != static_status:
        raise ValueError("conflict counterfactual paths resolved inconsistently")
    if selected is None or static is None:
        if selected_status == "censored":
            summary.censored += 1
        else:
            summary.missing_data += 1
        return {"status": selected_status}
    selected_return = selected.directional_close_return_bps
    static_return = static.directional_close_return_bps
    advantage = selected_return - static_return
    summary.decision_times_ms.append(conflict.selected.decision_time_ms)
    summary.selected_returns.append(selected_return)
    summary.static_returns.append(static_return)
    summary.advantages.append(advantage)
    return {
        "status": "resolved",
        "regime_selected_return_bps": selected_return,
        "static_priority_return_bps": static_return,
        "regime_advantage_bps": advantage,
    }


def _resolve(
    intent: _Intent, candles: Mapping[int, Candle], horizon: int
) -> tuple[str, DirectionalPath | None]:
    return resolve_directional_path(
        decision_time_ms=intent.decision_time_ms,
        reference_price=intent.reference_price,
        side=intent.side,
        candles=candles,
        horizon_minutes=horizon,
    )


def _intent_payload(intent: _Intent) -> dict[str, object]:
    return {
        "strategy_id": intent.strategy_id,
        "side": intent.side,
        "reference_price": intent.reference_price,
        "regime_alignment_score": intent.regime_score,
        "regime_alignment_stance": intent.regime_stance,
        "regime_decision_time_ms": intent.regime_decision_time_ms,
        "regime_alignment_basis": intent.regime_basis,
    }


def _active_report(
    conflicts: Sequence[_Conflict],
    excluded: int,
    journal: list[dict[str, object]],
    summaries: Mapping[int, _HorizonSummary],
    horizons: Sequence[int],
) -> dict[str, object]:
    comparable = sum(value.comparison == "opposite_direction" for value in conflicts)
    missing = sum(value.missing_data for value in summaries.values())
    resolved = sum(len(value.advantages) for value in summaries.values())
    return {
        "schema_version": 1,
        "mode": "regime_conflict_counterfactual_journal",
        "state": "active",
        "contract": _contract(),
        "conflicts": len(conflicts),
        "conflicts_changing_static_choice": sum(
            value.selection_changed for value in conflicts
        ),
        "directionally_comparable_conflicts": comparable,
        "same_direction_provider_only": sum(
            value.comparison == "same_direction_provider_only" for value in conflicts
        ),
        "preactivation_conflicts_excluded": excluded,
        "horizons_minutes": list(horizons),
        "horizons": {
            str(horizon): _horizon_payload(summaries[horizon], horizon)
            for horizon in horizons
        },
        "journal": journal,
        "coverage": {"complete": missing == 0, "missing_data_paths": missing},
        "evidence_state": _evidence_state(len(conflicts), comparable, resolved),
        "limitations": _limitations(),
    }


def _horizon_payload(summary: _HorizonSummary, horizon: int) -> dict[str, object]:
    advantages = summary.advantages
    return {
        "resolved": len(advantages),
        "non_overlapping_resolved": non_overlapping_count(
            summary.decision_times_ms, horizon
        ),
        "censored": summary.censored,
        "missing_data": summary.missing_data,
        "regime_preference_wins": sum(value > 0.0 for value in advantages),
        "static_priority_wins": sum(value < 0.0 for value in advantages),
        "ties": sum(value == 0.0 for value in advantages),
        "mean_regime_selected_return_bps": _mean(summary.selected_returns),
        "mean_static_priority_return_bps": _mean(summary.static_returns),
        "mean_regime_advantage_bps": _mean(advantages),
    }


def _inactive_report(horizons: Sequence[int], policy_mode: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "regime_conflict_counterfactual_journal",
        "state": "not_active",
        "policy_mode": policy_mode,
        "contract": _contract(),
        "conflicts": 0,
        "conflicts_changing_static_choice": 0,
        "directionally_comparable_conflicts": 0,
        "same_direction_provider_only": 0,
        "preactivation_conflicts_excluded": 0,
        "horizons_minutes": list(horizons),
        "horizons": {},
        "journal": [],
        "coverage": {"complete": True, "missing_data_paths": 0},
        "evidence_state": "policy_not_active",
        "limitations": _limitations(),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "counterfactual_only": True,
        "fills_assumed": False,
        "pnl_claimed": False,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }


def _evidence_state(conflicts: int, comparable: int, resolved: int) -> str:
    if conflicts == 0:
        return "no_regime_conflicts_observed"
    if comparable == 0:
        return "execution_plan_difference_not_identifiable_from_bars"
    if resolved == 0:
        return "forward_paths_pending"
    return "descriptive_regime_conflict_evidence"


def _limitations() -> list[str]:
    return [
        "completed candles are counterfactual paths rather than executable fills",
        "same-direction provider choices require execution evidence, not bar returns",
        "overlapping paths are descriptive and report an independent count",
        "small conflict samples do not establish routing edge",
        "this journal cannot route, pause, retune, or submit orders",
    ]


def _mean(values: Sequence[float]) -> float | None:
    return float(mean(values)) if values else None
