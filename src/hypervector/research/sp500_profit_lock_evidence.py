"""Shared frozen inputs for SP500 profit-lock evidence commands."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

import pandas as pd

from hypervector.research.cohort_profit_lock_l2_proxy import ProxyLifecycle

SP500_PROFIT_LOCK_STRATEGY: Final = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
SP500_PROFIT_LOCK_SYMBOL: Final = "xyz:SP500"
SP500_PROFIT_LOCK_FRICTION: Final = "stress"
SP500_PROFIT_LOCK_PHASES: Final = ("development", "validation")
_REQUIRED: Final = frozenset(
    {
        "strategy_id",
        "symbol",
        "phase",
        "friction",
        "direction",
        "entry_time_utc",
        "exit_time_utc",
        "entry_price",
        "exit_price",
        "quantity",
        "gross_pnl_usd",
        "fees_usd",
    }
)


def load_sp500_profit_lock_lifecycles(
    path: Path,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> tuple[ProxyLifecycle, ...]:
    """Load the frozen SP500 stress lifecycle contract within optional bounds."""
    _validate_bounds(start_ms, end_ms)
    frame = pd.read_parquet(path)
    missing = sorted(_REQUIRED.difference(frame.columns))
    if missing:
        raise ValueError(f"SP500 lifecycle evidence missing columns: {missing}")
    selected = frame.loc[_contract_mask(frame)].copy()
    if selected.empty:
        raise ValueError("SP500 profit-lock selection produced no lifecycles")
    selected["entry_time_utc"] = pd.to_datetime(selected["entry_time_utc"], utc=True)
    selected["exit_time_utc"] = pd.to_datetime(selected["exit_time_utc"], utc=True)
    rows = tuple(_lifecycle(row) for row in selected.itertuples(index=False))
    bounded = tuple(row for row in rows if _inside(row, start_ms, end_ms))
    identities = [row.lifecycle_id for row in bounded]
    if not bounded:
        raise ValueError("SP500 archive bounds produced no lifecycles")
    if len(set(identities)) != len(identities):
        raise ValueError("SP500 profit-lock lifecycle identities are not unique")
    return bounded


def profit_lock_lifecycle_bounds(
    lifecycles: tuple[ProxyLifecycle, ...],
) -> tuple[int, int]:
    """Return the exact earliest entry and latest exit boundaries."""
    if not lifecycles:
        raise ValueError("SP500 profit-lock lifecycle bounds require rows")
    return (
        min(row.entry_timestamp_ms for row in lifecycles),
        max(row.exit_timestamp_ms for row in lifecycles),
    )


def sp500_profit_lock_selection(
    lifecycles: tuple[ProxyLifecycle, ...],
) -> dict[str, object]:
    """Describe the immutable SP500 lifecycle selection contract."""
    return {
        "strategy_id": SP500_PROFIT_LOCK_STRATEGY,
        "symbol": SP500_PROFIT_LOCK_SYMBOL,
        "friction": SP500_PROFIT_LOCK_FRICTION,
        "phases": list(SP500_PROFIT_LOCK_PHASES),
        "selected_lifecycles": len(lifecycles),
    }


def assess_sp500_profit_lock(report: Mapping[str, object]) -> dict[str, object]:
    """Apply the frozen cross-partition disposition rule to one report."""
    thresholds = _mapping(report.get("thresholds_ms"), "thresholds")
    threshold = _mapping(thresholds.get("15000"), "15-second threshold")
    phases = _mapping(threshold.get("by_phase"), "phase summaries")
    development = _mapping(phases.get("development"), "development summary")
    validation = _mapping(phases.get("validation"), "validation summary")
    policies = (
        "a25_floor15_trail10",
        "a40_floor15_trail20",
        "a60_floor15_trail30",
    )
    dispositions = {
        policy: _policy_disposition(
            _mapping(development.get(policy), f"{policy} development"),
            _mapping(validation.get(policy), f"{policy} validation"),
        )
        for policy in policies
    }
    supportive = "research_supportive_not_authorized" in dispositions.values()
    return {
        "overall_disposition": (
            "research_supportive_not_live_authorized"
            if supportive
            else "no_exit_policy_change"
        ),
        **dispositions,
        "execution_effect": "report_only",
    }


def _contract_mask(frame: pd.DataFrame) -> pd.Series:
    return (
        (frame["strategy_id"] == SP500_PROFIT_LOCK_STRATEGY)
        & (frame["symbol"] == SP500_PROFIT_LOCK_SYMBOL)
        & (frame["friction"] == SP500_PROFIT_LOCK_FRICTION)
        & frame["phase"].isin(SP500_PROFIT_LOCK_PHASES)
    )


def _policy_disposition(
    development: Mapping[str, object], validation: Mapping[str, object]
) -> str:
    if not _supportive(validation):
        return "rejected_validation_after_cost_negative"
    if not _supportive(development):
        return "withheld_no_cross_partition_support"
    return "research_supportive_not_authorized"


def _supportive(summary: Mapping[str, object]) -> bool:
    net = summary.get("estimated_net_ex_funding_usd")
    profit_factor = summary.get("profit_factor")
    valid_net = isinstance(net, (int, float)) and not isinstance(net, bool) and net > 0
    valid_pf = profit_factor is None or (
        isinstance(profit_factor, (int, float))
        and not isinstance(profit_factor, bool)
        and profit_factor > 1
    )
    return valid_net and valid_pf


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"SP500 profit-lock {label} is not a mapping")
    return value


def _lifecycle(row: object) -> ProxyLifecycle:
    entry = getattr(row, "entry_time_utc")
    exit_time = getattr(row, "exit_time_utc")
    entry_ms = int(entry.timestamp() * 1_000)
    return ProxyLifecycle(
        lifecycle_id=(f"{SP500_PROFIT_LOCK_SYMBOL}:{getattr(row, 'phase')}:{entry_ms}"),
        phase=str(getattr(row, "phase")),
        side=str(getattr(row, "direction")),
        entry_timestamp_ms=entry_ms,
        exit_timestamp_ms=int(exit_time.timestamp() * 1_000),
        entry_price=float(getattr(row, "entry_price")),
        exit_price=float(getattr(row, "exit_price")),
        quantity=float(getattr(row, "quantity")),
        gross_pnl_usd=float(getattr(row, "gross_pnl_usd")),
        fees_usd=float(getattr(row, "fees_usd")),
    )


def _inside(row: ProxyLifecycle, start_ms: int | None, end_ms: int | None) -> bool:
    return (start_ms is None or row.entry_timestamp_ms >= start_ms) and (
        end_ms is None or row.exit_timestamp_ms < end_ms
    )


def _validate_bounds(start_ms: int | None, end_ms: int | None) -> None:
    values = (start_ms, end_ms)
    if any(
        isinstance(value, bool) or (value is not None and value < 0) for value in values
    ):
        raise ValueError("SP500 profit-lock bounds must be nonnegative integers")
    if start_ms is not None and end_ms is not None and end_ms <= start_ms:
        raise ValueError("SP500 profit-lock end bound must follow its start")
