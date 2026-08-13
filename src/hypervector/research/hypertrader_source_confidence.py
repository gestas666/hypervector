"""Report-only source-confidence challengers for Hypertrader replays."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hypertrader_source_adapter import (
    extract_source_follow_all_day_events,
)

MINIMUM_SOURCE_CONFIDENCE = 0.70


def _minimum_confidence(events: pd.DataFrame, recipe_id: str) -> pd.DataFrame:
    confidence = pd.to_numeric(events["confidence"], errors="raise")
    selected = events.loc[confidence.ge(MINIMUM_SOURCE_CONFIDENCE)].copy()
    selected["recipe_id"] = recipe_id
    return selected.reset_index(drop=True)


def extract_source_follow_all_day_confidence_70_events(
    labels: pd.DataFrame,
) -> pd.DataFrame:
    """Retain all-day TREND_DOWN onsets with confidence at least 0.70."""
    return _minimum_confidence(
        extract_source_follow_all_day_events(labels),
        "follow_td_all_day_conf70",
    )


def _session_confidence_events(
    labels: pd.DataFrame,
    *,
    start_hour: int,
    end_hour: int,
    recipe_id: str,
) -> pd.DataFrame:
    events = extract_source_follow_all_day_confidence_70_events(labels)
    hours = pd.to_datetime(events["label_time_utc"], utc=True).dt.hour
    selected = events.loc[hours.ge(start_hour) & hours.lt(end_hour)].copy()
    selected["recipe_id"] = recipe_id
    return selected.reset_index(drop=True)


def extract_source_follow_session_05_14_confidence_70_events(
    labels: pd.DataFrame,
) -> pd.DataFrame:
    """Retain confidence-qualified TREND_DOWN onsets from 05:00-14:00 UTC."""
    return _session_confidence_events(
        labels,
        start_hour=5,
        end_hour=14,
        recipe_id="follow_td_session_05_14_conf70",
    )


def extract_source_follow_session_06_15_confidence_70_events(
    labels: pd.DataFrame,
) -> pd.DataFrame:
    """Retain early-session TREND_DOWN onsets with confidence at least 0.70."""
    return _session_confidence_events(
        labels,
        start_hour=6,
        end_hour=15,
        recipe_id="follow_td_session_06_15_conf70",
    )


def extract_source_follow_session_07_16_confidence_70_events(
    labels: pd.DataFrame,
) -> pd.DataFrame:
    """Retain confidence-qualified TREND_DOWN onsets from 07:00-16:00 UTC."""
    return _session_confidence_events(
        labels,
        start_hour=7,
        end_hour=16,
        recipe_id="follow_td_session_07_16_conf70",
    )


def extract_source_follow_session_08_17_confidence_70_events(
    labels: pd.DataFrame,
) -> pd.DataFrame:
    """Retain confidence-qualified TREND_DOWN onsets from 08:00-17:00 UTC."""
    return _session_confidence_events(
        labels,
        start_hour=8,
        end_hour=17,
        recipe_id="follow_td_session_08_17_conf70",
    )
