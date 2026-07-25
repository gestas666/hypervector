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

    total_entries: int
    direction_matches: int
    direction_recall_pct: float
    false_range_at_entries: int
    no_entry_state_at_entries: int


@dataclass(frozen=True)
class BreakoutQualityReport:
    """Directional target follow-through for confirmed breakout events."""

    breakout_events: int
    false_breakouts: int
    false_breakout_pct: float


@dataclass(frozen=True)
class HypervelocityRegimeReport:
    """Complete report-only result for one causal regime candidate."""

    total_bars: int
    entry_alignment: EntryAlignmentReport
    breakout_quality: BreakoutQualityReport
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


def _decision_directions(rows: pd.DataFrame) -> pd.Series:
    directions = pd.Series(None, index=rows.index, dtype=object)
    directions = directions.mask(rows["primary_regime"].eq(PrimaryRegime.TREND_UP.value), "long")
    directions = directions.mask(rows["primary_regime"].eq(PrimaryRegime.TREND_DOWN.value), "short")
    is_breakout = rows["primary_regime"].eq(PrimaryRegime.BREAKOUT.value)
    directions = directions.mask(
        is_breakout & rows["breakout_direction"].eq(BreakoutDirection.UPWARD.value), "long"
    )
    return directions.mask(
        is_breakout & rows["breakout_direction"].eq(BreakoutDirection.DOWNWARD.value), "short"
    )


def evaluate_entry_alignment(
    decisions: pd.DataFrame,
    positions: pd.DataFrame,
) -> EntryAlignmentReport:
    """Measure whether candidate states recover recorded entry directions."""
    times = _position_times(positions)
    unique = positions.assign(_time=times).drop_duplicates(["_time", "side"])
    aligned = decisions.reindex(pd.DatetimeIndex(unique["_time"]), method="ffill")
    wanted = unique["side"].astype(str).str.lower().to_numpy()
    predicted = _decision_directions(aligned).to_numpy()
    primary = aligned["primary_regime"]
    matches = int((predicted == wanted).sum())
    total = len(unique)
    return EntryAlignmentReport(
        total_entries=total,
        direction_matches=matches,
        direction_recall_pct=(100.0 * matches / total) if total else 0.0,
        false_range_at_entries=int(primary.eq(PrimaryRegime.RANGE.value).sum()),
        no_entry_state_at_entries=int(pd.isna(predicted).sum()),
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
    valid = breakout & future_high.notna() & future_low.notna()
    upward = decisions["breakout_direction"].eq(BreakoutDirection.UPWARD.value)
    downward = decisions["breakout_direction"].eq(BreakoutDirection.DOWNWARD.value)
    success = (upward & (future_high >= close * (1.0 + target_price_fraction))) | (
        downward & (future_low <= close * (1.0 - target_price_fraction))
    )
    count = int(valid.sum())
    failures = int((valid & ~success).sum())
    return BreakoutQualityReport(
        breakout_events=count,
        false_breakouts=failures,
        false_breakout_pct=(100.0 * failures / count) if count else 0.0,
    )


def _mean_transition_latency(decisions: pd.DataFrame) -> float:
    primary = decisions["primary_regime"].astype(str)
    state_1m = decisions["state_1m"].astype(str)
    changes = [i for i in range(1, len(primary)) if primary.iloc[i] != primary.iloc[i - 1]]
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
    aggregated = bars.resample("30min", label="right", closed="right").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna()
    classified = classify_timeframe(aggregated, RegimeClassifierConfig()).shift(1)
    return classified["primary_regime"].reindex(bars.index, method="ffill").fillna(
        PrimaryRegime.UNKNOWN.value
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
) -> HypervelocityRegimeReport:
    """Evaluate canonical regimes without accepting or rejecting a trial."""
    indexed = _datetime_bars(bars)
    decisions = classify_multitimeframe(indexed)
    alignment = evaluate_entry_alignment(decisions, positions)
    breakout = evaluate_breakout_quality(
        indexed,
        decisions,
        target_price_fraction=target_price_fraction,
        forward_horizon=forward_horizon,
    )
    primary = decisions["primary_regime"].astype(str)
    sources = tuple(sorted(indexed.get("source", pd.Series(dtype=str)).astype(str).unique()))
    return HypervelocityRegimeReport(
        total_bars=len(indexed),
        entry_alignment=alignment,
        breakout_quality=breakout,
        state_distribution={str(key): int(value) for key, value in primary.value_counts().items()},
        label_churn=int(primary.ne(primary.shift()).sum() - (1 if len(primary) else 0)),
        mean_transition_latency_bars=_mean_transition_latency(decisions),
        bar_sources=sources,
        source_limited=sources != ("bitget",),
        context_direction_recall_pct=_context_recalls(indexed, decisions, positions),
    )
