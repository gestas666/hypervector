"""Normalized duration comparison for the first resolved V58 ETH lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

Record = Mapping[str, object]

_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
_OBSERVER_RUN = "bidirectional-observe-1787127644202"
_OBSERVER_DECISION_MS = 1787172900000
_OBSERVER_HOLD_MINUTES = 720
_OBSERVER_MAXIMUM_RESOLUTION_DELAY_MS = 60_000
_MILLISECONDS_PER_MINUTE = 60_000


def build_v58_eth_exit_comparison(
    close_report: Record, duration_report: Record
) -> dict[str, object]:
    """Compare one reconciled live close with frozen observer duration controls."""
    identity = _close_identity(close_report)
    actual = _actual_close(close_report)
    duration = _duration_inputs(duration_report)
    observer = _observer_control(close_report, duration_report)
    comparison = _duration_comparison(actual, duration, observer)
    return {
        "schema_version": 1,
        "mode": "v58_eth_first_live_exit_comparison_v1",
        "status": "diagnostic_only_one_resolved_long",
        "frozen_identity": identity,
        "duration_comparison": comparison,
        "profit_protection_alternatives": {
            "policies": dict(
                _mapping(close_report.get("frozen_counterfactuals"), "policies")
            ),
            "direct_ranking_withheld": True,
            "reason": "counterfactual funding and slippage scope differs",
        },
        "interpretation": "one long lifecycle cannot establish an exit replacement",
        "strategy_change_supported": False,
        "contract": _report_only_contract(),
    }


def _close_identity(report: Record) -> dict[str, object]:
    if report.get("mode") != "v58_eth_first_live_close_reconciliation_v1":
        raise ValueError("V58 ETH exit comparison close mode differs")
    if report.get("status") != "reconciled":
        raise ValueError("V58 ETH exit comparison close is unresolved")
    if report.get("contract") != _report_only_contract():
        raise ValueError("V58 ETH exit comparison close contract differs")
    if report.get("strategy_change_supported") is not False:
        raise ValueError("V58 ETH exit comparison close proposes a live change")
    identity = dict(_mapping(report.get("frozen_identity"), "close identity"))
    expected = {
        "profile_id": _PROFILE,
        "strategy_id": _STRATEGY,
        "route": f"{_STRATEGY}|ETH",
        "symbol": "ETH",
        "side": "long",
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH exit comparison identity differs")
    return identity


def _actual_close(report: Record) -> dict[str, object]:
    actual = _mapping(report.get("actual_live_close"), "actual close")
    return {
        "exit_reason": _text(actual.get("exit_reason"), "actual exit reason"),
        "holding_time_ms": _positive(actual.get("holding_time_ms"), "holding time"),
        "entry_notional_usd": _positive(
            actual.get("entry_notional_usd"), "actual notional"
        ),
        "net_pnl_usd": _number(actual.get("net_pnl_usd"), "actual net PnL"),
        "net_return_bps": _number(
            actual.get("net_return_on_entry_notional_bps"), "actual net return"
        ),
        "actual_orders_and_fills_claimed": True,
    }


def _duration_inputs(report: Record) -> dict[str, dict[str, object]]:
    if report.get("mode") != "v58_eth_fixed_entry_duration_checkpoint_v1":
        raise ValueError("V58 ETH exit comparison duration mode differs")
    if report.get("execution_authority") != "none":
        raise ValueError("V58 ETH exit comparison duration has authority")
    if report.get("strategy_change_supported") is not False:
        raise ValueError("V58 ETH exit comparison duration proposes a live change")
    _duration_identity(_mapping(report.get("source_lifecycle"), "duration identity"))
    rows = _mapping(report.get("duration_checkpoints"), "duration checkpoints")
    return {
        "fixed_240m": _duration_row(rows.get("fixed_240m"), 240),
        "fixed_480m": _duration_row(rows.get("fixed_480m"), 480),
    }


def _duration_identity(identity: Record) -> None:
    expected = {
        "source_run_id": _OBSERVER_RUN,
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "side": "long",
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH exit comparison duration identity differs")


def _duration_row(value: object, minutes: int) -> dict[str, object]:
    row = _mapping(value, f"fixed {minutes}m duration")
    _duration_identity(row)
    expected = {
        "status": "resolved",
        "maximum_hold_minutes": minutes,
        "entry_notional_usd": 750.0,
        "net_return_scope": "exact_depth_fee_and_funding",
    }
    if any(row.get(key) != expected_value for key, expected_value in expected.items()):
        raise ValueError(f"V58 ETH fixed {minutes}m duration contract differs")
    return {
        "maximum_hold_minutes": minutes,
        "entry_notional_usd": 750.0,
        "net_return_bps": _number(row.get("net_return_bps"), "duration return"),
        "simulated_net_pnl_usd": _number(
            row.get("simulated_net_pnl_usd"), "duration PnL"
        ),
        "net_return_scope": "exact_depth_fee_and_funding",
        "actual_orders_or_fills_claimed": False,
    }


def _observer_control(report: Record, duration_report: Record) -> dict[str, object]:
    row = _mapping(report.get("observer_comparison"), "observer control")
    expected = {
        "source_run_id": _OBSERVER_RUN,
        "strategy_id": _STRATEGY,
        "symbol": "ETH",
        "side": "long",
        "decision_time_ms": _OBSERVER_DECISION_MS,
        "notional_usd": 750.0,
        "exit_reason": "maximum_hold",
        "net_return_scope": "exact_depth_fee_and_funding",
        "actual_orders_or_fills_claimed": False,
    }
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH observer 720m control differs")
    entry_ms = _positive_int(row.get("entry_time_ms"), "observer entry time")
    exit_ms = _positive_int(row.get("exit_time_ms"), "observer exit time")
    deadline_ms = _observer_deadline(duration_report, entry_ms)
    delay_ms = exit_ms - deadline_ms
    if not 0 <= delay_ms <= _OBSERVER_MAXIMUM_RESOLUTION_DELAY_MS:
        raise ValueError("V58 ETH observer 720m control differs")
    return {
        "maximum_hold_minutes": _OBSERVER_HOLD_MINUTES,
        "entry_time_ms": entry_ms,
        "deadline_time_ms": deadline_ms,
        "exit_time_ms": exit_ms,
        "resolution_delay_ms": delay_ms,
        "entry_notional_usd": 750.0,
        "net_return_bps": _number(row.get("net_return_bps"), "observer return"),
        "simulated_net_pnl_usd": _number(
            row.get("simulated_net_pnl_usd"), "observer PnL"
        ),
        "net_return_scope": "exact_depth_fee_and_funding",
        "actual_orders_or_fills_claimed": False,
    }


def _observer_deadline(report: Record, entry_ms: int) -> int:
    retained = _mapping(report.get("retained_control"), "retained control")
    expected = {
        "maximum_hold_minutes": _OBSERVER_HOLD_MINUTES,
        "state": "awaiting_resolution",
    }
    if any(retained.get(key) != value for key, value in expected.items()):
        raise ValueError("V58 ETH observer 720m control differs")
    deadline = _positive_int(retained.get("deadline_time_ms"), "observer deadline")
    hold_ms = _OBSERVER_HOLD_MINUTES * _MILLISECONDS_PER_MINUTE
    if deadline != entry_ms + hold_ms:
        raise ValueError("V58 ETH observer 720m control differs")
    return deadline


def _duration_comparison(
    actual: dict[str, object],
    durations: dict[str, dict[str, object]],
    observer: dict[str, object],
) -> dict[str, object]:
    actual_bps = _number(actual["net_return_bps"], "actual net return")
    at_240 = _number(durations["fixed_240m"]["net_return_bps"], "240m return")
    at_480 = _number(durations["fixed_480m"]["net_return_bps"], "480m return")
    at_720 = _number(observer["net_return_bps"], "720m return")
    return {
        "actual_live_native": actual,
        "observer_240m": durations["fixed_240m"],
        "observer_480m": durations["fixed_480m"],
        "observer_720m": observer,
        "actual_minus_observer_240m_bps": actual_bps - at_240,
        "actual_minus_observer_480m_bps": actual_bps - at_480,
        "actual_minus_observer_720m_bps": actual_bps - at_720,
        "cross_notional_dollar_deltas_withheld": True,
    }


def _report_only_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
        "approval_requested": False,
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 ETH exit comparison {label} must be a mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"V58 ETH exit comparison {label} must be text")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 ETH exit comparison {label} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"V58 ETH exit comparison {label} must be finite")
    return result


def _positive(value: object, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ValueError(f"V58 ETH exit comparison {label} must be positive")
    return result


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 ETH exit comparison {label} must be a positive integer")
    return value
