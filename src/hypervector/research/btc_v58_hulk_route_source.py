"""Reconstruct exact report-only V58 BTC Hulk short route events."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.research.backtest_lab_cipher_adapter import (
    compute_market_cipher_signal_components,
    inspect_backtest_lab_sources,
)
from hypervector.research.btc_trend_pullback_route_competition import BtcRouteEvent
from hypervector.research.hulk_smash_candidates import (
    select_hulk_expansion_moderate_adx,
)
from hypervector.research.hulk_smash_quality import build_hulk_quality_frame
from hypervector.research.hulk_smash_rebuilt_signals import (
    RebuiltHulkConfig,
    evaluate_rebuilt_hulk_signals,
)
from hypervector.research.market_cipher_strategy_research import (
    HulkResearchProfile,
    resolve_hulk_research_profile,
)


ComponentBuilder = Callable[..., pd.DataFrame]
QualityBuilder = Callable[..., pd.DataFrame]
SignalBuilder = Callable[..., pd.DataFrame]
_PROFILE_PRIORITY = {
    "hulk_expansion_short_robust_v3": 20,
    "hulk_expansion_short_tuned_v2": 19,
}
_SIGNAL_BAR = pd.Timedelta(minutes=30)
_MINUTE = pd.Timedelta(minutes=1)


@dataclass(frozen=True)
class BtcHulkRouteSource:
    """Exact route events and their source/profile identity."""

    events: tuple[BtcRouteEvent, ...]
    source_identity: dict[str, object]


def build_v58_hulk_short_events(
    minute_bars: pd.DataFrame,
    backtest_lab_root: Path,
    strategy_id: str,
    *,
    component_builder: ComponentBuilder = compute_market_cipher_signal_components,
    quality_builder: QualityBuilder = build_hulk_quality_frame,
    signal_builder: SignalBuilder = evaluate_rebuilt_hulk_signals,
    inspect_source: bool = True,
) -> BtcHulkRouteSource:
    """Build the frozen completed-30m short route without live imports."""
    priority = _profile_priority(strategy_id)
    profile = resolve_hulk_research_profile(strategy_id)
    strategy = _completed_thirty_minute_bars(minute_bars)
    indexed = strategy.set_index("bar_open_at")
    components = component_builder(strategy, backtest_lab_root, bar_minutes=30)
    quality = quality_builder(
        indexed,
        supertrend_period=profile.supertrend_period,
        supertrend_multiplier=profile.supertrend_multiplier,
        adx_period=profile.adx_period,
        squeeze_period=profile.squeeze_period,
    )
    signals = signal_builder(indexed, components, quality, _signal_config(profile))
    selected = select_hulk_expansion_moderate_adx(signals)
    selected = selected.loc[selected["side"].eq("short")].copy()
    events = tuple(
        BtcRouteEvent.structural(
            strategy_id,
            priority,
            pd.Timestamp(row.signal_time_utc) + _SIGNAL_BAR - _MINUTE,
            float(row.stop_anchor),
        )
        for row in selected.itertuples(index=False)
    )
    identity: dict[str, object] = {
        "strategy_id": strategy_id,
        "profile": asdict(profile),
        "bar_minutes": 30,
        "execution_authority": "none",
        "live_module_imported": False,
        "signal_count": len(events),
    }
    if inspect_source:
        identity["backtest_lab"] = inspect_backtest_lab_sources(backtest_lab_root)
    else:
        identity["backtest_lab"] = {"inspection_skipped_for_injected_test": True}
    return BtcHulkRouteSource(events, identity)


def _completed_thirty_minute_bars(minute_bars: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(minute_bars.columns))
    if missing:
        raise ValueError(f"BTC Hulk minute bars missing columns: {missing}")
    if not isinstance(minute_bars.index, pd.DatetimeIndex):
        raise ValueError("BTC Hulk minute bars require a datetime index")
    index = minute_bars.index
    if index.tz is None or not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("BTC Hulk minute bars must be aware, ordered, and unique")
    values = minute_bars[list(required)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("BTC Hulk minute bars must be finite")
    grouped = minute_bars.resample("30min", label="left", closed="left")
    output = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        constituent_bars=("close", "count"),
    )
    complete = output["constituent_bars"].eq(30)
    selected = output.loc[complete].drop(columns="constituent_bars")
    if selected.empty:
        raise ValueError("BTC Hulk source has no complete 30-minute bars")
    return selected.rename_axis("bar_open_at").reset_index()


def _signal_config(profile: HulkResearchProfile) -> RebuiltHulkConfig:
    return RebuiltHulkConfig(
        minimum_score=profile.minimum_score,
        pivot_bars=profile.pivot_bars,
        adx_usable=profile.adx_usable,
        adx_trending=profile.adx_trending,
    )


def _profile_priority(strategy_id: str) -> int:
    if strategy_id not in _PROFILE_PRIORITY:
        raise ValueError(f"unsupported V58 BTC Hulk route: {strategy_id}")
    return _PROFILE_PRIORITY[strategy_id]
