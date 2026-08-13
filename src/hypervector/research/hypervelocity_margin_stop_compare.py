"""Creator-calibrated fixed-margin stop comparison utilities."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import math

import pandas as pd

from hypervector.research.maker_replay_models import (
    MakerReplayConfig,
    MakerReplayLifecycle,
    MakerReplayReport,
    MakerReplayTrade,
    SameDirectionReentryPolicy,
)
from hypervector.research.hypervelocity_reentry_compare import (
    bounded_target_ladder_candidate_matrix,
    logical_source_positions,
    mature_target_continuation_candidate_matrix,
)

_STOP_CANDIDATES: tuple[tuple[str, float | None], ...] = (
    ("no_stop_control", None),
    ("stop_6pct_margin", 6.0),
    ("stop_10pct_margin", 10.0),
    ("stop_14pct_margin", 14.0),
    ("stop_18pct_margin", 18.0),
)
_TIGHT_STOP_CANDIDATES: tuple[tuple[str, float | None], ...] = (
    ("no_stop_control", None),
    ("stop_2pct_margin", 2.0),
    ("stop_3pct_margin", 3.0),
    ("stop_4pct_margin", 4.0),
)
_WIDE_STOP_CANDIDATES: tuple[tuple[str, float | None], ...] = (
    ("no_stop_control", None),
    ("stop_25pct_margin", 25.0),
    ("stop_35pct_margin", 35.0),
    ("stop_45pct_margin", 45.0),
)
_MAX_HOLD_CANDIDATES: tuple[tuple[str, float | None], ...] = (
    ("no_timeout_control", None),
    ("max_hold_6h", 21_600.0),
    ("max_hold_12h", 43_200.0),
    ("max_hold_24h", 86_400.0),
)
_RESOLVED_STATUSES = frozenset(
    {
        "target_completed",
        "stopped",
        "time_exited",
        "regime_exited",
        "reversed",
        "liquidated",
    }
)


def _faithful_risk_config(
    initial_equity: float,
    *,
    margin_stop_pct: float | None = None,
    maximum_hold_seconds: float | None = None,
    reentry_policy: SameDirectionReentryPolicy = "regime_reset",
    reentry_clearance_bps: float = 0.0,
    target_limit_per_episode: int | None = None,
    target_minimum_episode_seconds: float = 0.0,
) -> MakerReplayConfig:
    return MakerReplayConfig(
        initial_equity=initial_equity,
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        fill_rule="trade-through",
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy=reentry_policy,
        same_direction_reentry_clearance_bps=reentry_clearance_bps,
        target_continuation_limit_per_episode=target_limit_per_episode,
        target_continuation_minimum_episode_seconds=(target_minimum_episode_seconds),
        fixed_margin_stop_pct=margin_stop_pct,
        maximum_hold_seconds=maximum_hold_seconds,
    )


def margin_stop_candidate_configs(
    initial_equity: float = 10_000.0,
) -> dict[str, MakerReplayConfig]:
    """Return the immutable, predeclared creator-calibrated stop grid."""
    return {
        name: _faithful_risk_config(initial_equity, margin_stop_pct=stop_pct)
        for name, stop_pct in _STOP_CANDIDATES
    }


def tight_margin_stop_candidate_configs(
    initial_equity: float = 10_000.0,
) -> dict[str, MakerReplayConfig]:
    """Return the frozen reverse-engineered 2-4% margin-stop grid."""
    return {
        name: _faithful_risk_config(initial_equity, margin_stop_pct=stop_pct)
        for name, stop_pct in _TIGHT_STOP_CANDIDATES
    }


def wide_margin_stop_candidate_configs(
    initial_equity: float = 10_000.0,
) -> dict[str, MakerReplayConfig]:
    """Return the predeclared 25-45% emergency margin-stop grid."""
    return {
        name: _faithful_risk_config(initial_equity, margin_stop_pct=stop_pct)
        for name, stop_pct in _WIDE_STOP_CANDIDATES
    }


def maximum_hold_candidate_configs(
    initial_equity: float = 10_000.0,
) -> dict[str, MakerReplayConfig]:
    """Return the immutable, source-bounded maximum-hold grid."""
    return {
        name: _faithful_risk_config(
            initial_equity,
            maximum_hold_seconds=maximum_hold_seconds,
        )
        for name, maximum_hold_seconds in _MAX_HOLD_CANDIDATES
    }


def bounded_target_ladder_candidate_configs(
    initial_equity: float = 10_000.0,
) -> dict[str, MakerReplayConfig]:
    """Return the immutable source-bounded target ladder replay grid."""
    configs: dict[str, MakerReplayConfig] = {}
    for candidate in bounded_target_ladder_candidate_matrix():
        if candidate.policy not in {
            "regime_reset",
            "cooldown_only",
            "target_continuation",
        }:
            raise ValueError(f"unsupported event re-entry policy: {candidate.policy}")
        configs[candidate.candidate_id] = _faithful_risk_config(
            initial_equity,
            reentry_policy=candidate.policy,
            reentry_clearance_bps=candidate.clearance_bps,
            target_limit_per_episode=candidate.target_limit_per_episode,
        )
    return configs


def mature_target_continuation_candidate_configs(
    initial_equity: float = 10_000.0,
) -> dict[str, MakerReplayConfig]:
    """Return the frozen mature-episode continuation replay grid."""
    configs: dict[str, MakerReplayConfig] = {}
    for candidate in mature_target_continuation_candidate_matrix():
        if candidate.policy not in {
            "regime_reset",
            "cooldown_only",
            "target_continuation",
        }:
            raise ValueError(f"unsupported event re-entry policy: {candidate.policy}")
        configs[candidate.candidate_id] = _faithful_risk_config(
            initial_equity,
            reentry_policy=candidate.policy,
            reentry_clearance_bps=candidate.clearance_bps,
            target_limit_per_episode=candidate.target_limit_per_episode,
            target_minimum_episode_seconds=candidate.minimum_episode_seconds,
        )
    return configs


def source_hold_compatibility(
    positions: pd.DataFrame,
    configs: Mapping[str, MakerReplayConfig],
) -> dict[str, object]:
    """Measure how many closed creator holds each deadline would preserve."""
    logical = logical_source_positions(positions)
    durations = (logical["close_ts"] - logical["open_ts"]).dt.total_seconds()
    closed = durations.dropna()
    if closed.lt(0.0).any():
        raise ValueError("source position closes before its open time")
    candidates: dict[str, object] = {}
    for name, config in configs.items():
        maximum = config.maximum_hold_seconds
        compatible = len(closed) if maximum is None else int(closed.le(maximum).sum())
        candidates[name] = {
            "maximum_hold_seconds": maximum,
            "compatible_closed": compatible,
            "compatible_closed_pct": 100.0 * compatible / len(closed)
            if len(closed)
            else 0.0,
        }
    return {
        "logical_positions": len(logical),
        "closed_positions": len(closed),
        "open_or_missing_close": int(durations.isna().sum()),
        "candidates": candidates,
    }


def break_even_gross_margin_stop_pct(
    *,
    win_rate: float,
    target_margin_pct: float,
    leverage: float,
    maker_fee_rate: float,
    taker_fee_rate: float,
) -> float:
    """Return the gross losing margin move that has zero expected net PnL."""
    values = (win_rate, target_margin_pct, leverage, maker_fee_rate, taker_fee_rate)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("break-even inputs must be finite")
    if not 0.0 < win_rate < 1.0:
        raise ValueError("win_rate must be within (0, 1)")
    if target_margin_pct <= 0.0 or leverage <= 0.0:
        raise ValueError("target_margin_pct and leverage must be positive")
    if maker_fee_rate < 0.0 or taker_fee_rate < 0.0:
        raise ValueError("fee rates must be non-negative")
    net_target = target_margin_pct - 2.0 * maker_fee_rate * leverage * 100.0
    loss_fees = (maker_fee_rate + taker_fee_rate) * leverage * 100.0
    if net_target <= 0.0:
        raise ValueError("target does not cover round-trip maker fees")
    return win_rate * net_target / (1.0 - win_rate) - loss_fees


def _timestamp(value: str) -> pd.Timestamp:
    return pd.Timestamp(value).tz_convert("UTC")


def _status_counts(
    lifecycles: Sequence[MakerReplayLifecycle],
) -> dict[str, int]:
    counts = Counter(lifecycle.status for lifecycle in lifecycles)
    return {status: int(count) for status, count in counts.items()}


def _average_pnl_by_status(
    trades: Sequence[MakerReplayTrade],
) -> dict[str, float]:
    values: defaultdict[str, list[float]] = defaultdict(list)
    for trade in trades:
        values[trade.status].append(trade.net_pnl)
    return {status: float(sum(pnls) / len(pnls)) for status, pnls in values.items()}


def _resolved_lifecycle_map(
    lifecycles: Sequence[MakerReplayLifecycle],
) -> dict[tuple[str, str], MakerReplayLifecycle]:
    result: dict[tuple[str, str], MakerReplayLifecycle] = {}
    for lifecycle in lifecycles:
        if lifecycle.status not in _RESOLVED_STATUSES:
            continue
        signal = _timestamp(lifecycle.signal_time_utc).isoformat()
        key = (signal, lifecycle.direction)
        if key in result:
            raise ValueError(f"duplicate resolved lifecycle key: {key}")
        result[key] = lifecycle
    return result


def _lifecycle_substitution(
    control: MakerReplayReport,
    candidate: MakerReplayReport,
) -> dict[str, object]:
    control_rows = _resolved_lifecycle_map(control.lifecycles)
    candidate_rows = _resolved_lifecycle_map(candidate.lifecycles)
    shared = control_rows.keys() & candidate_rows.keys()
    transitions = Counter(
        f"{control_rows[key].status}->{candidate_rows[key].status}" for key in shared
    )
    return {
        "shared_resolved_lifecycles": len(shared),
        "control_only_resolved_lifecycles": len(control_rows.keys() - shared),
        "candidate_only_resolved_lifecycles": len(candidate_rows.keys() - shared),
        "status_transitions": dict(sorted(transitions.items())),
    }


def _closed_trade_path(trades: Sequence[MakerReplayTrade]) -> tuple[float, float]:
    growth = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for trade in sorted(trades, key=lambda item: _timestamp(item.exit_time_utc)):
        if trade.margin <= 0.0:
            raise ValueError("trade margin must be positive")
        growth *= 1.0 + 0.70 * trade.net_pnl / trade.margin
        peak = max(peak, growth)
        maximum_drawdown = min(maximum_drawdown, 100.0 * (growth / peak - 1.0))
    return growth, maximum_drawdown


def _segment_summary(
    lifecycles: Sequence[MakerReplayLifecycle],
    trades: Sequence[MakerReplayTrade],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, object]:
    selected_lifecycles = [
        item for item in lifecycles if start <= _timestamp(item.signal_time_utc) < end
    ]
    selected_trades = [
        item for item in trades if start <= _timestamp(item.signal_time_utc) < end
    ]
    counts = _status_counts(selected_lifecycles)
    targets = sum(item.status == "target_completed" for item in selected_trades)
    growth, drawdown = _closed_trade_path(selected_trades)
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "submitted_entries": len(selected_lifecycles),
        "expired_entries": counts.get("expired", 0),
        "status_counts": counts,
        "resolved_trades": len(selected_trades),
        "resolved_target_rate_pct": (
            100.0 * targets / len(selected_trades) if selected_trades else 0.0
        ),
        "average_net_pnl_by_status": _average_pnl_by_status(selected_trades),
        "closed_trade_growth_multiple": growth,
        "closed_trade_maximum_drawdown_pct": drawdown,
    }


def _segments(
    report: MakerReplayReport,
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment_days: int,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    cursor = start
    interval = pd.Timedelta(days=segment_days)
    while cursor < end:
        boundary = min(cursor + interval, end)
        result.append(
            _segment_summary(report.lifecycles, report.trades, cursor, boundary)
        )
        cursor = boundary
    return result


def _candidate_summary(
    report: MakerReplayReport,
    config: MakerReplayConfig,
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment_days: int,
) -> dict[str, object]:
    targets = sum(trade.status == "target_completed" for trade in report.trades)
    return {
        "fixed_margin_stop_pct": config.fixed_margin_stop_pct,
        "maximum_hold_seconds": config.maximum_hold_seconds,
        "same_direction_reentry_policy": config.same_direction_reentry_policy,
        "same_direction_reentry_clearance_bps": (
            config.same_direction_reentry_clearance_bps
        ),
        "target_continuation_limit_per_episode": (
            config.target_continuation_limit_per_episode
        ),
        "target_continuation_minimum_episode_seconds": (
            config.target_continuation_minimum_episode_seconds
        ),
        "status_counts": _status_counts(report.lifecycles),
        "resolved_target_rate_pct": (
            100.0 * targets / len(report.trades) if report.trades else 0.0
        ),
        "average_net_pnl_by_status": _average_pnl_by_status(report.trades),
        "segments": _segments(report, start, end, segment_days),
        "replay": report.to_dict(),
    }


def summarize_margin_stop_grid(
    reports: Mapping[str, MakerReplayReport],
    configs: Mapping[str, MakerReplayConfig],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment_days: int = 30,
) -> dict[str, object]:
    """Summarize replay candidates without discarding lifecycle outcomes."""
    if set(reports) != set(configs):
        raise ValueError("report and config candidate names must match")
    start_utc, end_utc = pd.Timestamp(start), pd.Timestamp(end)
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("summary bounds must be timezone-aware")
    start_utc, end_utc = start_utc.tz_convert("UTC"), end_utc.tz_convert("UTC")
    if start_utc >= end_utc:
        raise ValueError("summary start must precede end")
    if isinstance(segment_days, bool) or segment_days <= 0:
        raise ValueError("segment_days must be a positive integer")
    candidates = {
        name: _candidate_summary(
            reports[name], configs[name], start_utc, end_utc, segment_days
        )
        for name in configs
    }
    control_name = next(iter(configs))
    for name, candidate in candidates.items():
        candidate["versus_control"] = _lifecycle_substitution(
            reports[control_name], reports[name]
        )
    return {
        "window": {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "segment_days": segment_days,
        },
        "control_candidate": control_name,
        "candidates": candidates,
    }
