"""Validated current-run closed lifecycle context for V58 research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isclose, isfinite

Record = Mapping[str, object]
_POLICY_IDS = (
    "a25_floor15_trail10",
    "a40_floor15_trail20",
    "a60_floor15_trail30",
)


def extract_v58_live_closed_lifecycles(
    audit: Record,
    *,
    run_id: str,
    profile_fingerprint: str,
    routes: Sequence[str],
) -> dict[str, object]:
    """Return exact current-run closes from the checkpoint trade reflections."""
    _require_coverage(audit)
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    _require_contract(reflections)
    trades = _records(reflections.get("trades"), "trade reflection rows")
    if reflections.get("closed_trades") != len(trades):
        raise ValueError("V58 reflected close count is inconsistent")
    route_set = {_text(route, "configured route") for route in routes}
    if len(route_set) != len(tuple(routes)):
        raise ValueError("V58 configured routes must be unique")
    current_rows = [row for row in trades if row.get("source_run_id") == run_id]
    profit_locks = _profit_lock_index(audit) if current_rows else {}
    selected = [
        _trade_payload(row, run_id, profile_fingerprint, route_set, profit_locks)
        for row in current_rows
    ]
    identities = [row["lifecycle_id"] for row in selected]
    if len(identities) != len(set(identities)):
        raise ValueError("V58 current-run closed lifecycles are duplicated")
    return {
        "measurement_scope": "actual_current_run_closed_lifecycles",
        "closed_lifecycles": len(selected),
        "trades": selected,
        "actual_entry_fills_claimed": bool(selected),
        "actual_exit_fills_claimed": bool(selected),
        "execution_authority": "none",
    }


def _trade_payload(
    row: Record,
    run_id: str,
    fingerprint: str,
    routes: set[str],
    profit_locks: Mapping[str, Record],
) -> dict[str, object]:
    lifecycle, strategy, symbol, side = _close_identity(
        row, run_id, fingerprint, routes
    )
    entry = _mapping(row.get("entry"), "close entry")
    exit_fill = _mapping(row.get("exit"), "close exit")
    entry_time, exit_time = _close_times_and_size(entry, exit_fill)
    net_pnl = _number(row.get("net_pnl_usd"), "net PnL")
    capture = _completed_hold_capture(row)
    lock = _profit_lock_result(
        profit_locks.get(lifecycle),
        lifecycle=lifecycle,
        run_id=run_id,
        fingerprint=fingerprint,
        strategy=strategy,
        symbol=symbol,
        side=side,
        actual_net=net_pnl,
    )
    return {
        "lifecycle_id": lifecycle,
        "strategy_id": strategy,
        "symbol": symbol,
        "side": side,
        "actual_entry_fill_claim": True,
        "actual_exit_fill_claim": True,
        "entry_price": _positive_number(entry.get("price"), "entry price"),
        "entry_time_ms": entry_time,
        "exit_price": _positive_number(exit_fill.get("price"), "exit price"),
        "exit_time_ms": exit_time,
        "exit_reason": _text(row.get("exit_reason"), "exit reason"),
        "net_pnl_usd": net_pnl,
        "fees_usd": _nonnegative_number(row.get("fees_usd"), "fees"),
        "funding_usd": _number(row.get("funding_usd"), "funding"),
        "completed_hold_capture": capture,
        "profit_lock_challenger": lock,
        "technical_complete": True,
    }


def _close_identity(
    row: Record, run_id: str, fingerprint: str, routes: set[str]
) -> tuple[str, str, str, str]:
    if row.get("source_run_id") != run_id:
        raise ValueError("V58 current-run close identity differs")
    if row.get("source_profile_fingerprint") != fingerprint:
        raise ValueError("V58 current-run close profile fingerprint differs")
    symbol = _text(row.get("symbol"), "close symbol")
    strategy = _text(row.get("strategy_id"), "close strategy")
    if f"{strategy}|{symbol}" not in routes:
        raise ValueError("V58 current-run close route is not executable")
    entry_oid = _positive_integer(row.get("entry_oid"), "entry oid")
    lifecycle = _text(row.get("lifecycle_id"), "lifecycle id")
    if lifecycle != f"{symbol}:{entry_oid}":
        raise ValueError("V58 current-run close lifecycle identity differs")
    return lifecycle, strategy, symbol, _side(row.get("side"))


def _close_times_and_size(entry: Record, exit_fill: Record) -> tuple[int, int]:
    entry_time = _positive_integer(entry.get("venue_timestamp_ms"), "entry time")
    exit_time = _positive_integer(exit_fill.get("venue_timestamp_ms"), "exit time")
    if exit_time < entry_time:
        raise ValueError("V58 current-run close timestamps are inconsistent")
    entry_size = _positive_number(entry.get("size"), "entry size")
    exit_size = _positive_number(exit_fill.get("size"), "exit size")
    if not isclose(entry_size, exit_size, abs_tol=1e-10):
        raise ValueError("V58 current-run close size is inconsistent")
    return entry_time, exit_time


def _completed_hold_capture(row: Record) -> dict[str, object]:
    capture = _mapping(row.get("completed_hold_capture"), "completed hold capture")
    if capture.get("status") != "resolved":
        raise ValueError("V58 completed hold capture is unresolved")
    _positive_integer(capture.get("completed_bars"), "completed hold bars")
    for key in (
        "maximum_favorable_excursion_bps",
        "maximum_adverse_excursion_bps",
        "peak_giveback_bps",
    ):
        _nonnegative_number(capture.get(key), f"completed hold {key}")
    _number(capture.get("realized_net_return_bps"), "completed hold realized net")
    return dict(capture)


def _profit_lock_index(audit: Record) -> dict[str, Record]:
    report = _mapping(audit.get("profit_lock_challenger"), "profit lock challenger")
    expected = {
        "schema_version": 1,
        "mode": "cohort_profit_lock_challenger_v1",
        "scope": "compatible_profile_history",
    }
    if any(report.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 profit-lock report contract differs")
    _require_profit_lock_authority(report)
    results = _records(report.get("latest_results"), "profit-lock results")
    indexed: dict[str, Record] = {}
    for result in results:
        lifecycle = _text(result.get("lifecycle_id"), "profit-lock lifecycle")
        if lifecycle in indexed:
            raise ValueError("V58 profit-lock lifecycle is duplicated")
        indexed[lifecycle] = result
    return indexed


def _require_profit_lock_authority(report: Record) -> None:
    contract = _mapping(report.get("contract"), "profit lock contract")
    safe = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "balance_gate": False,
        "portfolio_pnl_claimed": False,
    }
    if any(contract.get(key) != value for key, value in safe.items()):
        raise ValueError("V58 profit-lock report has execution authority")


def _profit_lock_result(
    value: object,
    *,
    lifecycle: str,
    run_id: str,
    fingerprint: str,
    strategy: str,
    symbol: str,
    side: str,
    actual_net: float,
) -> dict[str, object]:
    result = _mapping(value, "closed profit-lock result")
    identity = {
        "lifecycle_id": lifecycle,
        "source_run_id": run_id,
        "source_profile_fingerprint": fingerprint,
        "strategy_id": strategy,
        "symbol": symbol,
        "side": side,
    }
    if any(result.get(key) != expected for key, expected in identity.items()):
        raise ValueError("V58 closed profit-lock identity differs")
    _profit_lock_coverage(result)
    if not isclose(
        _number(result.get("actual_net_pnl_usd"), "lock actual net"),
        actual_net,
        abs_tol=1e-8,
    ):
        raise ValueError("V58 closed profit-lock actual net differs")
    _profit_lock_policies(result, actual_net)
    return {
        **dict(result),
        "measurement_scope": "actual_closed_lifecycle_counterfactual",
        "actual_exit_fill_claim": True,
        "execution_authority": "none",
    }


def _profit_lock_coverage(result: Record) -> None:
    expected = _nonnegative_integer(
        result.get("completed_bars_expected"), "lock expected bars"
    )
    observed = _nonnegative_integer(
        result.get("completed_bars_observed"), "lock observed bars"
    )
    status = _text(result.get("status"), "lock status")
    valid = (status == "eligible" and observed == expected) or (
        status == "insufficient_candle_coverage" and observed < expected
    )
    if not valid:
        raise ValueError("V58 closed profit-lock coverage differs")


def _profit_lock_policies(result: Record, actual_net: float) -> None:
    policies = _mapping(result.get("policies"), "closed profit-lock policies")
    if set(policies) != set(_POLICY_IDS):
        raise ValueError("V58 closed profit-lock policy set differs")
    for policy_id in _POLICY_IDS:
        policy = _mapping(policies[policy_id], f"profit-lock {policy_id}")
        _text(policy.get("status"), f"profit-lock {policy_id} status")
        policy_actual = _number(
            policy.get("actual_net_pnl_usd"), f"profit-lock {policy_id} actual"
        )
        if not isclose(policy_actual, actual_net, abs_tol=1e-8):
            raise ValueError("V58 profit-lock policy actual net differs")
        _profit_lock_estimate(policy, actual_net, policy_id)


def _profit_lock_estimate(policy: Record, actual_net: float, policy_id: str) -> None:
    estimated = policy.get("estimated_net_pnl_usd")
    delta = policy.get("estimated_minus_actual_net_usd")
    if estimated is None or delta is None:
        if estimated is not None or delta is not None:
            raise ValueError("V58 profit-lock estimate is partially unavailable")
        return
    estimate = _number(estimated, f"profit-lock {policy_id} estimate")
    difference = _number(delta, f"profit-lock {policy_id} delta")
    if not isclose(estimate - actual_net, difference, abs_tol=1e-8):
        raise ValueError("V58 profit-lock estimate does not reconcile")


def _require_coverage(audit: Record) -> None:
    coverage = _mapping(audit.get("coverage"), "checkpoint coverage")
    if coverage.get("complete") is not True or coverage.get("technical_gaps") != []:
        raise ValueError("V58 current-run close checkpoint coverage is incomplete")


def _require_contract(reflections: Record) -> None:
    expected = {
        "schema_version": 1,
        "mode": "cohort_trade_reflections",
        "scope": "compatible_profile_history",
    }
    if any(reflections.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 trade reflection contract differs")
    contract = _mapping(reflections.get("contract"), "trade reflection contract")
    safe = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_strategy_changes": False,
        "runtime_strategy_changed": False,
    }
    if any(contract.get(key) != value for key, value in safe.items()):
        raise ValueError("V58 trade reflection authority differs")


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"V58 {label} must be an array")
    if any(not isinstance(row, Mapping) for row in value):
        raise ValueError(f"V58 {label} must contain mappings")
    return tuple(value)  # type: ignore[return-value]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be an object")
    return value


def _side(value: object) -> str:
    side = _text(value, "close side")
    if side not in {"long", "short"}:
        raise ValueError("V58 close side is invalid")
    return side


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"V58 {label} must be non-empty text")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"V58 {label} must be finite")
    return number


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"V58 {label} must be positive")
    return number


def _nonnegative_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number < 0.0:
        raise ValueError(f"V58 {label} must be nonnegative")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 {label} must be a positive integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"V58 {label} must be a nonnegative integer")
    return value
