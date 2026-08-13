"""Authentic funding and official-candle checks for HIP-3 transfer research."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

_OHLC = ("open", "high", "low", "close")
_FUNDING_SOURCE = "hl_funding_history"


@dataclass(frozen=True)
class MetricQuantiles:
    """Finite count plus selected empirical quantiles."""

    count: int
    p50: float | None
    p90: float | None
    p99: float | None


@dataclass(frozen=True)
class FundingAttachmentEvidence:
    """Coverage and timing evidence for attached official settlements."""

    funding_events: int
    first_funding_utc: str
    last_funding_utc: str
    assigned_event_count: int
    pre_window_event_count: int
    post_window_event_count: int
    delayed_event_count: int
    maximum_assignment_delay_seconds: float
    unassigned_event_count: int
    source: str = _FUNDING_SOURCE


@dataclass(frozen=True)
class MidpointProxyValidation:
    """Comparison between L2 midpoint bars and retained official candles."""

    proxy_bars: int
    official_bars: int
    matched_bars: int
    absolute_error_bps: dict[str, MetricQuantiles]
    return_correlation: float | None
    direction_agreement: float | None
    execution_authority: str = "none"


def attach_official_funding(
    bars: pd.DataFrame,
    funding: pd.DataFrame,
) -> tuple[pd.DataFrame, FundingAttachmentEvidence]:
    """Attach each authentic settlement to its first observable strategy bar."""
    strategy = _validated_bars(bars)
    events = _validated_funding(funding)
    first_bar = strategy.index.min()
    last_bar = strategy.index.max()
    _require_internal_hourly_coverage(events.index)
    pre_window = int((events.index < first_bar).sum())
    post_window = int((events.index > last_bar).sum())
    assignable = events.loc[(events.index >= first_bar) & (events.index <= last_bar)]
    output = strategy.copy()
    output["funding_rate"] = 0.0
    positions = output.index.searchsorted(assignable.index, side="left")
    delayed = 0
    maximum_delay = 0.0
    for event_position, bar_position in enumerate(positions):
        event_time = assignable.index[event_position]
        bar_time = output.index[int(bar_position)]
        delay = (bar_time - event_time).total_seconds()
        delayed += int(delay > 0.0)
        maximum_delay = max(maximum_delay, delay)
        column = output.columns.get_loc("funding_rate")
        output.iat[int(bar_position), column] += float(assignable.iloc[event_position])
    evidence = FundingAttachmentEvidence(
        funding_events=len(events),
        first_funding_utc=events.index.min().isoformat(),
        last_funding_utc=events.index.max().isoformat(),
        assigned_event_count=len(assignable),
        pre_window_event_count=pre_window,
        post_window_event_count=post_window,
        delayed_event_count=delayed,
        maximum_assignment_delay_seconds=maximum_delay,
        unassigned_event_count=pre_window + post_window,
    )
    return output, evidence


def compare_midpoint_proxy_to_official(
    proxy_bars: pd.DataFrame,
    official_candles: pd.DataFrame,
) -> MidpointProxyValidation:
    """Measure exact-timestamp midpoint-proxy error against official candles."""
    proxy = _validated_bars(proxy_bars).loc[:, list(_OHLC)].copy()
    official = _official_bars(official_candles)
    merged = proxy.join(official, how="inner", lsuffix="_proxy", rsuffix="_official")
    if len(merged) < 2:
        raise ValueError("proxy validation requires at least two matched bars")
    errors = {
        column: _quantiles(
            (merged[f"{column}_proxy"] / merged[f"{column}_official"] - 1.0).abs()
            * 10_000.0
        )
        for column in _OHLC
    }
    proxy_returns = merged["close_proxy"].pct_change().dropna()
    official_returns = merged["close_official"].pct_change().dropna()
    correlation = _correlation(proxy_returns, official_returns)
    agreement = float(
        (
            np.sign(proxy_returns.to_numpy(float))
            == np.sign(official_returns.to_numpy(float))
        ).mean()
    )
    return MidpointProxyValidation(
        proxy_bars=len(proxy),
        official_bars=len(official),
        matched_bars=len(merged),
        absolute_error_bps=errors,
        return_correlation=correlation,
        direction_agreement=agreement,
    )


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(_OHLC).difference(bars.columns))
    if missing:
        raise ValueError(f"HIP-3 strategy bars missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("HIP-3 strategy bars require a timezone-aware index")
    if bars.empty or not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("HIP-3 strategy bars require ordered unique rows")
    values = bars.loc[:, list(_OHLC)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("HIP-3 strategy OHLC must be finite and positive")
    return bars.copy()


def _validated_funding(funding: pd.DataFrame) -> pd.Series:
    required = {"timestamp", "funding_rate", "source"}
    missing = sorted(required.difference(funding.columns))
    if missing:
        raise ValueError(f"official funding missing columns: {missing}")
    frame = funding.loc[:, ["timestamp", "funding_rate", "source"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["funding_rate"] = pd.to_numeric(frame["funding_rate"], errors="raise")
    if frame.empty or not frame["funding_rate"].map(isfinite).all():
        raise ValueError("official funding must contain finite rows")
    if not frame["source"].eq(_FUNDING_SOURCE).all():
        raise ValueError("official funding source identity is invalid")
    if not frame["timestamp"].dt.floor("h").equals(frame["timestamp"]):
        raise ValueError("official funding timestamps must align to UTC hours")
    conflicts = frame.groupby("timestamp")["funding_rate"].nunique().gt(1)
    if bool(conflicts.any()):
        raise ValueError("official funding contains conflicting duplicate rows")
    output = frame.drop_duplicates("timestamp").sort_values("timestamp")
    return output.set_index("timestamp")["funding_rate"].astype(float)


def _require_internal_hourly_coverage(index: pd.DatetimeIndex) -> None:
    expected = pd.date_range(index.min(), index.max(), freq="h")
    missing = expected.difference(index)
    if len(missing):
        raise ValueError(
            f"official funding missing {len(missing)} internal hourly rows"
        )


def _official_bars(candles: pd.DataFrame) -> pd.DataFrame:
    frame = candles.copy()
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.set_index("timestamp")
    return _validated_bars(frame).loc[:, list(_OHLC)]


def _quantiles(values: pd.Series) -> MetricQuantiles:
    finite = values[np.isfinite(values.to_numpy(float))]
    if finite.empty:
        return MetricQuantiles(0, None, None, None)
    return MetricQuantiles(
        len(finite),
        float(finite.quantile(0.50)),
        float(finite.quantile(0.90)),
        float(finite.quantile(0.99)),
    )


def _correlation(left: pd.Series, right: pd.Series) -> float | None:
    if len(left) < 2 or left.nunique() < 2 or right.nunique() < 2:
        return None
    value = float(left.corr(right))
    return value if isfinite(value) else None
