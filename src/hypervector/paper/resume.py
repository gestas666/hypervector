"""Validated restart state for the persistent Hypervelocity shadow portfolio."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Mapping

from hypervector.strategies.hypervelocity_contract import is_hypervelocity_strategy
from hypervector.paper.event_resume import PendingTargetResume, event_resume_details
from hypervector.paper.portfolio_migration import migrated_portfolio_spec
from hypervector.paper.position_hold_resume import recover_position_hold_resume
from hypervector.paper.position_math import normalized_position_quantity

_EQUITY_ABS_TOLERANCE_USD = 0.01
_EQUITY_REL_TOLERANCE = 1e-9


class ShadowResumeError(ValueError):
    """Raised when persisted shadow state cannot be trusted."""


@dataclass(frozen=True)
class PendingMakerResume:
    """Durable state for one unmatched post-only entry order."""

    direction: Literal["long", "short"]
    qty: float
    limit_price: float
    submitted_at: str
    conviction: float | None
    conviction_source: str | None
    metalabel_p: float | None
    metalabel_bundle_id: str | None
    client_order_id: str | None = None
    cumulative_quantity: float = 0.0
    remaining_quantity: float | None = None


@dataclass(frozen=True)
class ShadowPortfolioResume:
    """Authoritative portfolio and maker-order state recovered from shadow."""

    run_id: str
    init_cash: float
    position_qty: float
    position_avg_px: float
    realized_pnl: float
    unrealized_pnl: float
    equity: float
    state_asof: str
    last_exit_at: str | None
    pending_entry: PendingMakerResume | None
    expired_entry_direction: Literal["long", "short"] | None
    completed_trade_direction: Literal["long", "short"] | None
    portfolio_fingerprint: str | None
    portfolio_profile_changed_from: str | None
    execution_model: str
    active_targets: tuple[PendingTargetResume, ...]
    next_order_sequence: int
    open_position_fees_usd: float
    open_position_funding_net_usd: float
    liquidation_cooldown_until_ms: int | None = None
    position_opened_at: str | None = None
    maximum_hold_seconds: float | None = None


def normalize_shadow_portfolio_resume(
    resume: ShadowPortfolioResume,
) -> ShadowPortfolioResume:
    """Normalize sub-epsilon closed-fill residue to an authoritative flat state."""
    if normalized_position_quantity(resume.position_qty) != 0.0:
        return resume
    return replace(
        resume,
        position_qty=0.0,
        position_avg_px=0.0,
        unrealized_pnl=0.0,
        active_targets=(),
        open_position_fees_usd=0.0,
        open_position_funding_net_usd=0.0,
        liquidation_cooldown_until_ms=None,
        position_opened_at=None,
        maximum_hold_seconds=None,
    )


def load_shadow_portfolio_resume(
    ledger_path: Path,
    *,
    symbol: str,
    timeframe: str,
    expected_spec: Mapping[str, object] | None = None,
) -> ShadowPortfolioResume | None:
    """Load the latest Hypervelocity shadow run with durable trading state."""
    if not ledger_path.is_file():
        return None
    rows = _read_matching_rows(ledger_path, symbol=symbol, timeframe=timeframe)
    selected_run_id = _latest_persistent_run_id(rows)
    if selected_run_id is None:
        return None
    run_rows = [row for row in rows if row.get("run_id") == selected_run_id]
    pending_entry = _latest_pending_entry(run_rows, selected_run_id)
    expired_direction = _latest_expired_entry_direction(run_rows)
    completed_direction = _latest_completed_trade_direction(run_rows)
    event_details = event_resume_details(run_rows)
    state = _latest_portfolio_state(run_rows, selected_run_id)
    init_cash = _initial_cash(run_rows, selected_run_id)
    qty = normalized_position_quantity(
        _required_number(state, "position_qty", selected_run_id)
    )
    avg_px = _position_average(state, qty=qty, run_id=selected_run_id)
    try:
        hold = recover_position_hold_resume(run_rows, final_position_qty=qty)
    except ValueError as exc:
        raise ShadowResumeError(
            f"shadow run {selected_run_id!r} has invalid hold state: {exc}"
        ) from exc
    realized = _required_number(state, "realized_pnl", selected_run_id)
    unrealized = _number(state, "unrealized_pnl") or 0.0
    equity = _number(state, "equity")
    if equity is None:
        equity = init_cash + realized + unrealized
    if init_cash <= 0.0 or (abs(qty) > 0.0 and avg_px <= 0.0):
        raise ShadowResumeError(
            f"filled shadow run {selected_run_id!r} has inconsistent portfolio state"
        )
    _validate_equity_identity(
        run_id=selected_run_id,
        init_cash=init_cash,
        realized=realized,
        unrealized=unrealized,
        equity=equity,
    )
    fingerprint, changed_from = _validate_portfolio_spec(
        run_rows,
        run_id=selected_run_id,
        position_qty=qty,
        has_pending_entry=pending_entry is not None,
        expected_spec=expected_spec,
    )
    terminal_actions = {"close", "liquidation", "backstop_liquidation"}
    last_exit_at = next(
        (
            str(row.get("feed_ts"))
            for row in reversed(run_rows)
            if row.get("action") in terminal_actions and row.get("feed_ts")
        ),
        None,
    )
    state_asof = str(state.get("feed_ts") or "unknown")
    if state.get("action") == "session_start" and state.get("portfolio_state_asof"):
        state_asof = str(state["portfolio_state_asof"])
    resume = ShadowPortfolioResume(
        run_id=selected_run_id,
        init_cash=init_cash,
        position_qty=qty,
        position_avg_px=avg_px,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        equity=equity,
        state_asof=state_asof,
        last_exit_at=last_exit_at,
        pending_entry=pending_entry,
        expired_entry_direction=expired_direction,
        completed_trade_direction=completed_direction,
        portfolio_fingerprint=fingerprint,
        portfolio_profile_changed_from=changed_from,
        execution_model=event_details.execution_model,
        active_targets=event_details.active_targets,
        next_order_sequence=event_details.next_order_sequence,
        open_position_fees_usd=event_details.open_position_fees_usd,
        open_position_funding_net_usd=(event_details.open_position_funding_net_usd),
        liquidation_cooldown_until_ms=(event_details.liquidation_cooldown_until_ms),
        position_opened_at=hold.position_opened_at,
        maximum_hold_seconds=hold.maximum_hold_seconds,
    )
    return normalize_shadow_portfolio_resume(resume)


def portfolio_fingerprint(spec: Mapping[str, object]) -> str:
    """Return a stable digest of execution-affecting portfolio settings."""
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_portfolio_spec(
    rows: list[dict[str, object]],
    *,
    run_id: str,
    position_qty: float,
    has_pending_entry: bool,
    expected_spec: Mapping[str, object] | None,
) -> tuple[str | None, str | None]:
    if expected_spec is None:
        return None, None
    expected = portfolio_fingerprint(expected_spec)
    identity = next(
        (row for row in reversed(rows) if row.get("action") == "session_start"),
        None,
    )
    if identity is None:
        raise ShadowResumeError(f"filled shadow run {run_id!r} has no session identity")
    recorded_spec = identity.get("portfolio_spec")
    if not isinstance(recorded_spec, dict):
        recorded_spec = _legacy_portfolio_spec(identity)
    recorded = portfolio_fingerprint(recorded_spec)
    if recorded == expected:
        return expected, None
    migrated = migrated_portfolio_spec(
        recorded_spec,
        expected_spec,
        allow_pending_event_age_upgrade=(
            has_pending_entry and abs(position_qty) <= 1e-12
        ),
    )
    if migrated is not None and portfolio_fingerprint(migrated) == expected:
        return expected, recorded
    if abs(position_qty) > 0.0:
        raise ShadowResumeError(
            f"incompatible portfolio profile for open position in run {run_id!r}"
        )
    if has_pending_entry:
        raise ShadowResumeError(
            f"incompatible portfolio profile for pending entry in run {run_id!r}"
        )
    return expected, recorded


def _legacy_portfolio_spec(identity: dict[str, object]) -> dict[str, object]:
    keys = (
        "strategy_name",
        "symbol",
        "timeframe",
        "strategy_params",
        "position_policy",
        "exits",
        "risk",
        "execution",
    )
    return {key: identity.get(key) for key in keys}


def _validate_equity_identity(
    *,
    run_id: str,
    init_cash: float,
    realized: float,
    unrealized: float,
    equity: float,
) -> None:
    expected = init_cash + realized + unrealized
    if not math.isclose(
        equity,
        expected,
        rel_tol=_EQUITY_REL_TOLERANCE,
        abs_tol=_EQUITY_ABS_TOLERANCE_USD,
    ):
        raise ShadowResumeError(
            f"filled shadow run {run_id!r} violates portfolio equity identity"
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
    if qty == 0.0:
        return 0.0
    value = _number(row, "position_avg_px")
    if value is not None:
        return value
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


def _latest_persistent_run_id(rows: list[dict[str, object]]) -> str | None:
    selected: str | None = None
    for row in rows:
        action = row.get("action")
        quantity = _persistent_quantity(row, action)
        run_id = row.get("run_id")
        if quantity is not None and abs(quantity) > 0.0 and isinstance(run_id, str):
            selected = run_id
    return selected


def _persistent_quantity(row: dict[str, object], action: object) -> float | None:
    if action == "submit_entry":
        return _number(row, "requested_qty")
    if action not in {"enter_long", "enter_short"} or row.get("skipped") is True:
        return None
    return _number(row, "fill_qty") or _number(row, "qty")


def _latest_pending_entry(
    rows: list[dict[str, object]], run_id: str
) -> PendingMakerResume | None:
    pending: PendingMakerResume | None = None
    for row in rows:
        action = row.get("action")
        if action == "submit_entry":
            pending = _parse_pending_entry(row, run_id)
        elif action in {"cancel_entry", "rejected_entry", "expired_entry"}:
            pending = None
        elif action in {"enter_long", "enter_short"} and row.get("skipped") is not True:
            remaining = _number(row, "remaining_qty")
            order_id = row.get("client_order_id")
            if (
                pending is not None
                and remaining is not None
                and remaining > 0.0
                and order_id == pending.client_order_id
            ):
                pending = replace(
                    pending,
                    cumulative_quantity=(_number(row, "cumulative_filled_qty") or 0.0),
                    remaining_quantity=remaining,
                )
            else:
                pending = None
    return pending


def _latest_expired_entry_direction(
    rows: list[dict[str, object]],
) -> Literal["long", "short"] | None:
    """Recover a consumed TTL attempt until a non-matching regime is observed."""
    blocked: Literal["long", "short"] | None = None
    ttl_reasons = {"entry_ttl_expired", "entry_ttl_expired_during_downtime"}
    for row in rows:
        action = row.get("action")
        if (
            action == "cancel_entry" and row.get("reason") in ttl_reasons
        ) or action in {"rejected_entry", "expired_entry"}:
            side = row.get("side")
            blocked = "long" if side == "buy" else "short" if side == "sell" else None
        elif action in {"submit_entry", "enter_long", "enter_short"}:
            blocked = None
        elif (
            action == "regime_observation"
            and blocked is not None
            and "entry_direction" in row
            and row.get("entry_direction") != blocked
        ):
            blocked = None
    return blocked


def _latest_completed_trade_direction(
    rows: list[dict[str, object]],
) -> Literal["long", "short"] | None:
    """Recover the completed side until a non-matching regime is observed."""
    blocked: Literal["long", "short"] | None = None
    for row in rows:
        if (
            row.get("action")
            in {
                "close",
                "liquidation",
                "backstop_liquidation",
            }
            and row.get("skipped") is not True
        ):
            side = row.get("side")
            blocked = "long" if side == "sell" else "short" if side == "buy" else None
        elif (
            row.get("action") == "regime_observation"
            and blocked is not None
            and row.get("entry_direction") != blocked
        ):
            blocked = None
    return blocked


def _parse_pending_entry(row: dict[str, object], run_id: str) -> PendingMakerResume:
    side = row.get("side")
    qty = _required_number(row, "requested_qty", run_id)
    limit_price = _required_number(row, "fill_px", run_id)
    submitted_at = row.get("feed_ts")
    if side not in {"buy", "sell"} or qty <= 0.0 or limit_price <= 0.0:
        raise ShadowResumeError(
            f"shadow run {run_id!r} has inconsistent pending entry state"
        )
    if not isinstance(submitted_at, str) or not submitted_at:
        raise ShadowResumeError(f"shadow run {run_id!r} pending entry has no timestamp")
    return PendingMakerResume(
        direction="long" if side == "buy" else "short",
        qty=qty,
        limit_price=limit_price,
        submitted_at=submitted_at,
        conviction=_number(row, "conviction"),
        conviction_source=_optional_string(row, "conviction_source"),
        metalabel_p=_number(row, "metalabel_p"),
        metalabel_bundle_id=_optional_string(row, "metalabel_bundle_id"),
        client_order_id=_optional_string(row, "client_order_id"),
        cumulative_quantity=_number(row, "cumulative_filled_qty") or 0.0,
        remaining_quantity=_number(row, "remaining_qty"),
    )


def _optional_string(row: dict[str, object], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) and value else None


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
