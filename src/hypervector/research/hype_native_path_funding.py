"""Official-funding reconciliation for a HYPE-native depth path."""

from __future__ import annotations

from collections.abc import Mapping
import math

import pandas as pd

from hypervector.data.hl_funding_evidence import HlFundingEvidence
from hypervector.research.hype_funding_events import build_hype_funding_events

_STRATEGY_ID = "hype_native_breakout_onset_bidirectional_v2"


def reconcile_hype_native_path_funding(
    path: Mapping[str, object],
    funding: HlFundingEvidence,
    oracle_prices: pd.DataFrame,
    *,
    maximum_oracle_staleness_ms: int,
    horizon_minutes: int | None = 480,
) -> dict[str, object]:
    """Apply official funding rates to one causal oracle-valued path."""
    _require_report_only(path)
    execution = _mapping(path.get("execution_path"), "execution_path")
    entry_ms = _integer(execution, "entry_book_time_ms")
    exit_ms, before, exit_basis = _selected_exit(execution, horizon_minutes)
    quantity = _positive_number(execution, "entry_quantity")
    side = _side(_mapping(path.get("source_signal"), "source_signal"))
    events = build_hype_funding_events(
        funding,
        oracle_prices,
        side=side,
        quantity=quantity,
        entry_time_ms=entry_ms,
        exit_time_ms=exit_ms,
        maximum_oracle_staleness_ms=maximum_oracle_staleness_ms,
    )
    funding_cashflow = sum(float(row["cashflow_usd"]) for row in events)
    return {
        "schema_version": 1,
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "funding_rate_source": "hl_funding_history",
            "funding_reference_source": "0xarchive_hyperliquid_oracle_price",
        },
        "symbol": "HYPE",
        "strategy_id": _STRATEGY_ID,
        "side": side,
        "entry_book_time_ms": entry_ms,
        "exit_book_time_ms": exit_ms,
        "exit_basis": exit_basis,
        "horizon_minutes": horizon_minutes,
        "funding_event_count": len(events),
        "funding_events": events,
        "funding_cashflow_usd": funding_cashflow,
        "net_pnl_usd_before_funding": before,
        "net_pnl_usd_after_funding": before + funding_cashflow,
    }


def _selected_exit(
    execution: Mapping[str, object], horizon_minutes: int | None
) -> tuple[int, float, str]:
    if horizon_minutes is not None:
        horizon = _horizon(execution, horizon_minutes)
        return (
            _integer(horizon, "book_time_ms"),
            _number(horizon, "net_pnl_usd"),
            "fixed_horizon_bbo_proxy",
        )
    if execution.get("status") != "resolved":
        raise ValueError("HYPE resolved path exit is unavailable")
    return (
        _integer(execution, "exit_book_time_ms"),
        _number(execution, "net_pnl_usd_before_funding"),
        "resolved_path_exit",
    )


def _require_report_only(path: Mapping[str, object]) -> None:
    contract = _mapping(path.get("contract"), "contract")
    identity = _mapping(path.get("identity"), "identity")
    if contract.get("report_only") is not True:
        raise ValueError("HYPE path must be report-only")
    if contract.get("execution_authority") != "none":
        raise ValueError("HYPE path must have no execution authority")
    if identity.get("symbol") != "HYPE":
        raise ValueError("HYPE path must have exact HYPE symbol identity")
    if identity.get("candidate_strategy_id") != _STRATEGY_ID:
        raise ValueError("HYPE path candidate strategy identity is invalid")


def _horizon(execution: Mapping[str, object], minutes: int) -> Mapping[str, object]:
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0:
        raise ValueError("horizon_minutes must be a positive integer")
    horizons = _mapping(execution.get("horizons"), "horizons")
    selected = _mapping(horizons.get(str(minutes)), "selected horizon")
    if selected.get("status") != "resolved_bbo_proxy":
        raise ValueError("selected HYPE horizon is not resolved")
    return selected


def _side(source: Mapping[str, object]) -> str:
    value = source.get("side")
    if value not in {"long", "short"}:
        raise ValueError("HYPE path side must be long or short")
    return str(value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _integer(row: Mapping[str, object], field: str) -> int:
    return _integer_value(row.get(field), field)


def _integer_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _number(row: Mapping[str, object], field: str) -> float:
    return _number_value(row.get(field), field, positive=False)


def _positive_number(row: Mapping[str, object], field: str) -> float:
    return _number_value(row.get(field), field, positive=True)


def _number_value(value: object, label: str, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    output = float(value)
    if not math.isfinite(output) or (positive and output <= 0.0):
        qualifier = "positive and finite" if positive else "finite"
        raise ValueError(f"{label} must be {qualifier}")
    return output
