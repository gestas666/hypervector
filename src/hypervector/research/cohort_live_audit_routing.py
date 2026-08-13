"""Validate and summarize entry-provider and backend lifecycle routing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    configured_symbols,
    event_rows,
    executable_provider_pairs,
    object_list,
    payload,
    text,
    text_counter,
)

Record = Mapping[str, object]
_LIFECYCLE_CLOSE_STRATEGIES = frozenset(
    {"cohort_maximum_hold", "operator_override:manual_close"}
)
_OPERATOR_PREFIX = "operator_override:"


def build_routing_summary(
    records: Sequence[Record], identity: Record
) -> dict[str, object]:
    """Return routing evidence after validating every executable action."""
    cycles = event_rows(records, "intent_routing")
    actions = [item for row in cycles for item in object_list(payload(row), "actions")]
    withheld = [
        item for row in cycles for item in object_list(payload(row), "withheld")
    ]
    executable = executable_provider_pairs(identity)
    symbols = frozenset(configured_symbols(identity))
    unauthorized = sorted(
        _action_key(action)
        for action in actions
        if not _action_is_authorized(action, executable, symbols)
    )
    if unauthorized:
        raise ValueError(
            f"live actions exceed configured execution scope: {unauthorized}"
        )
    return _summary(
        cycles,
        actions,
        withheld,
        executable,
        len(event_rows(records, "strategy_intent")),
    )


def _action_is_authorized(
    action: Record,
    executable: frozenset[str],
    symbols: frozenset[str],
) -> bool:
    strategy = text(action.get("strategy_id"), "action strategy")
    symbol = text(action.get("symbol"), "action symbol")
    kind = action.get("action")
    if strategy in _LIFECYCLE_CLOSE_STRATEGIES:
        return kind == "close" and symbol in symbols
    if strategy.startswith(_OPERATOR_PREFIX):
        provider = strategy.removeprefix(_OPERATOR_PREFIX)
        return kind == "enter" and f"{provider}|{symbol}" in executable
    return f"{strategy}|{symbol}" in executable


def _action_key(action: Record) -> str:
    strategy = text(action.get("strategy_id"), "action strategy")
    symbol = text(action.get("symbol"), "action symbol")
    return f"{strategy}|{symbol}"


def _summary(
    cycles: Sequence[Record],
    actions: Sequence[Record],
    withheld: Sequence[Record],
    executable: frozenset[str],
    strategy_intents: int,
) -> dict[str, object]:
    return {
        "cycles": len(cycles),
        "strategy_intents": strategy_intents,
        "actions": len(actions),
        "lifecycle_actions": sum(
            action.get("strategy_id") in _LIFECYCLE_CLOSE_STRATEGIES
            for action in actions
        ),
        "withheld": len(withheld),
        "actions_by_strategy": text_counter(actions, "strategy_id"),
        "actions_by_symbol": text_counter(actions, "symbol"),
        "actions_by_side": text_counter(actions, "side"),
        "withheld_reasons": text_counter(withheld, "reason"),
        "executable_provider_symbols": sorted(executable),
    }
