"""Report-only regime and forward-path context for closed cohort trades."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    mapping,
    mapping_list,
    nonnegative_int,
    number,
    payload,
    text,
)
from hypervector.research.cohort_entry_followthrough import (
    build_entry_followthrough_paths,
)
from hypervector.research.cohort_regime_assessment import build_regime_assessment
from hypervector.research.cohort_regime_opposition import (
    build_regime_opposition_episode,
)
from hypervector.research.cohort_trade_performance import trade_economics
from hypervector.research.cohort_trade_profile_attribution import (
    attach_source_profile_fingerprints,
)
from hypervector.research.cohort_trade_capture import build_completed_hold_capture
from hypervector.research.cohort_trade_reflection_index import (
    Candle as _Candle,
    ReflectionEvidenceIndex,
    build_reflection_evidence_index,
    canonical_timeline,
    exact_canonical_evaluation,
    latest_canonical_at_or_before,
)
from hypervector.research.cohort_trade_reflection_report import (
    build_all_time_reflection_report,
    build_reflection_report,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000
_DEFAULT_HORIZONS = (5, 15, 30, 60)
_ENTRY_FOLLOWTHROUGH_HORIZONS = (240, 720, 1_440, 2_880)


def build_trade_reflections(
    cohort_records: Sequence[Record],
    journals: Mapping[str, Mapping[str, object]],
    *,
    asset_records: Mapping[str, Sequence[Record]],
    compatible_run_ids: Sequence[str],
    current_profile_fingerprint: str,
    current_run_id: str,
    horizons_minutes: Sequence[int] = _DEFAULT_HORIZONS,
) -> dict[str, object]:
    """Join closed executions to decision-time regimes and later candle paths."""
    horizons = _validated_horizons(horizons_minutes)
    allowed_runs = _validated_run_ids(compatible_run_ids)
    trades = _reflected_trades(
        cohort_records, journals, asset_records, allowed_runs, horizons
    )
    return build_reflection_report(
        trades,
        horizons,
        _ENTRY_FOLLOWTHROUGH_HORIZONS,
        current_profile_fingerprint,
        current_run_id,
    )


def build_all_time_trade_reflections(
    cohort_records: Sequence[Record],
    journals: Mapping[str, Mapping[str, object]],
    *,
    asset_records: Mapping[str, Sequence[Record]],
    live_run_ids: Sequence[str],
    horizons_minutes: Sequence[int] = _DEFAULT_HORIZONS,
) -> dict[str, object]:
    """Build user-facing lifecycle history across every armed-live profile."""
    horizons = _validated_horizons(horizons_minutes)
    allowed_runs = _validated_run_ids(live_run_ids)
    trades = _reflected_trades(
        cohort_records, journals, asset_records, allowed_runs, horizons
    )
    return build_all_time_reflection_report(trades, horizons)


def _reflected_trades(
    cohort_records: Sequence[Record],
    journals: Mapping[str, Mapping[str, object]],
    asset_records: Mapping[str, Sequence[Record]],
    allowed_runs: frozenset[str],
    horizons: Sequence[int],
) -> list[dict[str, object]]:
    """Project sorted lifecycle reflections for an explicit set of run identities."""
    selected = tuple(row for row in cohort_records if row.get("run_id") in allowed_runs)
    index = build_reflection_evidence_index(selected)
    source_runs = entry_source_runs(asset_records)
    trades = sorted(
        [
            _reflect_trade(
                symbol,
                trade,
                trade_source_run(symbol, trade, source_runs),
                index,
                horizons,
            )
            for symbol, journal in sorted(journals.items())
            for trade in mapping_list(journal.get("trades"), f"{symbol} journal trades")
        ],
        key=_reflected_exit_time,
    )
    return attach_source_profile_fingerprints(trades, selected)


def _validated_horizons(values: Sequence[int]) -> tuple[int, ...]:
    horizons = tuple(values)
    if not horizons or len(horizons) != len(set(horizons)):
        raise ValueError("trade-reflection horizons must be unique and non-empty")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in horizons
    ):
        raise ValueError("trade-reflection horizons must be positive integer minutes")
    return tuple(sorted(horizons))


def _reflected_exit_time(trade: Record) -> int:
    exit_leg = mapping(trade.get("exit"), "reflected trade exit")
    return nonnegative_int(exit_leg.get("venue_timestamp_ms"), "reflected exit time")


def _validated_run_ids(values: Sequence[str]) -> frozenset[str]:
    run_ids = tuple(values)
    if not run_ids:
        raise ValueError("trade reflections require compatible run identities")
    if any(not isinstance(value, str) or not value.strip() for value in run_ids):
        raise ValueError("compatible run identities must be non-empty strings")
    return frozenset(run_ids)


def entry_source_runs(
    assets: Mapping[str, Sequence[Record]],
) -> dict[tuple[str, int], str]:
    """Map accepted entry order identities to their originating live run."""
    output: dict[tuple[str, int], str] = {}
    for symbol, rows in assets.items():
        for row in rows:
            if row.get("event_type") != "order_acknowledgement":
                continue
            values = payload(row)
            if values.get("operation") != "entry" or values.get("accepted") is not True:
                continue
            oid = nonnegative_int(values.get("oid"), "entry oid")
            if oid < 1:
                raise ValueError("entry oid must be positive")
            key = (symbol, oid)
            run_id = text(row.get("run_id"), "asset run id")
            prior = output.get(key)
            if prior is not None and prior != run_id:
                raise ValueError("entry oid appears in multiple asset runs")
            output[key] = run_id
    return output


def trade_source_run(
    symbol: str,
    trade: Record,
    source_runs: Mapping[tuple[str, int], str],
) -> str:
    """Resolve one journal lifecycle to its originating live run."""
    oid = nonnegative_int(trade.get("entry_oid"), "trade entry oid")
    source = source_runs.get((symbol, oid))
    if source is None:
        raise ValueError(f"{symbol} trade {oid} lacks an entry source run")
    return source


def _reflect_trade(
    symbol: str,
    trade: Record,
    source_run_id: str,
    index: ReflectionEvidenceIndex,
    horizons: Sequence[int],
) -> dict[str, object]:
    side = text(trade.get("direction"), "trade direction")
    if side not in {"long", "short"}:
        raise ValueError("trade direction must be long or short")
    entry = mapping(trade.get("entry"), "trade entry")
    exit_leg = mapping(trade.get("exit"), "trade exit")
    entry_regime = mapping(trade.get("entry_regime"), "entry regime")
    strategy = text(entry_regime.get("strategy_id"), "entry strategy")
    exit_regime = mapping(trade.get("exit_regime"), "exit regime")
    exit_controller = text(exit_regime.get("strategy_id"), "exit controller strategy")
    decision_ms = nonnegative_int(entry_regime.get("decision_time_ms"), "entry time")
    exit_ms = nonnegative_int(exit_leg.get("venue_timestamp_ms"), "exit time")
    protective_stop = project_protective_stop(trade)
    return {
        **_trade_core_fields(
            symbol,
            trade,
            source_run_id,
            strategy,
            exit_controller,
            side,
            entry,
            exit_leg,
            protective_stop,
        ),
        **_trade_context_fields(
            index,
            symbol,
            strategy,
            exit_controller,
            side,
            source_run_id,
            decision_ms,
            exit_ms,
            entry,
            exit_leg,
            protective_stop,
            horizons,
            trade,
        ),
    }


def _trade_core_fields(
    symbol: str,
    trade: Record,
    source_run_id: str,
    strategy: str,
    exit_controller: str,
    side: str,
    entry: Record,
    exit_leg: Record,
    protective_stop: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "lifecycle_id": f"{symbol}:{trade.get('entry_oid')}",
        "source_run_id": source_run_id,
        "symbol": symbol,
        "strategy_id": strategy,
        "entry_strategy_id": strategy,
        "exit_controller_strategy_id": exit_controller,
        "cross_provider_exit": exit_controller != strategy,
        "side": side,
        "entry_oid": nonnegative_int(trade.get("entry_oid"), "trade entry oid"),
        "exit_oid": nonnegative_int(trade.get("exit_oid"), "trade exit oid"),
        "entry": dict(entry),
        "exit": dict(exit_leg),
        "protective_stop": protective_stop,
        "exit_reason": trade.get("exit_reason"),
        "holding_time_ms": trade.get("holding_time_ms"),
        "net_pnl_usd": trade.get("net_pnl_usd"),
        "fees_usd": trade.get("fees_usd"),
        "funding_usd": trade.get("funding_usd"),
        **trade_economics(trade, side),
    }


def _trade_context_fields(
    index: ReflectionEvidenceIndex,
    symbol: str,
    strategy: str,
    exit_controller: str,
    side: str,
    source_run_id: str,
    decision_ms: int,
    exit_ms: int,
    entry: Record,
    exit_leg: Record,
    protective_stop: dict[str, object] | None,
    horizons: Sequence[int],
    economics: Record,
) -> dict[str, object]:
    entry_context = _entry_context(index, source_run_id, strategy, symbol, decision_ms)
    exit_context = _exit_context(
        index,
        strategy,
        exit_controller,
        symbol,
        exit_ms,
    )
    candles = index.candles.get(symbol, {})
    exit_price = number(exit_leg.get("price"), "exit price")
    return {
        "entry_context": entry_context,
        "entry_regime_assessment": build_regime_assessment(side, entry_context),
        "exit_context": exit_context,
        "exit_regime_assessment": build_regime_assessment(side, exit_context),
        "regime_opposition_episode": build_regime_opposition_episode(
            side,
            index.timelines.get((strategy, symbol), ()),
            canonical_timeline(index, symbol),
            entry_timestamp_ms=nonnegative_int(
                entry.get("venue_timestamp_ms"), "trade entry timestamp"
            ),
            end_timestamp_ms=exit_ms,
        ),
        "entry_followthrough_path": build_entry_followthrough_paths(
            candles,
            side,
            entry,
            protective_stop,
            _ENTRY_FOLLOWTHROUGH_HORIZONS,
        ),
        "completed_hold_capture": build_completed_hold_capture(
            candles, side, entry, exit_leg, economics=economics
        ),
        "post_exit_path": _post_exit_paths(
            candles, side, exit_ms, exit_price, horizons
        ),
    }


def _entry_context(
    index: ReflectionEvidenceIndex,
    source_run_id: str,
    strategy: str,
    symbol: str,
    decision_ms: int,
) -> dict[str, object]:
    return {
        "signal_provider": project_regime_context(
            index.evaluations.get((source_run_id, strategy, symbol, decision_ms))
        ),
        "canonical_regime": project_regime_context(
            exact_canonical_evaluation(index, source_run_id, symbol, decision_ms)
        ),
    }


def _exit_context(
    index: ReflectionEvidenceIndex,
    strategy: str,
    exit_controller: str,
    symbol: str,
    exit_ms: int,
) -> dict[str, object]:
    return {
        "signal_provider": project_regime_context(
            _latest_at_or_before(index.timelines.get((strategy, symbol), ()), exit_ms),
            observed_for_ms=exit_ms,
        ),
        "canonical_regime": project_regime_context(
            latest_canonical_at_or_before(index, symbol, exit_ms),
            observed_for_ms=exit_ms,
        ),
        "exit_controller": project_regime_context(
            _latest_at_or_before(
                index.timelines.get((exit_controller, symbol), ()), exit_ms
            ),
            observed_for_ms=exit_ms,
        ),
    }


def _latest_at_or_before(records: Sequence[Record], timestamp_ms: int) -> Record | None:
    candidates = [row for row in records if _evaluation_time(row) <= timestamp_ms]
    return candidates[-1] if candidates else None


def _evaluation_time(record: Record) -> int:
    return nonnegative_int(record.get("decision_time_ms"), "evaluation decision time")


def project_regime_context(
    evaluation: Record | None, *, observed_for_ms: int | None = None
) -> dict[str, object]:
    """Project one provider evaluation without inferring missing regime fields."""
    if evaluation is None:
        return {"status": "unavailable"}
    decision_ms = _evaluation_time(evaluation)
    readiness = mapping(evaluation.get("readiness"), "evaluation readiness")
    output = {
        "status": "observed",
        "strategy_id": evaluation.get("strategy_id"),
        "decision_time_ms": decision_ms,
        "decision_action": evaluation.get("decision_action"),
        "eligible": evaluation.get("eligible"),
        "reason": evaluation.get("reason"),
        "side": evaluation.get("side"),
        "primary_regime": evaluation.get("primary_regime"),
        "state_1m": evaluation.get("state_1m"),
        "state_5m": evaluation.get("state_5m"),
        "context_15m": evaluation.get("context_15m"),
        "confidence": evaluation.get("confidence"),
        "readiness": dict(readiness),
    }
    if observed_for_ms is not None:
        output["observation_lag_ms"] = observed_for_ms - decision_ms
    return output


def _post_exit_paths(
    candles: Mapping[int, _Candle],
    side: str,
    exit_ms: int,
    exit_price: float,
    horizons: Sequence[int],
) -> dict[str, object]:
    first_ms = ((exit_ms + _MINUTE_MS - 1) // _MINUTE_MS) * _MINUTE_MS
    return {
        str(horizon): _resolve_path(candles, side, exit_price, first_ms, horizon)
        for horizon in horizons
    }


def _resolve_path(
    candles: Mapping[int, _Candle],
    side: str,
    exit_price: float,
    first_ms: int,
    horizon: int,
) -> dict[str, object]:
    expected = tuple(first_ms + offset * _MINUTE_MS for offset in range(horizon))
    if not candles:
        return {"status": "missing_data"}
    if max(candles) < expected[-1]:
        return {"status": "censored"}
    if any(timestamp not in candles for timestamp in expected):
        return {"status": "missing_data"}
    path = tuple(candles[timestamp] for timestamp in expected)
    direction = 1.0 if side == "long" else -1.0
    close_bps = direction * (path[-1].close / exit_price - 1.0) * 10_000.0
    highest = max(item.high for item in path)
    lowest = min(item.low for item in path)
    upward_bps = (highest / exit_price - 1.0) * 10_000.0
    downward_bps = (1.0 - lowest / exit_price) * 10_000.0
    favorable = upward_bps if direction > 0.0 else downward_bps
    adverse = downward_bps if direction > 0.0 else upward_bps
    return {
        "status": "resolved",
        "first_candle_timestamp_ms": expected[0],
        "last_candle_timestamp_ms": expected[-1],
        "last_close_price": path[-1].close,
        "lowest_price": lowest,
        "highest_price": highest,
        "directional_close_return_bps": close_bps,
        "favorable_excursion_bps": max(0.0, favorable),
        "adverse_excursion_bps": max(0.0, adverse),
        "interpretation": _path_interpretation(close_bps),
    }


def project_protective_stop(trade: Record) -> dict[str, object] | None:
    """Project one lifecycle's exact accepted protective-stop evidence."""
    value = trade.get("protective_stop")
    if value is None:
        return None
    values = mapping(value, "trade protective stop")
    oid = nonnegative_int(values.get("oid"), "protective-stop oid")
    trigger = number(values.get("trigger_price"), "protective-stop trigger")
    if oid < 1 or trigger <= 0.0:
        raise ValueError("trade protective stop requires positive identity and trigger")
    return {"oid": oid, "trigger_price": trigger}


def _path_interpretation(directional_close_return_bps: float) -> str:
    if directional_close_return_bps > 0.0:
        return "continued_original_direction"
    if directional_close_return_bps < 0.0:
        return "reversed_against_original_direction"
    return "unchanged"
