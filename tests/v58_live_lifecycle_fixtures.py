"""Shared authority-none lifecycle fixtures for V58 research tests."""

from __future__ import annotations


def empty_trade_reflections() -> dict[str, object]:
    """Return a complete compatible-history contract with no closed trades."""
    return {
        "schema_version": 1,
        "mode": "cohort_trade_reflections",
        "scope": "compatible_profile_history",
        "closed_trades": 0,
        "trades": [],
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_strategy_changes": False,
            "runtime_strategy_changed": False,
        },
    }
