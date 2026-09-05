"""Immutable report metadata for causal near-miss path evidence."""

from __future__ import annotations


def nearmiss_report_contract() -> dict[str, object]:
    """Describe the diagnostic's report-only execution boundary."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "counterfactual_only": True,
        "orders_or_fills_assumed": False,
        "runtime_strategy_changed": False,
    }


def nearmiss_report_limitations() -> list[str]:
    """Return limitations that prevent proxy evidence becoming live authority."""
    return [
        "completed trade candles do not prove a Hyperliquid mark-price stop trigger",
        "sampled BBO proves an executable quote later crossed the stop level, not a fill",
        "one-minute OHLC cannot order a target and stop touched inside the same candle",
        "the modeled hurdle is not realized execution friction",
        "one near miss cannot establish strategy expectancy or authorize relaxation",
    ]
