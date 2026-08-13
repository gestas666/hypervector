"""Authority and limitation labels for cohort trade reflections."""

from __future__ import annotations


def trade_reflection_contract() -> dict[str, object]:
    """Declare the non-executable trade-reflection authority boundary."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }


def trade_reflection_limitations() -> list[str]:
    """Disclose the causal and execution limits of reflection evidence."""
    return [
        "entry follow-through continues after the real exit and is not trade PnL",
        "completed-candle stop crosses do not estimate trigger-fill slippage",
        "post-exit paths use completed one-minute candles rather than executable fills",
        "positive directional return means continuation, not proof the exit was wrong",
        "context is unavailable when compatible cohort routing history is absent",
        "this report cannot alter strategy state or submit orders",
    ]
