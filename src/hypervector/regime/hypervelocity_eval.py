"""Report-only acceptance metrics for Hypervelocity regime candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig, classify_timeframe
from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.models import BreakoutDirection, PrimaryRegime


@dataclass(frozen=True)
class EntryAlignmentReport:
    """Alignment between recorded entries and candidate regime decisions."""

    recorded_positions: int
    unique_entry_decisions: int
    total_entries: int
    direction_matches: int
    direction_recall_pct: float
    false_range_at_entries: int
    no_entry_state_at_entries: int
    direction_recall_by_lookback_pct: dict[str, float]
    range_only_entries_by_lookback: dict[str, int]


@dataclass(frozen=True)
class BreakoutQualityReport:
    """Directional target follow-through for confirmed breakout events."""

    breakout_bars: int
    breakout_events: int
    false_breakouts: int
    false_breakout_pct: float


@dataclass(frozen=True)
class RangeQualityReport:
    """Forward outcomes observed after bars classified as range."""

    range_events: int
    one_sided_expansions: int
    two_sided_oscillations: int
    quiet_ranges: int
    one_sided_expansion_pct: float


@dataclass(frozen=True)
class HypervelocityRegimeReport:
    """Complete report-only result for one causal regime candidate."""

    total_bars: int
    entry_alignment: EntryAlignmentReport
    breakout_quality: BreakoutQualityReport
    range_quality: RangeQualityReport
    state_distribution: dict[str, int]
    label_churn: int
    mean_transition_latency_bars: float
    bar_sources: tuple[str, ...]
    source_limited: bool
    context_direction_recall_pct: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe nested representation."""
        return asdict(self)


def _datetime_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if isinstance(bars.index, pd.DatetimeIndex):
        result = bars.copy()
    elif "timestamp" in bars.columns:
        result = bars.copy()
        result.index = pd.DatetimeIndex(pd.to_datetime(result["timestamp"], utc=True))
    else:
        raise ValueError("bars require a DatetimeIndex or timestamp column")
    return result[~result.index.duplicated(keep="last")].sort_index()


def _position_times(positions: pd.DataFrame) -> pd.DatetimeIndex:
    required = {"open_time_utc", "side"}
    missing = required.difference(positions.columns)
    if missing:
        raise ValueError(f"positions missing columns: {sorted(missing)}")
    return pd.DatetimeIndex(pd.to_datetime(positions["open_time_utc"], utc=True))


def _unique_entry_decisions(
    positions: pd.DataFrame,
    *,
    cluster_seconds: float,
) -> pd.DataFrame:
    if cluster_seconds < 0.0:
        raise ValueError("cluster_seconds must be non-negative")
    timed = (
        positions.assign(event_time=_position_times(positions))
        .sort_values("event_time")
        .reset_index(drop=True)
    )
    keep: list[int] = []
    last_by_side: dict[str, pd.Timestamp] = {}
    threshold = pd.Timedelta(seconds=cluster_seconds)
    for index, row in timed.iterrows():
        side = str(row["side"]).lower()
        event_time = pd.Timestamp(row["event_time"])
        previous = last_by_side.get(side)
        if previous is None or event_time - previous > threshold:
            keep.append(index)
        last_by_side[side] = event_time
    return timed.loc[keep]


def _decision_directions(rows: pd.DataFrame) -> pd.Series:
    directions = pd.Series(None, index=rows.index, dtype=object)
    directions = directions.mask(
        rows["primary_regime"].eq(PrimaryRegime.TREND_UP.value), "long"
    )
    directions = directions.mask(
        rows["primary_regime"].eq(PrimaryRegime.TREND_DOWN.value), "short"
    )
    is_breakout = rows["primary_regime"].eq(PrimaryRegime.BREAKOUT.value)
    directions = directions.mask(
        is_breakout & rows["breakout_direction"].eq(BreakoutDirection.UPWARD.value),
        "long",
    )
    return directions.mask(
        is_breakout & rows["breakout_direction"].eq(BreakoutDirection.DOWNWARD.value),
        "short",
    )


def _available_decisions(
    decisions: pd.DataFrame,
    bar_duration: pd.Timedelta,
) -> pd.DataFrame:
    if bar_duration <= pd.Timedelta(0):
        raise ValueError("bar_duration must be positive")
    available = decisions.copy()
    available.index = available.index + bar_duration
    return available


