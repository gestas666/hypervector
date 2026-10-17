"""Report-only acceptance metrics for Hypervelocity regime candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from hypervector.data.source_position_records import (
    reconcile_source_position_records,
)
from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.regime.composite import _completed_context, classify_multitimeframe
from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.strategies.hypervelocity_contract import faithful_regime_config


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
    position_regime_performance: dict[str, object]
    cost_sensitivity: dict[str, object]

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
    if result.index.has_duplicates or not result.index.is_monotonic_increasing:
        raise ValueError("bars require a unique, increasing timestamp index")
    return result


def _position_times(positions: pd.DataFrame) -> pd.DatetimeIndex:
    required = {"open_time_utc", "side"}
    missing = required.difference(positions.columns)
    if missing:
        raise ValueError(f"positions missing columns: {sorted(missing)}")
    return pd.DatetimeIndex(
        pd.to_datetime(positions["open_time_utc"], utc=True, format="ISO8601")
    )


def _unique_entry_decisions(
    positions: pd.DataFrame,
    *,
    cluster_seconds: float,
) -> pd.DataFrame:
    if cluster_seconds < 0.0:
        raise ValueError("cluster_seconds must be non-negative")
    reconciled = reconcile_source_position_records(positions)
    timed = (
        reconciled.assign(event_time=_position_times(reconciled))
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
    if "entry_direction" in rows.columns:
        tactical = rows["entry_direction"].astype(object)
        return tactical.where(tactical.isin(["long", "short"]), None)
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


_NANOSECONDS_PER_MINUTE = 60_000_000_000
_DIRECTION_COLUMNS = ("primary_regime", "breakout_direction", "entry_direction")


@dataclass(frozen=True)
class _PreparedEntries:
    """Recorded entries de-duplicated once and reused across candidates."""

    recorded_positions: int
    unique: pd.DataFrame
    event_times: pd.DatetimeIndex
    sides: np.ndarray


@dataclass(frozen=True)
class _PreparedDecisions:
    """Per-candidate decision arrays shared by every split and lookback."""

    index: pd.DatetimeIndex
    times_ns: np.ndarray
    directions: np.ndarray
    primary: np.ndarray
    long_prefix: np.ndarray
    short_prefix: np.ndarray
    range_prefix: np.ndarray


def _prepare_entries(
    positions: pd.DataFrame, *, cluster_seconds: float
) -> _PreparedEntries:
    unique = _unique_entry_decisions(positions, cluster_seconds=cluster_seconds)
    return _PreparedEntries(
        recorded_positions=len(positions),
        unique=unique,
        event_times=pd.DatetimeIndex(unique["event_time"]).as_unit("ns"),
        sides=unique["side"].astype(str).str.lower().to_numpy(),
    )


def _prefix(mask: np.ndarray) -> np.ndarray:
    return np.concatenate(([0], np.cumsum(mask, dtype=np.int64)))


def _prepare_decisions(
    decisions: pd.DataFrame, bar_duration: pd.Timedelta
) -> _PreparedDecisions | None:
    """Derive directions and prefix counts once; None means use the slow path.

    The vectorised path needs a unique, increasing DatetimeIndex (which the
    original ``reindex(method="ffill")`` also required).
    """
    index = decisions.index
    if not (
        isinstance(index, pd.DatetimeIndex)
        and index.is_monotonic_increasing
        and index.is_unique
    ):
        return None
    columns = [name for name in _DIRECTION_COLUMNS if name in decisions.columns]
    available = _available_decisions(decisions[columns], bar_duration)
    directions = _decision_directions(available).to_numpy(dtype=object)
    primary = available["primary_regime"].to_numpy(dtype=object)
    available_index = available.index.as_unit("ns")
    return _PreparedDecisions(
        index=available_index,
        times_ns=available_index.asi8,
        directions=directions,
        primary=primary,
        long_prefix=_prefix(directions == "long"),
        short_prefix=_prefix(directions == "short"),
        range_prefix=_prefix(primary == PrimaryRegime.RANGE.value),
    )


def _entry_alignment_report(
    prepared: _PreparedDecisions,
    entries: _PreparedEntries,
    lookback_minutes: tuple[int, ...],
) -> EntryAlignmentReport:
    """Vectorised equivalent of the per-position window loop."""
    end = prepared.index.searchsorted(entries.event_times, side="right") - 1
    found = end >= 0
    safe_end = np.where(found, end, 0)
    if prepared.times_ns.size:
        predicted = np.where(found, prepared.directions[safe_end], None)
        primary = np.where(found, prepared.primary[safe_end], None)
        end_ns = prepared.times_ns[safe_end]
    else:  # no decisions: every entry precedes the first available state
        predicted = np.full(len(end), None, dtype=object)
        primary = np.full(len(end), None, dtype=object)
        end_ns = np.zeros(len(end), dtype=np.int64)
    wanted = entries.sides
    matches = int((predicted == wanted).sum())
    total = len(entries.unique)
    is_long = wanted == "long"
    is_short = wanted == "short"
    by_window: dict[int, tuple[int, int]] = {}
    for minutes in lookback_minutes:
        low = np.searchsorted(
            prepared.times_ns, end_ns - minutes * _NANOSECONDS_PER_MINUTE, side="left"
        )
        high = np.searchsorted(prepared.times_ns, end_ns, side="right")
        longs = prepared.long_prefix[high] - prepared.long_prefix[low]
        shorts = prepared.short_prefix[high] - prepared.short_prefix[low]
        ranges = prepared.range_prefix[high] - prepared.range_prefix[low]
        matched = found & ((is_long & (longs > 0)) | (is_short & (shorts > 0)))
        range_only = found & (high > low) & (ranges == high - low)
        by_window[minutes] = (int(matched.sum()), int(range_only.sum()))
    return _alignment_report(
        entries.recorded_positions,
        total,
        matches,
        int((primary == PrimaryRegime.RANGE.value).sum()),
        int(pd.isna(predicted).sum()),
        by_window,
    )


def _alignment_report(
    recorded: int,
    total: int,
    matches: int,
    false_range: int,
    no_entry_state: int,
    by_window: dict[int, tuple[int, int]],
) -> EntryAlignmentReport:
    return EntryAlignmentReport(
        recorded_positions=recorded,
        unique_entry_decisions=total,
        total_entries=total,
        direction_matches=matches,
        direction_recall_pct=(100.0 * matches / total) if total else 0.0,
        false_range_at_entries=false_range,
        no_entry_state_at_entries=no_entry_state,
        direction_recall_by_lookback_pct={
            f"{minutes}m": (100.0 * values[0] / total) if total else 0.0
            for minutes, values in by_window.items()
        },
        range_only_entries_by_lookback={
            f"{minutes}m": values[1] for minutes, values in by_window.items()
        },
    )


def _window_alignment(
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
    minutes: int,
) -> tuple[int, int]:
    """Original per-position loop, kept for indexes the fast path cannot use."""
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
    entries = _prepare_entries(positions, cluster_seconds=decision_cluster_seconds)
    prepared = _prepare_decisions(decisions, bar_duration)
    if prepared is not None:
        return _entry_alignment_report(prepared, entries, lookback_minutes)
    return _loop_entry_alignment(decisions, entries, lookback_minutes, bar_duration)


def _loop_entry_alignment(
    decisions: pd.DataFrame,
    entries: _PreparedEntries,
    lookback_minutes: tuple[int, ...],
    bar_duration: pd.Timedelta,
) -> EntryAlignmentReport:
    """Original implementation; raises where it always did on bad indexes."""
    unique = entries.unique
    available = _available_decisions(decisions, bar_duration)
    aligned = available.reindex(pd.DatetimeIndex(unique["event_time"]), method="ffill")
    predicted = _decision_directions(aligned).to_numpy()
    primary = aligned["primary_regime"]
    by_window = {
        minutes: _window_alignment(available, unique, minutes)
        for minutes in lookback_minutes
    }
    return _alignment_report(
        entries.recorded_positions,
        len(unique),
        int((predicted == entries.sides).sum()),
        int(primary.eq(PrimaryRegime.RANGE.value).sum()),
        int(pd.isna(predicted).sum()),
        by_window,
    )


def _future_extreme(series: pd.Series, horizon: int, kind: str) -> pd.Series:
    """Extreme of the next ``horizon`` values (NaN if any is missing).

    A reversed rolling window equals the former concat-of-shifts reduction
    with ``skipna=False`` exactly, in O(n) instead of O(n * horizon).
    """
    if horizon < 1:
        raise ValueError("forward_horizon must be positive")
    window = series.iloc[::-1].rolling(horizon, min_periods=horizon)
    extreme = window.max() if kind == "max" else window.min()
    return extreme.iloc[::-1].shift(-1).rename(None)


def _future_extremes(
    bars: pd.DataFrame,
    forward_horizon: int,
    future_high: pd.Series | None,
    future_low: pd.Series | None,
) -> tuple[pd.Series, pd.Series]:
    if future_high is None:
        future_high = _future_extreme(bars["high"].astype(float), forward_horizon, "max")
    if future_low is None:
        future_low = _future_extreme(bars["low"].astype(float), forward_horizon, "min")
    return future_high, future_low


def evaluate_breakout_quality(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    target_price_fraction: float,
    forward_horizon: int,
    future_high: pd.Series | None = None,
    future_low: pd.Series | None = None,
) -> BreakoutQualityReport:
    """Report breakouts that fail to reach their directional target.

    ``future_high``/``future_low`` may be precomputed for these exact ``bars``
    and ``forward_horizon`` (they depend on nothing else).
    """
    future_high, future_low = _future_extremes(
        bars, forward_horizon, future_high, future_low
    )
    close = bars["close"].astype(float)
    direction = decisions["breakout_direction"]
    directional = direction.isin(
        [BreakoutDirection.UPWARD.value, BreakoutDirection.DOWNWARD.value]
    )
    breakout = (
        decisions["primary_regime"].eq(PrimaryRegime.BREAKOUT.value) & directional
    )
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
    future_high: pd.Series | None = None,
    future_low: pd.Series | None = None,
) -> RangeQualityReport:
    """Classify forward outcomes after range states without gating execution."""
    future_high, future_low = _future_extremes(
        bars, forward_horizon, future_high, future_low
    )
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
    context = _completed_context(
        bars,
        bars.index,
        30,
        RegimeClassifierConfig(),
    )
    return context["primary_regime"]


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


def _aligned_position_rows(
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> pd.DataFrame:
    available = _available_decisions(decisions, pd.Timedelta(minutes=1))
    aligned = available.reindex(_position_times(positions), method="ffill")
    result = positions.reset_index(drop=True).copy()
    result["primary_regime"] = aligned["primary_regime"].to_numpy()
    result["predicted_direction"] = _decision_directions(aligned).to_numpy()
    return result


def _position_regime_performance(
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> dict[str, object]:
    if "net_margin_pnl_pct" not in positions.columns:
        return {"status": "unavailable", "reason": "net_margin_pnl_pct not reported"}
    reconciled = reconcile_source_position_records(positions)
    aligned = _aligned_position_rows(decisions, reconciled)
    aligned["net_margin_pnl_pct"] = pd.to_numeric(
        aligned["net_margin_pnl_pct"], errors="raise"
    )
    aligned["direction_match"] = aligned["predicted_direction"].eq(
        aligned["side"].astype(str).str.lower()
    )
    return {
        "status": "completed",
        "annotation_only": True,
        "states": {
            str(state): _position_group_metrics(group)
            for state, group in aligned.groupby("primary_regime", dropna=False)
        },
    }


def _position_group_metrics(group: pd.DataFrame) -> dict[str, object]:
    returns = group["net_margin_pnl_pct"].astype(float)
    return {
        "positions": len(group),
        "mean_net_margin_pnl_pct": float(returns.mean()),
        "median_net_margin_pnl_pct": float(returns.median()),
        "win_rate_pct": float((returns > 0.0).mean() * 100.0),
        "direction_match_pct": float(group["direction_match"].mean() * 100.0),
    }


def _cost_sensitivity(positions: pd.DataFrame) -> dict[str, object]:
    required = {"net_margin_pnl_pct", "fees_usd", "approx_margin_usd", "leverage"}
    missing = required.difference(positions.columns)
    if missing:
        return {"status": "unavailable", "missing_columns": sorted(missing)}
    reconciled = reconcile_source_position_records(positions)
    frame = reconciled.loc[:, sorted(required)].apply(pd.to_numeric, errors="raise")
    if (frame["approx_margin_usd"] <= 0.0).any():
        raise ValueError("approx_margin_usd must be positive for cost sensitivity")
    fee_drag = frame["fees_usd"] / frame["approx_margin_usd"] * 100.0
    gross = frame["net_margin_pnl_pct"] + fee_drag
    scenarios = {
        "maker_1_5bps_per_side": 0.00030,
        "taker_4_5bps_per_side": 0.00090,
        "maker_plus_1bps_slippage_per_side": 0.00050,
    }
    return {
        "status": "completed",
        "basis": "gross reconstructed from reported net plus reported fees",
        "funding": "unchanged from recorded position outcome",
        "scenarios": {
            name: _cost_scenario(gross, frame["leverage"], rate)
            for name, rate in scenarios.items()
        },
    }


def _cost_scenario(
    gross_margin_pct: pd.Series,
    leverage: pd.Series,
    roundtrip_notional_rate: float,
) -> dict[str, object]:
    adjusted = gross_margin_pct - roundtrip_notional_rate * leverage * 100.0
    return {
        "roundtrip_notional_rate": roundtrip_notional_rate,
        "mean_net_margin_pnl_pct": float(adjusted.mean()),
        "median_net_margin_pnl_pct": float(adjusted.median()),
        "win_rate_pct": float((adjusted > 0.0).mean() * 100.0),
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
    decisions = classify_multitimeframe(
        indexed,
        config=config or faithful_regime_config(),
    )
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
        source_limited=not sources or any(source != "hl" for source in sources),
        context_direction_recall_pct=_context_recalls(indexed, decisions, positions),
        position_regime_performance=_position_regime_performance(
            decisions,
            positions,
        ),
        cost_sensitivity=_cost_sensitivity(positions),
    )
