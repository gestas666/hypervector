"""Read-only development path diagnostics for frozen MU research tracks."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.research.mu_hip3_archive_reporting import (
    _evidence_at_or_before,
    _stale_exit_quote,
    _stale_l2_row,
    partition_trade_path_quality,
    track_identity,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveTrack
from hypervector.research.mu_hip3_candidate import (
    MuChronologicalWindows,
    MuPartitionResult,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)

_THRESHOLDS_MS = (5_000, 6_000, 7_500, 10_000, 15_000)
_RISK_SOURCE = "0xarchive_mark_price_with_public_trade_context_v1"
_SELECTED_PROVIDER_ID = "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1"
_SELECTED_PROFILE_ID = "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1"
_SELECTED_CONFIG = Hip3BreakoutPressureConfig(32, 9, 21, 0.1, 80.0)


def development_path_threshold_diagnostic(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
    *,
    track: MuArchiveTrack,
    windows: MuChronologicalWindows,
) -> dict[str, object]:
    """Measure unresolved selected lifecycles without opening OOS partitions."""
    _require_selected_track(track)
    return hip3_development_path_threshold_diagnostic(
        bars,
        partition,
        track=track,
        windows=windows,
    )


def hip3_development_path_threshold_diagnostic(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
    *,
    track: MuArchiveTrack,
    windows: MuChronologicalWindows,
) -> dict[str, object]:
    """Measure a frozen HIP-3 development track's path-threshold sensitivity."""
    if partition.name != "development":
        raise ValueError("HIP-3 path threshold diagnostic is development-only")
    if (
        partition.start_utc != windows.development_start_utc
        or partition.end_utc != windows.development_end_utc
    ):
        raise ValueError(
            "HIP-3 path diagnostic partition is not the canonical development window"
        )
    scoped = _development_bars(bars, partition)
    _require_columns(scoped)
    _require_partition_lifecycles(partition)
    original = partition_trade_path_quality(
        scoped,
        partition,
        timeframe=track.timeframe,
        family=track.family,
    )
    cumulative = {
        str(threshold): _threshold_result(
            scoped,
            partition,
            timeframe=track.timeframe,
            family=track.family,
            threshold_ms=threshold,
        )
        for threshold in _THRESHOLDS_MS
    }
    _require_original_parity(cumulative["5000"], original)
    _require_monotone(cumulative)
    full_resolved = _full_path_resolved(scoped, 5_000)
    entry_resolved = _entry_path_resolved(scoped, full_resolved, 5_000)
    return _diagnostic_payload(
        scoped,
        partition,
        track,
        original,
        cumulative,
        full_resolved,
        entry_resolved,
    )


def _diagnostic_payload(
    scoped: pd.DataFrame,
    partition: MuPartitionResult,
    track: MuArchiveTrack,
    original: dict[str, object],
    cumulative: dict[str, dict[str, object]],
    full_resolved: pd.Series,
    entry_resolved: pd.Series,
) -> dict[str, object]:
    return {
        "status": original["status"],
        "qualification_authority": "none",
        "partition": "development",
        "track": track_identity(track),
        "development_start_utc": partition.start_utc.isoformat(),
        "development_end_utc": partition.end_utc.isoformat(),
        "scoped_bar_count": len(scoped),
        "original_5000ms_path_quality": original,
        "unresolved_lifecycles_5000ms": {
            "nominal": _unresolved_lifecycles(
                scoped,
                partition.nominal,
                full_resolved,
                entry_resolved,
                family=track.family,
                timeframe=track.timeframe,
            ),
            "stress": _unresolved_lifecycles(
                scoped,
                partition.stress,
                full_resolved,
                entry_resolved,
                family=track.family,
                timeframe=track.timeframe,
            ),
        },
        "cumulative_thresholds_ms": cumulative,
        "mark_gap_bar_buckets_ms": _bar_buckets(scoped),
        "zero_mark_bars": int(scoped["mark_snapshot_count"].astype(int).eq(0).sum()),
        "l2_outage_bars": _l2_outage_bars(scoped),
        "monotonicity_verified": True,
        "limitations": [
            "thresholds are technical sensitivity only and cannot resolve the "
            "frozen 5000ms qualification path",
            "no prices are interpolated and no synthetic exits are generated",
            "validation and holdout are neither accepted nor accessed",
        ],
    }


