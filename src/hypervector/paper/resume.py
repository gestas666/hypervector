"""Validated restart state for the persistent Hypervelocity shadow portfolio."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from hypervector.strategies.hypervelocity_contract import is_hypervelocity_strategy


class ShadowResumeError(ValueError):
    """Raised when persisted shadow state cannot be trusted."""


@dataclass(frozen=True)
class ShadowPortfolioResume:
    """Authoritative portfolio state recovered from one filled shadow run."""

    run_id: str
    init_cash: float
    position_qty: float
    position_avg_px: float
    realized_pnl: float
    unrealized_pnl: float
    equity: float
    state_asof: str
    last_exit_at: str | None


def load_shadow_portfolio_resume(
    ledger_path: Path,
    *,
    symbol: str,
    timeframe: str,
) -> ShadowPortfolioResume | None:
    """Load the latest Hypervelocity shadow run that contains a filled entry."""
    if not ledger_path.is_file():
        return None
    rows = _read_matching_rows(ledger_path, symbol=symbol, timeframe=timeframe)
    selected_run_id = _latest_filled_run_id(rows)
    if selected_run_id is None:
        return None
    run_rows = [row for row in rows if row.get("run_id") == selected_run_id]
    state = _latest_portfolio_state(run_rows, selected_run_id)
    init_cash = _initial_cash(run_rows, selected_run_id)
    qty = _required_number(state, "position_qty", selected_run_id)
    avg_px = _position_average(state, qty=qty, run_id=selected_run_id)
    realized = _required_number(state, "realized_pnl", selected_run_id)
    unrealized = _number(state, "unrealized_pnl") or 0.0
    equity = _number(state, "equity")
    if equity is None:
        equity = init_cash + realized + unrealized
    if init_cash <= 0.0 or (abs(qty) > 0.0 and avg_px <= 0.0):
        raise ShadowResumeError(
            f"filled shadow run {selected_run_id!r} has inconsistent portfolio state"
        )
    last_exit_at = next(
        (
            str(row.get("feed_ts"))
            for row in reversed(run_rows)
            if row.get("action") == "close" and row.get("feed_ts")
        ),
        None,
    )
    return ShadowPortfolioResume(
        run_id=selected_run_id,
        init_cash=init_cash,
        position_qty=qty,
        position_avg_px=avg_px,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        equity=equity,
        state_asof=str(state.get("feed_ts") or "unknown"),
        last_exit_at=last_exit_at,
    )


def _latest_portfolio_state(
    rows: list[dict[str, object]], run_id: str
) -> dict[str, object]:
    state = next(
        (
            row
            for row in reversed(rows)
            if _number(row, "position_qty") is not None
            and _number(row, "realized_pnl") is not None
        ),
        None,
    )
    if state is None:
        raise ShadowResumeError(f"filled shadow run {run_id!r} has no portfolio state")
    return state


def _initial_cash(rows: list[dict[str, object]], run_id: str) -> float:
    value = next(
        (value for row in rows if (value := _number(row, "init_cash")) is not None),
        None,
    )
    if value is None:
        raise ShadowResumeError(f"filled shadow run {run_id!r} has no initial cash")
    return value


def _position_average(row: dict[str, object], *, qty: float, run_id: str) -> float:
    value = _number(row, "position_avg_px")
    if value is not None:
        return value
    if abs(qty) == 0.0:
        return 0.0
    raise ShadowResumeError(
        f"filled shadow run {run_id!r} has no finite position_avg_px"
    )


def _read_matching_rows(
    ledger_path: Path,
    *,
    symbol: str,
    timeframe: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with ledger_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ShadowResumeError(
                    f"invalid shadow ledger JSON at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(row, dict):
                raise ShadowResumeError(
                    f"invalid shadow ledger row at line {line_number}: expected object"
                )
            if (
                row.get("execution_mode") == "shadow"
                and is_hypervelocity_strategy(str(row.get("strategy_name") or ""))
                and row.get("symbol") == symbol
                and row.get("timeframe") == timeframe
            ):
                rows.append(row)
    return rows


def _latest_filled_run_id(rows: list[dict[str, object]]) -> str | None:
    selected: str | None = None
    for row in rows:
        if row.get("action") not in {"enter_long", "enter_short"}:
            continue
        if row.get("skipped") is True:
            continue
        quantity = _number(row, "fill_qty")
        if quantity is None:
            quantity = _number(row, "qty")
        run_id = row.get("run_id")
        if quantity is not None and abs(quantity) > 0.0 and isinstance(run_id, str):
            selected = run_id
    return selected


def _number(row: dict[str, object], key: str) -> float | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _required_number(row: dict[str, object], key: str, run_id: str) -> float:
    value = _number(row, key)
    if value is None:
        raise ShadowResumeError(f"filled shadow run {run_id!r} has no finite {key}")
    return value
