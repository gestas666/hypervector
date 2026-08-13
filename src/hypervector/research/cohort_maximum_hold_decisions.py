"""Validated report-only projection of live maximum-hold decisions."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import math

Record = Mapping[str, object]
_LATEST_LIMIT = 50


def build_maximum_hold_decision_evidence(
    records: Sequence[Record],
    expected_provider_symbols: frozenset[str],
) -> dict[str, object]:
    """Summarize causal deadline decisions without granting execution authority."""
    decisions = _validated_decisions(records, expected_provider_symbols)
    soft = [row for row in decisions if _decision_stage(row) == "soft"]
    terminal = [row for row in decisions if _decision_stage(row) == "terminal"]
    outcome_counts = Counter(_text(row["outcome"], "outcome") for row in soft)
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in soft:
        key = f"{row['strategy_id']}|{row['symbol']}"
        grouped[key].update((_text(row["outcome"], "outcome"),))
    terminal_providers = {f"{row['strategy_id']}|{row['symbol']}" for row in terminal}
    terminal_reasons = Counter(
        _text(row["exit_reason"], "exit_reason") for row in terminal
    )
    return {
        "contract": _contract(),
        "summary": {
            "observed": len(soft),
            "extended": outcome_counts["extend"],
            "exited": outcome_counts["exit"],
            "provider_symbols": len(grouped),
        },
        "by_provider_symbol": {
            key: {
                "observed": sum(counts.values()),
                "extended": counts["extend"],
                "exited": counts["exit"],
            }
            for key, counts in sorted(grouped.items())
        },
        "latest_decisions": soft[-_LATEST_LIMIT:],
        "terminal_exit_summary": {
            "observed": len(terminal),
            "provider_symbols": len(terminal_providers),
            "by_exit_reason": dict(sorted(terminal_reasons.items())),
        },
        "latest_terminal_exits": terminal[-_LATEST_LIMIT:],
    }


def _validated_decisions(
    records: Sequence[Record],
    expected_provider_symbols: frozenset[str],
) -> list[dict[str, object]]:
    decisions: list[dict[str, object]] = []
    identities: set[str] = set()
    for record in records:
        if record.get("event_type") != "maximum_hold_decision":
            continue
        payload = _mapping(record.get("payload"), "maximum-hold payload")
        validated = _validated_payload(payload, expected_provider_symbols)
        decision_id = _text(validated["decision_id"], "decision_id")
        if decision_id in identities:
            raise ValueError(f"duplicate maximum-hold decision: {decision_id}")
        identities.add(decision_id)
        decisions.append(validated)
    return decisions


def _validated_payload(
    payload: Record,
    expected_provider_symbols: frozenset[str],
) -> dict[str, object]:
    decision_id = _text(payload.get("decision_id"), "decision_id")
    lifecycle_id = _text(payload.get("lifecycle_id"), "lifecycle_id")
    symbol = _text(payload.get("symbol"), "symbol")
    strategy = _text(payload.get("strategy_id"), "strategy_id")
    stage = _decision_stage(payload)
    _validate_identity(decision_id, lifecycle_id, symbol, stage)
    if f"{strategy}|{symbol}" not in expected_provider_symbols:
        raise ValueError("maximum-hold provider-symbol is outside run identity")
    _validate_timing(payload)
    _validate_outcome(payload)
    _bounded_score(payload.get("structure_alignment_score"), "alignment score", True)
    _alignment_threshold(payload.get("structure_alignment_threshold"))
    for key in ("provider_evaluation", "canonical_evaluation"):
        if payload.get(key) is not None:
            _mapping(payload.get(key), key)
    if stage == "terminal":
        _validate_terminal_link(payload, lifecycle_id)
    return dict(payload)


def _validate_identity(
    decision_id: str, lifecycle_id: str, symbol: str, stage: str
) -> None:
    if decision_id != f"{lifecycle_id}:{stage}_maximum_hold":
        raise ValueError("maximum-hold decision identity is inconsistent")
    symbol_prefix = f"{symbol}:"
    oid = lifecycle_id.removeprefix(symbol_prefix)
    if not lifecycle_id.startswith(symbol_prefix) or not oid.isdigit() or int(oid) <= 0:
        raise ValueError("maximum-hold lifecycle identity is inconsistent")


def _validate_terminal_link(payload: Record, lifecycle_id: str) -> None:
    trigger = _text(payload.get("trigger_decision_id"), "trigger_decision_id")
    extension = _integer(payload.get("extension_duration_ms"), "extension duration")
    decision = _integer(payload.get("decision_time_ms"), "decision_time_ms")
    soft = _integer(payload.get("soft_deadline_timestamp_ms"), "soft deadline")
    if trigger != f"{lifecycle_id}:soft_maximum_hold" or decision - soft != extension:
        raise ValueError("terminal maximum-hold linkage is inconsistent")
    if payload.get("outcome") != "exit":
        raise ValueError("terminal maximum-hold decision must exit")


def _decision_stage(payload: Record) -> str:
    stage = _text(payload.get("decision_stage", "soft"), "decision_stage")
    if stage not in {"soft", "terminal"}:
        raise ValueError("maximum-hold decision stage is unsupported")
    return stage


def _validate_timing(payload: Record) -> None:
    decision = _integer(payload.get("decision_time_ms"), "decision_time_ms")
    opened = _integer(payload.get("opened_at_ms"), "opened_at_ms")
    elapsed = _integer(payload.get("elapsed_ms"), "elapsed_ms")
    soft = _integer(payload.get("soft_deadline_timestamp_ms"), "soft deadline")
    hard_value = payload.get("hard_deadline_timestamp_ms")
    hard = _integer(hard_value, "hard deadline") if hard_value is not None else None
    if decision - opened != elapsed or decision < soft:
        raise ValueError("maximum-hold timing is inconsistent")
    if hard is not None and hard <= soft:
        raise ValueError("maximum-hold hard deadline must follow soft deadline")


def _validate_outcome(payload: Record) -> None:
    side = _text(payload.get("side"), "side")
    outcome = _text(payload.get("outcome"), "outcome")
    reason = payload.get("exit_reason")
    if side not in {"long", "short"}:
        raise ValueError("maximum-hold side must be long or short")
    if outcome not in {"extend", "exit"}:
        raise ValueError("maximum-hold outcome must be extend or exit")
    if outcome == "exit" and not isinstance(reason, str):
        raise ValueError("maximum-hold exit outcome requires exit_reason")
    if outcome == "extend" and reason is not None:
        raise ValueError("maximum-hold extension cannot have exit_reason")


def _bounded_score(value: object, label: str, optional: bool = False) -> None:
    if value is None and optional:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"maximum-hold {label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not -1.0 <= number <= 1.0:
        raise ValueError(f"maximum-hold {label} is outside [-1,1]")


def _alignment_threshold(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("maximum-hold alignment threshold must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError("maximum-hold alignment threshold is outside [0,1]")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"maximum-hold {label} must be a nonnegative integer")
    return value


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"maximum-hold {label} must be non-empty text")
    return value.strip()


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "balance_gate": False,
    }