def _window_alignment(
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
    minutes: int,
) -> tuple[int, int]:
    matches = 0
    range_only = 0
    normalized_index = decisions.index.as_unit("ns")
    for row in positions.itertuples(index=False):
        timestamp = pd.Timestamp(row.event_time).as_unit("ns")
        end_position = int(normalized_index.searchsorted(timestamp, side="right")) - 1
        if end_position < 0:
            continue
        end_time = decisions.index[end_position]
        start = end_time - pd.Timedelta(minutes=minutes)
        window = decisions.loc[
            (decisions.index >= start) & (decisions.index <= end_time)
        ]
        predicted = set(_decision_directions(window).dropna().astype(str))
        matches += int(str(row.side).lower() in predicted)
        range_only += int(
            len(window) > 0
            and window["primary_regime"].eq(PrimaryRegime.RANGE.value).all()
        )
    return matches, range_only


def evaluate_entry_alignment(
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
    *,
    lookback_minutes: tuple[int, ...] = (0, 1, 5, 10, 30),
    decision_cluster_seconds: float = 1.0,
    bar_duration: pd.Timedelta = pd.Timedelta(minutes=1),
) -> EntryAlignmentReport:
    """Measure whether candidate states recover recorded entry directions."""
    unique = _unique_entry_decisions(
        positions,
        cluster_seconds=decision_cluster_seconds,
    )
    available = _available_decisions(decisions, bar_duration)
    aligned = available.reindex(pd.DatetimeIndex(unique["event_time"]), method="ffill")
    wanted = unique["side"].astype(str).str.lower().to_numpy()
    predicted = _decision_directions(aligned).to_numpy()
    primary = aligned["primary_regime"]
    matches = int((predicted == wanted).sum())
    total = len(unique)
    by_window = {
        minutes: _window_alignment(available, unique, minutes)
        for minutes in lookback_minutes
    }
    return EntryAlignmentReport(
        recorded_positions=len(positions),
        unique_entry_decisions=total,
        total_entries=total,
        direction_matches=matches,
        direction_recall_pct=(100.0 * matches / total) if total else 0.0,
        false_range_at_entries=int(primary.eq(PrimaryRegime.RANGE.value).sum()),
        no_entry_state_at_entries=int(pd.isna(predicted).sum()),
        direction_recall_by_lookback_pct={
            f"{minutes}m": (100.0 * values[0] / total) if total else 0.0
            for minutes, values in by_window.items()
        },
        range_only_entries_by_lookback={
            f"{minutes}m": values[1] for minutes, values in by_window.items()
        },
    )


def _future_extreme(series: pd.Series, horizon: int, kind: str) -> pd.Series:
    if horizon < 1:
        raise ValueError("forward_horizon must be positive")
    future = pd.concat([series.shift(-step) for step in range(1, horizon + 1)], axis=1)
    if kind == "max":
        return future.max(axis=1, skipna=False)
    return future.min(axis=1, skipna=False)


def evaluate_breakout_quality(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    target_price_fraction: float,
    forward_horizon: int,
) -> BreakoutQualityReport:
    """Report breakouts that fail to reach their directional target."""
    future_high = _future_extreme(bars["high"].astype(float), forward_horizon, "max")
    future_low = _future_extreme(bars["low"].astype(float), forward_horizon, "min")
    close = bars["close"].astype(float)
    breakout = decisions["primary_regime"].eq(PrimaryRegime.BREAKOUT.value)
    direction = decisions["breakout_direction"]
    onset = breakout & (
        ~breakout.shift(fill_value=False) | direction.ne(direction.shift())
    )
    valid = onset & future_high.notna() & future_low.notna()
    upward = decisions["breakout_direction"].eq(BreakoutDirection.UPWARD.value)
    downward = decisions["breakout_direction"].eq(BreakoutDirection.DOWNWARD.value)
    success = (upward & (future_high >= close * (1.0 + target_price_fraction))) | (
        downward & (future_low <= close * (1.0 - target_price_fraction))
    )
    count = int(valid.sum())
    failures = int((valid & ~success).sum())
    return BreakoutQualityReport(
        breakout_bars=int(breakout.sum()),
        breakout_events=count,
        false_breakouts=failures,
        false_breakout_pct=(100.0 * failures / count) if count else 0.0,
    )