def _unresolved_lifecycles(
    bars: pd.DataFrame,
    report: SharedPortfolioReport,
    full_resolved: pd.Series,
    entry_resolved: pd.Series,
    *,
    family: str,
    timeframe: str,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    interval = pd.Timedelta(minutes=5 if timeframe == "5m" else 15)
    for trade in report.trades:
        mark_bad, entry_bad = _mark_overlap(
            bars,
            trade,
            full_resolved,
            entry_resolved,
            interval,
        )
        l2_bad = _l2_overlap(bars, trade, family)
        if not (mark_bad or l2_bad):
            continue
        output.append(
            {
                "lifecycle_key": (
                    f"{trade.direction}|{trade.signal_time_utc}|"
                    f"{trade.entry_time_utc}|{trade.exit_time_utc}"
                ),
                "direction": trade.direction,
                "signal_time_utc": trade.signal_time_utc,
                "entry_time_utc": trade.entry_time_utc,
                "exit_time_utc": trade.exit_time_utc,
                "mark_path_unresolved": mark_bad,
                "entry_slice_unresolved": entry_bad,
                "l2_path_unresolved": l2_bad,
            }
        )
    return output


def _require_selected_track(track: MuArchiveTrack) -> None:
    expected = (
        "15m",
        "breakout_pressure",
        _SELECTED_PROVIDER_ID,
        _SELECTED_PROFILE_ID,
        _SELECTED_CONFIG,
    )
    observed = (
        track.timeframe,
        track.family,
        track.provider_id,
        track.profile_id,
        track.config,
    )
    if observed != expected:
        raise ValueError("MU path diagnostic requires the frozen selected track")


def _development_bars(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
) -> pd.DataFrame:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("MU path diagnostic bars require a timezone-aware index")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("MU path diagnostic bars must be ordered and unique")
    start = pd.Timestamp(partition.start_utc)
    end = pd.Timestamp(partition.end_utc)
    if start.tz is None or end.tz is None or start >= end:
        raise ValueError("MU development partition bounds are invalid")
    scoped = bars.loc[(bars.index >= start) & (bars.index < end)].copy()
    if scoped.empty:
        raise ValueError("MU development partition has no scoped bars")
    return scoped


def _require_partition_lifecycles(partition: MuPartitionResult) -> None:
    start = pd.Timestamp(partition.start_utc)
    end = pd.Timestamp(partition.end_utc)
    for report in (partition.nominal, partition.stress):
        for trade in report.trades:
            times = (
                pd.Timestamp(trade.signal_time_utc),
                pd.Timestamp(trade.entry_time_utc),
                pd.Timestamp(trade.exit_time_utc),
            )
            if times[0] < start or times[2] > end:
                raise ValueError(
                    "MU development trade lifecycle exceeds partition bounds"
                )


def _threshold_result(
    bars: pd.DataFrame,
    partition: MuPartitionResult,
    *,
    timeframe: str,
    family: str,
    threshold_ms: int,
) -> dict[str, object]:
    full_resolved = _full_path_resolved(bars, threshold_ms)
    entry_resolved = _entry_path_resolved(bars, full_resolved, threshold_ms)
    return {
        "resolved_bars": int(full_resolved.sum()),
        "unresolved_bars": int((~full_resolved).sum()),
        "nominal": _report_overlap(
            bars,
            partition.nominal,
            full_resolved,
            entry_resolved,
            timeframe=timeframe,
            family=family,
        ),
        "stress": _report_overlap(
            bars,
            partition.stress,
            full_resolved,
            entry_resolved,
            timeframe=timeframe,
            family=family,
        ),
        "unresolved_lifecycles": {
            "nominal": _unresolved_lifecycles(
                bars,
                partition.nominal,
                full_resolved,
                entry_resolved,
                family=family,
                timeframe=timeframe,
            ),
            "stress": _unresolved_lifecycles(
                bars,
                partition.stress,
                full_resolved,
                entry_resolved,
                family=family,
                timeframe=timeframe,
            ),
        },
    }


def _report_overlap(
    bars: pd.DataFrame,
    report: SharedPortfolioReport,
    full_resolved: pd.Series,
    entry_resolved: pd.Series,
    *,
    timeframe: str,
    family: str,
) -> dict[str, object]:
    counts = {
        "affected_trades": 0,
        "resolved_trades": 0,
        "mark_only_trades": 0,
        "l2_only_trades": 0,
        "mark_and_l2_trades": 0,
        "entry_slice_unresolved_trades": 0,
    }
    sides = {"long": 0, "short": 0}
    interval = pd.Timedelta(minutes=5 if timeframe == "5m" else 15)
    for trade in report.trades:
        mark_bad, entry_bad = _mark_overlap(
            bars,
            trade,
            full_resolved,
            entry_resolved,
            interval,
        )
        l2_bad = _l2_overlap(bars, trade, family)
        affected = mark_bad or l2_bad
        counts["affected_trades"] += int(affected)
        counts["mark_only_trades"] += int(mark_bad and not l2_bad)
        counts["l2_only_trades"] += int(l2_bad and not mark_bad)
        counts["mark_and_l2_trades"] += int(mark_bad and l2_bad)
        counts["entry_slice_unresolved_trades"] += int(entry_bad)
        sides[trade.direction] += int(affected)
    counts["resolved_trades"] = report.completed_trades - counts["affected_trades"]
    return {**counts, "by_side": sides, "completed_trades": report.completed_trades}


def _mark_overlap(
    bars: pd.DataFrame,
    trade: SharedPortfolioTrade,
    full_resolved: pd.Series,
    entry_resolved: pd.Series,
    interval: pd.Timedelta,
) -> tuple[bool, bool]:
    entry = pd.Timestamp(trade.entry_time_utc)
    exit_at = pd.Timestamp(trade.exit_time_utc)
    active = bars.index.to_series().lt(exit_at) & (bars.index + interval > entry)
    entry_bad = not _evidence_at_or_before(entry_resolved, entry)
    return bool((~full_resolved.loc[active]).any()) or entry_bad, entry_bad


def _l2_overlap(
    bars: pd.DataFrame,
    trade: SharedPortfolioTrade,
    family: str,
) -> bool:
    decision = family == "breakout_pressure" and _stale_l2_row(
        bars,
        pd.Timestamp(trade.signal_time_utc),
        "decision",
    )
    entry = _stale_l2_row(bars, pd.Timestamp(trade.entry_time_utc), "entry")
    return decision or entry or _stale_exit_quote(bars, trade)


def _full_path_resolved(bars: pd.DataFrame, threshold_ms: int) -> pd.Series:
    source = bars["risk_path_source"].astype(str).eq(_RISK_SOURCE)
    complete = _strict_bool(bars["trade_bundle_complete"])
    snapshots = pd.to_numeric(bars["mark_snapshot_count"], errors="raise")
    interval = pd.to_numeric(bars["maximum_mark_interval_ms"], errors="raise")
    resolved = source & complete & snapshots.ge(2) & interval.le(threshold_ms)
    if threshold_ms == 5_000:
        resolved &= _strict_bool(bars["mark_path_complete"])
    return resolved


def _entry_path_resolved(
    bars: pd.DataFrame,
    full_resolved: pd.Series,
    threshold_ms: int,
) -> pd.Series:
    snapshots = pd.to_numeric(bars["entry_mark_snapshot_count"], errors="raise")
    interval = pd.to_numeric(
        bars["entry_maximum_mark_interval_ms"],
        errors="raise",
    )
    resolved = full_resolved & snapshots.ge(1) & interval.le(threshold_ms)
    if threshold_ms == 5_000:
        resolved &= _strict_bool(bars["entry_mark_path_complete"])
    return resolved


def _strict_bool(values: pd.Series) -> pd.Series:
    if not pd.api.types.is_bool_dtype(values):
        raise ValueError("MU path diagnostic completeness fields must be boolean")
    return values.astype(bool)


def _bar_buckets(bars: pd.DataFrame) -> dict[str, int]:
    gaps = pd.to_numeric(bars["maximum_mark_interval_ms"], errors="raise")
    return {
        "le_5000": int(gaps.le(5_000).sum()),
        "gt_5000_le_6000": int((gaps.gt(5_000) & gaps.le(6_000)).sum()),
        "gt_6000_le_7500": int((gaps.gt(6_000) & gaps.le(7_500)).sum()),
        "gt_7500_le_10000": int((gaps.gt(7_500) & gaps.le(10_000)).sum()),
        "gt_10000_le_15000": int((gaps.gt(10_000) & gaps.le(15_000)).sum()),
        "gt_15000": int(gaps.gt(15_000).sum()),
    }


def _l2_outage_bars(bars: pd.DataFrame) -> int:
    unobserved = (
        bars[
            [
                "first_boundary_delay_ms",
                "maximum_snapshot_interval_ms",
                "end_boundary_age_ms",
            ]
        ]
        .astype(float)
        .max(axis=1)
    )
    return int(
        (unobserved.gt(15_000) | bars["source_snapshot_count"].astype(int).lt(2)).sum()
    )


def _require_original_parity(
    threshold: dict[str, object],
    original: dict[str, object],
) -> None:
    for scenario in ("nominal", "stress"):
        observed = _mapping(threshold[scenario], scenario)
        expected = _mapping(original[scenario], scenario)
        if observed["affected_trades"] != expected["unresolved_lifecycle_trades"]:
            raise ValueError("MU 5000ms diagnostic diverges from qualification path")


def _require_monotone(cumulative: dict[str, dict[str, object]]) -> None:
    for scenario in ("nominal", "stress"):
        affected = [
            int(_mapping(cumulative[str(value)][scenario], scenario)["affected_trades"])
            for value in _THRESHOLDS_MS
        ]
        if any(later > earlier for earlier, later in zip(affected, affected[1:])):
            raise ValueError("MU threshold lifecycle sensitivity must be monotone")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"MU {label} diagnostic must be an object")
    return value


def _require_columns(bars: pd.DataFrame) -> None:
    required = {
        "risk_path_source",
        "mark_path_complete",
        "maximum_mark_interval_ms",
        "mark_snapshot_count",
        "trade_bundle_complete",
        "entry_mark_path_complete",
        "entry_maximum_mark_interval_ms",
        "entry_mark_snapshot_count",
        "first_boundary_delay_ms",
        "maximum_snapshot_interval_ms",
        "end_boundary_age_ms",
        "source_snapshot_count",
    }
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"MU path diagnostic bars missing columns: {sorted(missing)}")
    numeric = bars[
        [
            "maximum_mark_interval_ms",
            "entry_maximum_mark_interval_ms",
            "first_boundary_delay_ms",
            "maximum_snapshot_interval_ms",
            "end_boundary_age_ms",
        ]
    ].astype(float)
    if not numeric.map(math.isfinite).to_numpy().all() or numeric.lt(0).any().any():
        raise ValueError(
            "MU path diagnostic timing fields must be finite and non-negative"
        )
