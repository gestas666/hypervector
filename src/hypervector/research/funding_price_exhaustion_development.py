"""Development-only fixed-horizon funding/price-exhaustion evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.research.funding_price_exhaustion_signals import (
    FundingPriceExhaustionConfig,
    build_funding_price_exhaustion_signals,
)

_BAR_MINUTES = 5


@dataclass(frozen=True)
class FundingExhaustionCosts:
    """Frozen nominal and stress round-trip friction in basis points."""

    nominal_round_trip_bps: float
    stress_round_trip_bps: float

    def __post_init__(self) -> None:
        """Reject malformed or inverted friction assumptions."""
        nominal = self.nominal_round_trip_bps
        stress = self.stress_round_trip_bps
        if not math.isfinite(nominal) or nominal < 0.0:
            raise ValueError("nominal round-trip cost must be finite and non-negative")
        if not math.isfinite(stress) or stress < nominal:
            raise ValueError("stress round-trip cost cannot be cheaper than nominal")


@dataclass(frozen=True)
class FundingExhaustionDevelopmentSpec:
    """Frozen horizons and robustness thresholds for one development screen."""

    horizons_minutes: tuple[int, ...] = (15, 60, 240, 480, 1_440)
    fold_count: int = 5
    minimum_observations: int = 10
    minimum_side_observations: int = 5

    def __post_init__(self) -> None:
        """Require unique five-minute horizons and usable thresholds."""
        horizons = self.horizons_minutes
        if not horizons or len(set(horizons)) != len(horizons):
            raise ValueError("development horizons must be unique and non-empty")
        if any(value < _BAR_MINUTES or value % _BAR_MINUTES for value in horizons):
            raise ValueError("development horizons must use positive five-minute bars")
        if self.fold_count < 2:
            raise ValueError("development screen requires at least two folds")
        if self.minimum_observations < 1 or self.minimum_side_observations < 1:
            raise ValueError("development observation thresholds must be positive")


@dataclass(frozen=True)
class FundingExhaustionPath:
    """One resolved side-relative fixed-horizon path before friction."""

    side: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    gross_return_bps: float
    funding_return_bps: float


@dataclass(frozen=True)
class _SignalBlock:
    bars: pd.DataFrame
    long_indexes: tuple[int, ...]
    short_indexes: tuple[int, ...]


def evaluate_funding_price_exhaustion_development(
    bars: pd.DataFrame,
    funding: pd.DataFrame,
    config: FundingPriceExhaustionConfig,
    costs: FundingExhaustionCosts,
    spec: FundingExhaustionDevelopmentSpec,
    *,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> dict[str, object]:
    """Evaluate frozen signals without reading validation or holdout outcomes."""
    start, end = _validated_window(start_utc, end_utc)
    frame = _validated_bars(bars, start, end)
    funding_frame = _normalized_funding(funding)
    blocks = _build_signal_blocks(frame, funding_frame, config)
    horizon_reports: dict[str, object] = {}
    for horizon in spec.horizons_minutes:
        paths, censored = _resolve_horizon(blocks, funding_frame, horizon)
        independent = _non_overlapping(paths)
        horizon_reports[_horizon_label(horizon)] = {
            "resolved_observations": len(paths),
            "censored_observations": censored,
            "all_resolved": _path_summary(paths, costs, start, end, spec.fold_count),
            "primary_non_overlapping": _path_summary(
                independent, costs, start, end, spec.fold_count
            ),
        }
    supportive = _supportive_horizons(horizon_reports, spec)
    maximum = max(
        int(_mapping(value)["primary_non_overlapping"]["observations"])
        for value in horizon_reports.values()
    )
    decision = _decision(maximum, supportive, spec.minimum_observations)
    return {
        "decision": decision,
        "supportive_horizons": supportive,
        "signal_counts": _signal_counts(blocks),
        "technical": _technical_summary(frame, blocks),
        "horizons": horizon_reports,
    }


def _validated_window(
    start_utc: pd.Timestamp, end_utc: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = pd.Timestamp(start_utc), pd.Timestamp(end_utc)
    if start.tz is None or end.tz is None:
        raise ValueError("development window must be timezone-aware")
    start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
    if start >= end:
        raise ValueError("development window start must precede end")
    return start, end


def _validated_bars(
    bars: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(bars.columns))
    if missing:
        raise ValueError(f"development bars missing columns: {missing}")
    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    if "contains_gap_fill" in bars:
        columns.append("contains_gap_fill")
    frame = bars.loc[:, columns].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.as_unit("ns")
    timestamps = pd.DatetimeIndex(frame["timestamp"])
    if (
        timestamps.hasnans
        or timestamps.has_duplicates
        or not timestamps.is_monotonic_increasing
    ):
        raise ValueError("development bars must be ordered and unique")
    if frame.empty or timestamps[0] < start or timestamps[-1] >= end:
        raise ValueError(
            "development bars must be non-empty and inside the frozen window"
        )
    if "contains_gap_fill" in frame:
        frame["contains_gap_fill"] = frame["contains_gap_fill"].astype(bool)
    else:
        frame["contains_gap_fill"] = False
    return frame.reset_index(drop=True)


def _normalized_funding(funding: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "event_ts_ms", "funding_rate", "source"}
    missing = sorted(required - set(funding.columns))
    if missing:
        raise ValueError(f"development funding missing columns: {missing}")
    frame = funding.loc[:, sorted(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.as_unit("ns")
    frame["event_ts_ms"] = pd.to_numeric(frame["event_ts_ms"], errors="raise")
    frame["funding_rate"] = pd.to_numeric(frame["funding_rate"], errors="raise")
    return frame


def _build_signal_blocks(
    bars: pd.DataFrame,
    funding: pd.DataFrame,
    config: FundingPriceExhaustionConfig,
) -> tuple[_SignalBlock, ...]:
    groups = bars["timestamp"].diff().ne(pd.Timedelta(minutes=_BAR_MINUTES)).cumsum()
    output: list[_SignalBlock] = []
    for _group, raw in bars.groupby(groups, sort=False):
        block = raw.reset_index(drop=True)
        signals = build_funding_price_exhaustion_signals(block, funding, config)
        output.append(
            _SignalBlock(
                block,
                tuple(
                    int(value)
                    for value in signals.long_signals[signals.long_signals].index
                ),
                tuple(
                    int(value)
                    for value in signals.short_signals[signals.short_signals].index
                ),
            )
        )
    return tuple(output)


def _resolve_horizon(
    blocks: tuple[_SignalBlock, ...],
    funding: pd.DataFrame,
    horizon_minutes: int,
) -> tuple[tuple[FundingExhaustionPath, ...], int]:
    paths: list[FundingExhaustionPath] = []
    censored = 0
    horizon_bars = horizon_minutes // _BAR_MINUTES
    for block in blocks:
        for side, indexes in (
            ("long", block.long_indexes),
            ("short", block.short_indexes),
        ):
            for signal_index in indexes:
                path = _resolve_path(
                    block.bars, funding, side, signal_index, horizon_bars
                )
                if path is None:
                    censored += 1
                else:
                    paths.append(path)
    return tuple(sorted(paths, key=lambda item: item.entry_time)), censored


def _resolve_path(
    bars: pd.DataFrame,
    funding: pd.DataFrame,
    side: str,
    signal_index: int,
    horizon_bars: int,
) -> FundingExhaustionPath | None:
    entry_index = signal_index + 1
    exit_index = entry_index + horizon_bars - 1
    if exit_index >= len(bars):
        return None
    signal_time = pd.Timestamp(bars.iloc[signal_index]["timestamp"]) + pd.Timedelta(
        minutes=5
    )
    entry_time = pd.Timestamp(bars.iloc[entry_index]["timestamp"])
    exit_time = entry_time + pd.Timedelta(minutes=horizon_bars * _BAR_MINUTES)
    entry_price = float(bars.iloc[entry_index]["open"])
    exit_price = float(bars.iloc[exit_index]["close"])
    direction = 1.0 if side == "long" else -1.0
    gross = direction * (exit_price / entry_price - 1.0) * 10_000.0
    funding_return = _funding_return(funding, entry_time, exit_time, direction)
    return FundingExhaustionPath(
        side, signal_time, entry_time, exit_time, gross, funding_return
    )


def _funding_return(
    funding: pd.DataFrame,
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
    direction: float,
) -> float:
    mask = funding["timestamp"].gt(entry_time) & funding["timestamp"].le(exit_time)
    rates = funding.loc[mask, "funding_rate"].to_numpy(float)
    return float(-direction * rates.sum() * 10_000.0)


def _non_overlapping(
    paths: tuple[FundingExhaustionPath, ...],
) -> tuple[FundingExhaustionPath, ...]:
    selected: list[FundingExhaustionPath] = []
    next_available: pd.Timestamp | None = None
    for path in paths:
        if next_available is not None and path.entry_time < next_available:
            continue
        selected.append(path)
        next_available = path.exit_time
    return tuple(selected)


def _path_summary(
    paths: tuple[FundingExhaustionPath, ...],
    costs: FundingExhaustionCosts,
    start: pd.Timestamp,
    end: pd.Timestamp,
    fold_count: int,
) -> dict[str, object]:
    nominal = _net_values(paths, costs.nominal_round_trip_bps)
    stress = _net_values(paths, costs.stress_round_trip_bps)
    summary = {
        "observations": len(paths),
        "long_observations": sum(path.side == "long" for path in paths),
        "short_observations": sum(path.side == "short" for path in paths),
        "gross_return_bps": float(sum(path.gross_return_bps for path in paths)),
        "funding_return_bps": float(sum(path.funding_return_bps for path in paths)),
        "nominal_net_bps": float(nominal.sum()),
        "stress_net_bps": float(stress.sum()),
        "stress_mean_bps": float(stress.mean()) if len(stress) else None,
        "stress_profit_factor": _profit_factor(stress),
        "stress_excluding_largest_winner_bps": _excluding_largest(stress),
    }
    folds = _fold_nets(paths, stress, start, end, fold_count)
    summary["stress_fold_net_bps"] = folds
    summary["stress_positive_folds"] = sum(value > 0.0 for value in folds)
    summary["sides"] = {
        side: _side_summary(paths, stress, side) for side in ("long", "short")
    }
    return summary


def _net_values(
    paths: tuple[FundingExhaustionPath, ...], cost_bps: float
) -> np.ndarray:
    return np.asarray(
        [path.gross_return_bps + path.funding_return_bps - cost_bps for path in paths],
        dtype=float,
    )


def _profit_factor(values: np.ndarray) -> float | None:
    gains = float(values[values > 0.0].sum())
    losses = float(-values[values < 0.0].sum())
    if losses == 0.0:
        return None
    return gains / losses


def _excluding_largest(values: np.ndarray) -> float:
    if not len(values):
        return 0.0
    winners = values[values > 0.0]
    return float(values.sum() - (winners.max() if len(winners) else 0.0))


def _fold_nets(
    paths: tuple[FundingExhaustionPath, ...],
    values: np.ndarray,
    start: pd.Timestamp,
    end: pd.Timestamp,
    fold_count: int,
) -> list[float]:
    folds = [0.0] * fold_count
    duration = end.value - start.value
    for path, value in zip(paths, values, strict=True):
        offset = path.entry_time.value - start.value
        index = min(fold_count - 1, max(0, int(offset * fold_count / duration)))
        folds[index] += float(value)
    return folds


def _side_summary(
    paths: tuple[FundingExhaustionPath, ...], values: np.ndarray, side: str
) -> dict[str, object]:
    selected = np.asarray(
        [value for path, value in zip(paths, values, strict=True) if path.side == side],
        dtype=float,
    )
    return {
        "observations": len(selected),
        "stress_net_bps": float(selected.sum()),
        "stress_profit_factor": _profit_factor(selected),
        "stress_excluding_largest_winner_bps": _excluding_largest(selected),
    }


def _supportive_horizons(
    reports: dict[str, object], spec: FundingExhaustionDevelopmentSpec
) -> list[str]:
    output: list[str] = []
    for label, raw in reports.items():
        primary = _mapping(raw)["primary_non_overlapping"]
        if not isinstance(primary, dict):
            raise TypeError("primary horizon summary must be a mapping")
        if _supportive_primary(primary, spec):
            output.append(label)
    return output


def _supportive_primary(
    summary: dict[str, object], spec: FundingExhaustionDevelopmentSpec
) -> bool:
    count = int(summary["observations"])
    net = float(summary["stress_net_bps"])
    excluded = float(summary["stress_excluding_largest_winner_bps"])
    factor = summary["stress_profit_factor"]
    factor_ok = (factor is None and net > 0.0) or (
        isinstance(factor, float) and factor > 1.0
    )
    if count < spec.minimum_observations or net <= 0.0 or excluded <= 0.0:
        return False
    if not factor_ok or int(summary["stress_positive_folds"]) < 3:
        return False
    return _directional_guard(_mapping(summary["sides"]), spec)


def _directional_guard(
    sides: dict[str, object], spec: FundingExhaustionDevelopmentSpec
) -> bool:
    long = _mapping(sides["long"])
    short = _mapping(sides["short"])
    minimum = spec.minimum_side_observations
    if int(long["observations"]) < minimum or int(short["observations"]) < minimum:
        return True
    return all(
        float(side["stress_excluding_largest_winner_bps"]) >= 0.0
        for side in (long, short)
    )


def _decision(maximum: int, supportive: list[str], minimum: int) -> str:
    if maximum < minimum:
        return "insufficient_development_evidence"
    if supportive:
        return "supportive_development_only"
    return "rejected_development_only"


def _signal_counts(blocks: tuple[_SignalBlock, ...]) -> dict[str, int]:
    longs = sum(len(block.long_indexes) for block in blocks)
    shorts = sum(len(block.short_indexes) for block in blocks)
    return {"long": longs, "short": shorts, "total": longs + shorts}


def _technical_summary(
    bars: pd.DataFrame, blocks: tuple[_SignalBlock, ...]
) -> dict[str, int]:
    expected = (
        int(
            (bars.iloc[-1]["timestamp"] - bars.iloc[0]["timestamp"])
            / pd.Timedelta(minutes=5)
        )
        + 1
    )
    return {
        "observed_bars": len(bars),
        "expected_bars_inside_observed_bounds": expected,
        "missing_bars_inside_observed_bounds": expected - len(bars),
        "contiguous_blocks": len(blocks),
    }


def _horizon_label(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h"


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("development report value must be a mapping")
    return value
