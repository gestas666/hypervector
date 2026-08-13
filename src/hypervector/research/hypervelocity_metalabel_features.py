"""Shared causal feature construction for Hypervelocity metalabel research."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from hypervector.data.oxa_archive_audit import (
    OxaArchiveAuditConfig,
    verified_archive_bundles,
)
from hypervector.regime.composite import _completed_context, classify_multitimeframe
from hypervector.research.hypervelocity_attribution import (
    align_book_pressure,
    build_bar_annotations,
)
from hypervector.research.hypervelocity_attribution_io import (
    load_signal_book_pressure,
)
from hypervector.research.hypervelocity_bbwp_precedence import (
    apply_1m_bbwp_recovery_delay,
    apply_1m_trend_breakout_confirmation,
    apply_5m_bbwp_range_precedence,
)
from hypervector.research.hypervelocity_book_sequence import align_book_sequence
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile

DecisionProfile = Literal["recovery6", "canonical", "faithful"]


def load_model_bars(
    path: Path,
    start: datetime,
    end: datetime,
    *,
    include_prior: bool = False,
) -> pd.DataFrame:
    """Load ordered uninterrupted one-minute bars for causal feature generation."""
    if not path.is_file():
        raise FileNotFoundError(f"Hyperliquid model bars are missing: {path}")
    bars = pd.read_parquet(path)
    if "timestamp" not in bars:
        raise ValueError("Hyperliquid model bars require timestamp")
    bars.index = pd.DatetimeIndex(pd.to_datetime(bars["timestamp"], utc=True))
    lower_bound = (
        pd.Series(True, index=bars.index) if include_prior else bars.index >= start
    )
    bars = bars.loc[lower_bound & (bars.index < end)].copy()
    if (
        bars.empty
        or bars.index.has_duplicates
        or not bars.index.is_monotonic_increasing
    ):
        raise ValueError(
            "Hyperliquid model bars must be ordered, unique, and non-empty"
        )
    cadence = bars.index.to_series().diff().iloc[1:]
    if not cadence.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError(
            "Hyperliquid model bars require uninterrupted one-minute cadence"
        )
    return bars


def candidate_feature_frames(
    bars: pd.DataFrame,
    config_path: Path,
    decision_profile: DecisionProfile,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build completed-bar decision, 5m context, and annotation features."""
    decisions, context_5m, regime_config = candidate_decisions(
        bars, config_path, decision_profile
    )
    annotations = build_bar_annotations(
        bars,
        decisions,
        structure_lookback=regime_config.structure_lookback,
        compression_threshold=regime_config.bbwp_compression_threshold,
    )
    return decisions, context_5m, annotations


def candidate_decisions(
    bars: pd.DataFrame,
    config_path: Path,
    decision_profile: DecisionProfile,
) -> tuple[pd.DataFrame, pd.DataFrame, object]:
    """Build causal decisions and completed 5m context for one frozen profile."""
    profile = load_hypervelocity_profile(config_path)
    decisions = classify_multitimeframe(bars, config=profile.regime_config)
    context_5m = _completed_context(bars, bars.index, 5, profile.regime_config)
    threshold = profile.regime_config.bbwp_compression_threshold
    if decision_profile == "faithful":
        decisions = apply_1m_bbwp_recovery_delay(
            decisions,
            threshold=threshold,
            minimum_age_bars=0,
        )
    elif decision_profile == "canonical":
        decisions = apply_1m_trend_breakout_confirmation(decisions)
        decisions = apply_1m_bbwp_recovery_delay(
            decisions,
            threshold=threshold,
            minimum_age_bars=0,
        )
    else:
        decisions = apply_5m_bbwp_range_precedence(
            decisions,
            context_5m,
            threshold=threshold,
        )
        decisions = apply_1m_bbwp_recovery_delay(
            decisions,
            threshold=threshold,
            minimum_age_bars=6,
        )
    return decisions, context_5m, profile.regime_config


def signal_book_features(
    data_root: Path,
    start: datetime,
    end: datetime,
    signal_times: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Build static and true causal L2 sequence features for exact signals."""
    bundles = verified_archive_bundles(
        OxaArchiveAuditConfig("BTC", start, end, data_root)
    )
    pressure = load_signal_book_pressure(bundles, signal_times)
    static = align_book_pressure(signal_times, pressure)
    sequence = align_book_sequence(signal_times, pressure)
    return static.join(sequence, validate="one_to_one")