def evaluate_range_quality(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    target_price_fraction: float,
    forward_horizon: int,
) -> RangeQualityReport:
    """Classify forward outcomes after range states without gating execution."""
    future_high = _future_extreme(bars["high"].astype(float), forward_horizon, "max")
    future_low = _future_extreme(bars["low"].astype(float), forward_horizon, "min")
    close = bars["close"].astype(float)
    valid = decisions["primary_regime"].eq(PrimaryRegime.RANGE.value)
    valid &= future_high.notna() & future_low.notna()
    upward = future_high >= close * (1.0 + target_price_fraction)
    downward = future_low <= close * (1.0 - target_price_fraction)
    one_sided = valid & upward.ne(downward)
    two_sided = valid & upward & downward
    quiet = valid & ~upward & ~downward
    count = int(valid.sum())
    one_sided_count = int(one_sided.sum())
    return RangeQualityReport(
        range_events=count,
        one_sided_expansions=one_sided_count,
        two_sided_oscillations=int(two_sided.sum()),
        quiet_ranges=int(quiet.sum()),
        one_sided_expansion_pct=(100.0 * one_sided_count / count) if count else 0.0,
    )


def _mean_transition_latency(decisions: pd.DataFrame) -> float:
    primary = decisions["primary_regime"].astype(str)
    state_1m = decisions["state_1m"].astype(str)
    changes = [
        i for i in range(1, len(primary)) if primary.iloc[i] != primary.iloc[i - 1]
    ]
    latencies: list[int] = []
    for position in changes:
        onset = position
        while onset > 0 and state_1m.iloc[onset - 1] == primary.iloc[position]:
            onset -= 1
        latencies.append(max(0, position - onset))
    return float(sum(latencies) / len(latencies)) if latencies else 0.0


def _state_decisions(index: pd.Index, state: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "primary_regime": state,
            "breakout_direction": None,
        },
        index=index,
    )


def _hard_30m_state(bars: pd.DataFrame) -> pd.Series:
    aggregated = (
        bars.resample("30min", label="right", closed="right")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )
    classified = classify_timeframe(aggregated, RegimeClassifierConfig()).shift(1)
    return (
        classified["primary_regime"]
        .reindex(bars.index, method="ffill")
        .fillna(PrimaryRegime.UNKNOWN.value)
    )


def _context_recalls(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> dict[str, float]:
    candidates = {
        "canonical_5m_primary": decisions,
        "hard_5m": _state_decisions(decisions.index, decisions["state_5m"]),
        "hard_15m": _state_decisions(decisions.index, decisions["context_15m"]),
        "hard_30m": _state_decisions(decisions.index, _hard_30m_state(bars)),
    }
    return {
        name: evaluate_entry_alignment(candidate, positions).direction_recall_pct
        for name, candidate in candidates.items()
    }


def evaluate_hypervelocity_regimes(
    bars: pd.DataFrame,
    positions: pd.DataFrame,
    *,
    target_price_fraction: float = 0.002,
    forward_horizon: int = 30,
    config: RegimeClassifierConfig | None = None,
) -> HypervelocityRegimeReport:
    """Evaluate canonical regimes without accepting or rejecting a trial."""
    indexed = _datetime_bars(bars)
    decisions = classify_multitimeframe(indexed, config=config)
    alignment = evaluate_entry_alignment(decisions, positions)
    breakout = evaluate_breakout_quality(
        indexed,
        decisions,
        target_price_fraction=target_price_fraction,
        forward_horizon=forward_horizon,
    )
    range_quality = evaluate_range_quality(
        indexed,
        decisions,
        target_price_fraction=target_price_fraction,
        forward_horizon=forward_horizon,
    )
    primary = decisions["primary_regime"].astype(str)
    sources = tuple(
        sorted(indexed.get("source", pd.Series(dtype=str)).astype(str).unique())
    )
    return HypervelocityRegimeReport(
        total_bars=len(indexed),
        entry_alignment=alignment,
        breakout_quality=breakout,
        range_quality=range_quality,
        state_distribution={
            str(key): int(value) for key, value in primary.value_counts().items()
        },
        label_churn=int(primary.ne(primary.shift()).sum() - (1 if len(primary) else 0)),
        mean_transition_latency_bars=_mean_transition_latency(decisions),
        bar_sources=sources,
        source_limited=sources != ("bitget",),
        context_direction_recall_pct=_context_recalls(indexed, decisions, positions),
    )
