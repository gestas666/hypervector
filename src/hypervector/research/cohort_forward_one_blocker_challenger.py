"""Frozen report-only forward journal for one executable blocker relaxation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Literal

from hypervector.research.cohort_one_blocker_execution_feasibility import (
    OneBlockerExecutionContract,
    OpiCohort,
)

Record = Mapping[str, object]
_LATEST_EXECUTION_LIMIT = 100
_FALSIFIERS = (
    "fresh net profit factor at or below one",
    "one observation dominates absolute outcomes",
    "short-side evidence contradicts the direction contract",
)
_LIMITATIONS = (
    "recorded BBO is an executable estimate rather than proof of IOC fill",
    "stop exits use adverse BBO rather than an exact venue trigger fill",
    "binary payoff geometry excludes funding and the fixed-horizon fallback",
    "the report has no order, sizing, promotion, or portfolio authority",
)


@dataclass(frozen=True)
class ForwardOneBlockerChallengerSpec:
    """Immutable causal and execution assumptions for one forward challenger."""

    strategy_id: str
    symbol: str
    blocker: str
    cutoff_time_ms: int
    horizon_minutes: int
    maximum_context_age_ms: int
    maximum_entry_delay_ms: int
    maximum_exit_delay_ms: int
    notional_usd: float
    taker_fee_rate: float
    stop_proxy_bps: float
    opi_cohort: OpiCohort
    target_proxy_bps: float | None = None
    minimum_entry_spacing_minutes: int | None = None
    source_authority: Literal["executable", "observe_only"] = "executable"

    def __post_init__(self) -> None:
        """Reject a mutable or non-forward experiment contract."""
        if (
            isinstance(self.cutoff_time_ms, bool)
            or not isinstance(self.cutoff_time_ms, int)
            or self.cutoff_time_ms <= 0
        ):
            raise ValueError("forward challenger cutoff must be a positive integer")
        if self.source_authority not in {"executable", "observe_only"}:
            raise ValueError("forward challenger source authority is invalid")
        self.execution_contract()

    def execution_contract(self) -> OneBlockerExecutionContract:
        """Return the underlying no-submit executable replay contract."""
        return OneBlockerExecutionContract(
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            blocker=self.blocker,
            horizon_minutes=self.horizon_minutes,
            maximum_context_age_ms=self.maximum_context_age_ms,
            maximum_entry_delay_ms=self.maximum_entry_delay_ms,
            maximum_exit_delay_ms=self.maximum_exit_delay_ms,
            notional_usd=self.notional_usd,
            taker_fee_rate=self.taker_fee_rate,
            stop_proxy_bps=self.stop_proxy_bps,
            opi_cohort=self.opi_cohort,
            target_proxy_bps=self.target_proxy_bps,
            minimum_available_time_ms=self.cutoff_time_ms,
            minimum_entry_spacing_minutes=self.minimum_entry_spacing_minutes,
        )


def build_forward_challenger_report(
    replay: Mapping[str, object],
    *,
    spec: ForwardOneBlockerChallengerSpec,
) -> dict[str, object]:
    """Validate and summarize only post-cutoff executable observations."""
    _validate_replay_contract(replay, spec)
    coverage = _mapping(replay.get("coverage"), "forward replay coverage")
    executions = _records(replay.get("executions"), "forward replay executions")
    _validate_executions(executions, spec.cutoff_time_ms)
    resolved = _nonnegative_int(
        coverage.get("resolved_executions"), "resolved executions"
    )
    if resolved != len(executions):
        raise ValueError("forward replay resolved count is inconsistent")
    summary = _summary(executions)
    return {
        "schema_version": 1,
        "mode": "cohort_forward_one_blocker_challenger",
        "state": _state(coverage, resolved),
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "live_strategy_changed": False,
            "automatic_promotion": False,
            "portfolio_pnl_claimed": False,
            "source_signal_authority": spec.source_authority,
            "direction_scope": ["long", "short"],
            "cutoff_time_ms": spec.cutoff_time_ms,
            "cutoff_utc": _utc(spec.cutoff_time_ms),
            "execution": spec.execution_contract().as_payload(),
        },
        "coverage": dict(coverage),
        "summary": summary,
        "entry_context_summary": _entry_context_summary(executions),
        "context_15m_summary": _context_15m_summary(executions),
        "payoff_geometry": _payoff_geometry(spec),
        "latest_executions": [
            dict(row) for row in executions[-_LATEST_EXECUTION_LIMIT:]
        ],
        "falsifiers": list(_FALSIFIERS),
        "limitations": list(_LIMITATIONS),
    }


def _payoff_geometry(
    spec: ForwardOneBlockerChallengerSpec,
) -> dict[str, object] | None:
    target = spec.target_proxy_bps
    if target is None:
        return None
    fee = spec.taker_fee_rate * 20_000.0
    target_net = target - fee
    stop_net = -spec.stop_proxy_bps - fee
    denominator = target_net + abs(stop_net)
    break_even = abs(stop_net) / denominator * 100.0 if target_net > 0.0 else None
    return {
        "scope": "binary_target_stop_benchmark_before_funding",
        "execution_authority": "none",
        "performance_gate": False,
        "target_proxy_bps": target,
        "stop_proxy_bps": spec.stop_proxy_bps,
        "estimated_round_trip_fee_bps": fee,
        "estimated_target_net_bps": target_net,
        "estimated_stop_net_bps": stop_net,
        "break_even_target_rate_pct": break_even,
        "fixed_horizon_changes_realized_distribution": True,
    }


def _validate_replay_contract(
    replay: Mapping[str, object], spec: ForwardOneBlockerChallengerSpec
) -> None:
    if replay.get("schema_version") != 1 or replay.get("mode") != (
        "one_blocker_execution_feasibility"
    ):
        raise ValueError("forward replay envelope is invalid")
    actual = _mapping(replay.get("contract"), "forward replay contract")
    expected = spec.execution_contract().as_payload()
    keys = (
        "strategy_id",
        "symbol",
        "blocker",
        "horizon_minutes",
        "minimum_entry_spacing_minutes",
        "maximum_context_age_ms",
        "maximum_entry_delay_ms",
        "maximum_exit_delay_ms",
        "notional_usd",
        "taker_fee_rate",
        "stop_proxy_bps",
        "target_proxy_bps",
        "opi_cohort",
        "minimum_available_time_ms",
        "execution_authority",
    )
    if any(actual.get(key) != expected.get(key) for key in keys):
        raise ValueError("replay does not match the frozen forward contract")


def _validate_executions(executions: Sequence[Record], cutoff_time_ms: int) -> None:
    prior_exit_ms = -1
    for row in executions:
        available = _nonnegative_int(row.get("available_time_ms"), "available time")
        entry = _nonnegative_int(row.get("entry_time_ms"), "entry time")
        exit_time = _nonnegative_int(row.get("exit_time_ms"), "exit time")
        side = row.get("side")
        net = _number(row.get("net_return_bps"), "net return")
        crossed = row.get("crossed_stop_proxy")
        if (
            available < cutoff_time_ms
            or not available <= entry <= exit_time
            or entry < prior_exit_ms
            or side not in {"long", "short"}
            or not isinstance(crossed, bool)
            or not isfinite(net)
        ):
            raise ValueError("forward execution evidence is inconsistent")
        prior_exit_ms = exit_time


def _summary(executions: Sequence[Record]) -> dict[str, object]:
    values = [_number(row.get("net_return_bps"), "net return") for row in executions]
    gains = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value < 0.0)
    absolute = sum(abs(value) for value in values)
    total = sum(values)
    return {
        "resolved": len(values),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value < 0.0 for value in values),
        "total_net_return_bps": total,
        "mean_net_return_bps": total / len(values) if values else None,
        "profit_factor": gains / losses if losses else None,
        "largest_abs_contribution_fraction": (
            max((abs(value) for value in values), default=0.0) / absolute
            if absolute
            else None
        ),
        "stop_proxy_crosses": sum(
            row.get("crossed_stop_proxy") is True for row in executions
        ),
        "long_resolved": sum(row.get("side") == "long" for row in executions),
        "short_resolved": sum(row.get("side") == "short" for row in executions),
    }


def _entry_context_summary(executions: Sequence[Record]) -> dict[str, object]:
    return _regime_context_summary(
        executions,
        feature_name="state_5m",
        mode="untuned_five_minute_regime_context",
        coverage_name="state_5m",
        state_summary_name="by_state_5m",
    )


def _context_15m_summary(executions: Sequence[Record]) -> dict[str, object]:
    return _regime_context_summary(
        executions,
        feature_name="context_15m",
        mode="untuned_fifteen_minute_regime_context",
        coverage_name="context_15m",
        state_summary_name="by_state_15m",
    )


def _regime_context_summary(
    executions: Sequence[Record],
    *,
    feature_name: str,
    mode: str,
    coverage_name: str,
    state_summary_name: str,
) -> dict[str, object]:
    stances: dict[str, list[Record]] = {
        "aligned": [],
        "opposed": [],
        "neutral": [],
        "unavailable": [],
    }
    states: dict[str, list[Record]] = {}
    observed = 0
    for row in executions:
        state = _entry_regime_state(row, feature_name)
        if state is None:
            stances["unavailable"].append(row)
            continue
        observed += 1
        states.setdefault(state, []).append(row)
        stances[_directional_stance(row, state)].append(row)
    return {
        "mode": mode,
        "execution_authority": "none",
        "performance_gate": False,
        "coverage": {
            "resolved": len(executions),
            f"{coverage_name}_observed": observed,
            f"{coverage_name}_missing": len(executions) - observed,
        },
        "by_directional_stance": {
            name: _summary(rows) for name, rows in stances.items()
        },
        state_summary_name: {
            name: _summary(rows) for name, rows in sorted(states.items())
        },
    }


def _entry_regime_state(row: Record, feature_name: str) -> str | None:
    value = row.get("entry_features")
    if value is None:
        return None
    features = _mapping(value, "entry features")
    state = features.get(feature_name)
    if state is None:
        return None
    allowed = {"BREAKOUT", "RANGE", "TRANSITION", "TREND_DOWN", "TREND_UP"}
    if not isinstance(state, str) or state not in allowed:
        raise ValueError(f"entry {feature_name} is invalid")
    return state


def _directional_stance(row: Record, state: str) -> str:
    side = row.get("side")
    if (side, state) in {("long", "TREND_UP"), ("short", "TREND_DOWN")}:
        return "aligned"
    if (side, state) in {("long", "TREND_DOWN"), ("short", "TREND_UP")}:
        return "opposed"
    return "neutral"


def _state(coverage: Record, resolved: int) -> str:
    exact = _nonnegative_int(coverage.get("exact_candidates"), "exact candidates")
    if exact == 0:
        return "awaiting_fresh_post_cutoff_candidate"
    if resolved == 0:
        return "awaiting_executable_resolution"
    return "descriptive_resolved_forward_evidence"


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} rows must be mappings")
    return tuple(row for row in value if isinstance(row, Mapping))


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1_000.0, tz=timezone.utc).isoformat()
