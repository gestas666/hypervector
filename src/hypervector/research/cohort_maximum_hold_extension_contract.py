"""Static contract and limitations for maximum-hold extension evidence."""

from __future__ import annotations


def extension_outcome_contract() -> dict[str, object]:
    """Return the fail-closed authority contract for extension outcomes."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "performance_gate": False,
        "balance_gate": False,
    }


def extension_outcome_limitations() -> list[str]:
    """Return the declared evidence limits for extension outcomes."""
    return [
        "the soft exit is an estimate rather than an order submitted at the boundary",
        "the estimate reuses the actual later exit fill/reference ratio and fee rate",
        "completed one-minute candles do not reveal private queue or intra-minute path",
        "a positive delta is descriptive evidence rather than an automatic hold rule",
        "this report cannot gate, size, route, close, or submit a trade",
    ]
