"""Report-only entry-to-current regime context for open cohort positions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_live_audit_values import (
    mapping,
    mapping_list,
    nonnegative_int,
    payload,
    text,
    timestamp,
)
from hypervector.research.cohort_regime_assessment import build_regime_assessment
from hypervector.research.cohort_regime_opposition import (
    build_regime_opposition_episode,
)
from hypervector.research.cohort_open_trade_evidence import build_open_trade_evidence
from hypervector.research.cohort_open_profit_protection import (
    build_open_profit_protection,
)
from hypervector.research.cohort_open_trade_target import project_open_target_order
from hypervector.research.cohort_open_exit_plan import build_open_exit_plan
from hypervector.research.cohort_trade_reflections import (
    ReflectionEvidenceIndex,
    build_reflection_evidence_index,
    entry_source_runs,
    project_regime_context,
    project_protective_stop,
    trade_source_run,
)
from hypervector.research.cohort_trade_reflection_index import (
    canonical_timeline,
    exact_canonical_evaluation,
    latest_canonical_for_run,
)

Record = Mapping[str, object]


@dataclass(frozen=True)
class _OpenTradeCore:
    position: Record
    entry: Record
    strategy: str
    side: str
    entry_context: dict[str, object]
    current_context: dict[str, object]
    entry_regime_assessment: dict[str, object]
    regime_assessment: dict[str, object]
    exit_plan: dict[str, object]


def build_open_trade_reflections(
    cohort_records: Sequence[Record],
    current_run_records: Sequence[Record],
    journals: Mapping[str, Mapping[str, object]],
    asset_records: Mapping[str, Sequence[Record]],
    open_positions: Sequence[Record],
    *,
    compatible_run_ids: Sequence[str],
    current_run_id: str,
) -> dict[str, object]:
    """Join open execution lifecycles to entry and current regime evidence."""
    allowed_runs = _validated_run_ids(compatible_run_ids)
    compatible = tuple(
        row for row in cohort_records if row.get("run_id") in allowed_runs
    )
    index = build_reflection_evidence_index(compatible)
    positions = _position_index(open_positions)
    source_runs = entry_source_runs(asset_records)
    opened_at = _runtime_opened_at_index(asset_records)
    as_of_ms = _as_of_ms(current_run_records)
    trades = [
        _reflect_open_trade(
            symbol,
            lifecycle,
            trade_source_run(symbol, lifecycle, source_runs),
            positions,
            index,
            current_run_id,
            as_of_ms,
            current_run_records,
            opened_at.get(
                (symbol, nonnegative_int(lifecycle.get("entry_oid"), "entry oid"))
            ),
        )
        for symbol, journal in sorted(journals.items())
        for lifecycle in mapping_list(
            journal.get("open_lifecycles"), f"{symbol} open lifecycles"
        )
        if lifecycle.get("status") == "open"
    ]
    return {
        "schema_version": 1,
        "mode": "cohort_open_trade_reflections",
        "contract": _contract(),
        "scope": "compatible_profile_history",
        "as_of_timestamp_ms": as_of_ms,
        "open_lifecycles": len(trades),
        "trades": trades,
        "limitations": _limitations(),
    }


def _validated_run_ids(values: Sequence[str]) -> frozenset[str]:
    run_ids = tuple(values)
    if not run_ids:
        raise ValueError("open trade reflections require compatible run identities")
    if any(not isinstance(value, str) or not value.strip() for value in run_ids):
        raise ValueError("compatible run identities must be non-empty strings")
    return frozenset(run_ids)


def _position_index(positions: Sequence[Record]) -> dict[str, Record]:
    output: dict[str, Record] = {}
    for position in positions:
        symbol = text(position.get("symbol"), "open position symbol")
        if symbol in output:
            raise ValueError(f"duplicate open position for {symbol}")
        output[symbol] = position
    return output


def _runtime_opened_at_index(
    assets: Mapping[str, Sequence[Record]],
) -> dict[tuple[str, int], int]:
    output: dict[tuple[str, int], int] = {}
    for symbol, rows in assets.items():
        for row in rows:
            if row.get("event_type") != "state_transition":
                continue
            values = payload(row)
            if values.get("entry_oid") is None:
                continue
            oid = nonnegative_int(values.get("entry_oid"), "runtime entry oid")
            opened_at = nonnegative_int(
                values.get("opened_at_ms"), "runtime opened_at_ms"
            )
            key = (symbol, oid)
            prior = output.get(key)
            if prior is not None and prior != opened_at:
                raise ValueError(f"{symbol}:{oid} has conflicting runtime opened_at_ms")
            output[key] = opened_at
    return output


def _as_of_ms(records: Sequence[Record]) -> int:
    if not records:
        raise ValueError("open trade reflections require current-run records")
    return int(timestamp(records[-1]).timestamp() * 1_000)


def _reflect_open_trade(
    symbol: str,
    lifecycle: Record,
    source_run_id: str,
    positions: Mapping[str, Record],
    index: ReflectionEvidenceIndex,
    current_run_id: str,
    as_of_ms: int,
    current_run_records: Sequence[Record],
    runtime_opened_at_ms: int | None,
) -> dict[str, object]:
    core = _open_trade_core(
        symbol,
        lifecycle,
        source_run_id,
        positions,
        index,
        current_run_id,
        as_of_ms,
        current_run_records,
        runtime_opened_at_ms,
    )
    protective_stop = project_protective_stop(lifecycle)
    entry_ms = nonnegative_int(
        core.entry.get("venue_timestamp_ms"), "open trade entry timestamp"
    )
    return {
        "lifecycle_id": f"{symbol}:{lifecycle.get('entry_oid')}",
        "source_run_id": source_run_id,
        "symbol": symbol,
        "strategy_id": core.strategy,
        "side": core.side,
        "entry": dict(core.entry),
        "protective_stop": protective_stop,
        **_execution_annotations(core, index, symbol, protective_stop, as_of_ms),
        "entry_context": core.entry_context,
        "entry_regime_assessment": core.entry_regime_assessment,
        "current_context": core.current_context,
        "regime_drift": _regime_drift(core.entry_context, core.current_context),
        "regime_assessment": core.regime_assessment,
        "regime_opposition_episode": build_regime_opposition_episode(
            core.side,
            index.timelines.get((core.strategy, symbol), ()),
            canonical_timeline(index, symbol),
            entry_timestamp_ms=entry_ms,
            end_timestamp_ms=as_of_ms,
        ),
        "marked_economics": dict(core.position),
    }


def _execution_annotations(
    core: _OpenTradeCore,
    index: ReflectionEvidenceIndex,
    symbol: str,
    protective_stop: dict[str, object],
    as_of_ms: int,
) -> dict[str, object]:
    evidence = build_open_trade_evidence(
        index.candles.get(symbol, {}),
        core.side,
        core.entry,
        core.position,
        core.exit_plan,
        as_of_ms,
        provider_evaluations=index.timelines.get((core.strategy, symbol), ()),
        protective_stop=protective_stop,
    )
    return {
        "profit_protection": build_open_profit_protection(
            core.side, core.entry, protective_stop, core.position
        ),
        "target_order": project_open_target_order(core.position, core.side),
        "exit_plan": core.exit_plan,
        **evidence,
        "holding_time_ms": _holding_time_ms(core.entry, as_of_ms),
    }


def _open_trade_core(
    symbol: str,
    lifecycle: Record,
    source_run_id: str,
    positions: Mapping[str, Record],
    index: ReflectionEvidenceIndex,
    current_run_id: str,
    as_of_ms: int,
    current_run_records: Sequence[Record],
    runtime_opened_at_ms: int | None,
) -> _OpenTradeCore:
    position = positions.get(symbol)
    if position is None:
        raise ValueError(f"{symbol} open lifecycle lacks a current position")
    entry = mapping(lifecycle.get("entry"), "open lifecycle entry")
    regime = mapping(lifecycle.get("entry_regime"), "open lifecycle entry regime")
    strategy = text(regime.get("strategy_id"), "open lifecycle strategy")
    decision_ms = nonnegative_int(regime.get("decision_time_ms"), "entry decision")
    side = text(lifecycle.get("direction"), "open lifecycle direction")
    entry_context = _entry_context(
        source_run_id, strategy, symbol, decision_ms, regime, index
    )
    current_context = _current_context(current_run_id, strategy, symbol, index)
    entry_regime_assessment = build_regime_assessment(side, entry_context)
    regime_assessment = build_regime_assessment(side, current_context)
    return _OpenTradeCore(
        position,
        entry,
        strategy,
        side,
        entry_context,
        current_context,
        entry_regime_assessment,
        regime_assessment,
        build_open_exit_plan(
            symbol,
            strategy,
            entry,
            as_of_ms,
            current_run_records,
            str(regime_assessment["maximum_hold_context"]),
            runtime_opened_at_ms,
        ),
    )


def _entry_context(
    source_run_id: str,
    strategy: str,
    symbol: str,
    decision_ms: int,
    signal_regime: Record,
    index: ReflectionEvidenceIndex,
) -> dict[str, object]:
    signal = index.evaluations.get((source_run_id, strategy, symbol, decision_ms))
    canonical = exact_canonical_evaluation(index, source_run_id, symbol, decision_ms)
    return {
        "signal_provider": project_regime_context(signal or signal_regime),
        "canonical_regime": project_regime_context(canonical),
    }


def _current_context(
    current_run_id: str,
    strategy: str,
    symbol: str,
    index: ReflectionEvidenceIndex,
) -> dict[str, object]:
    return {
        "signal_provider": project_regime_context(
            index.latest_by_run.get((current_run_id, strategy, symbol))
        ),
        "canonical_regime": project_regime_context(
            latest_canonical_for_run(index, current_run_id, symbol)
        ),
    }


def _regime_drift(entry: Record, current: Record) -> dict[str, object]:
    return {
        "signal_provider_changed": _context_changed(entry, current, "signal_provider"),
        "canonical_regime_changed": _context_changed(
            entry, current, "canonical_regime"
        ),
    }


def _context_changed(entry: Record, current: Record, key: str) -> bool | None:
    before = mapping(entry.get(key), f"entry {key}")
    after = mapping(current.get(key), f"current {key}")
    if before.get("status") != "observed" or after.get("status") != "observed":
        return None
    return before.get("primary_regime") != after.get("primary_regime")


def _holding_time_ms(entry: Record, as_of_ms: int) -> int:
    entry_ms = nonnegative_int(entry.get("venue_timestamp_ms"), "entry timestamp")
    if as_of_ms < entry_ms:
        raise ValueError("open trade checkpoint precedes entry fill")
    return as_of_ms - entry_ms


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }


def _limitations() -> list[str]:
    return [
        "current regime context is the latest backend evaluation in the checkpoint prefix",
        "profit protection estimates omit future funding and exit slippage",
        "regime drift is descriptive and supplies no automatic exit authority",
        "legacy ledgers without opened_at_ms use a labeled fill-time timer fallback",
        "this report cannot alter strategy state or submit orders",
    ]
