"""Report-only execution cash-drag diagnostics for resolved cohort trades."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_trade_performance import (
    build_all_time_trade_performance,
)

Record = Mapping[str, object]


def build_execution_drag_diagnostic(trades: Sequence[Record]) -> dict[str, object]:
    """Measure fees less realized funding without changing strategy authority."""
    return {
        "schema_version": 1,
        "mode": "cohort_execution_cash_drag_diagnostic_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
            "automatic_strategy_changes": False,
            "performance_gate": False,
        },
        "performance": build_all_time_trade_performance(trades),
        "metric_definition": {
            "execution_cash_drag_usd": "fees_usd minus realized funding_usd",
            "ratio_denominator": "positive pre-fee and pre-funding market PnL",
            "slippage_included": False,
        },
        "limitations": [
            "the ratio is descriptive and has no universal acceptance threshold",
            "realized entry and exit slippage require separate quote evidence",
            "mixed strategy profiles are not treated as one performance contract",
        ],
    }
