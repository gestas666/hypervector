"""Pinned-source helpers for the Hypertrader v2 BTC selective recipe."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

PINNED_HYPERTRADER_REVISION = "ad15f2bdc949619be495a5f516babd08f7f52a90"
LEGACY_HYPERTRADER_REVISION = "96014462c8f3911abff1babc925448893d65676d"
PINNED_SOURCE_HASHES: Mapping[str, str] = {
    "app/services/indicators.py": (
        "c4ce23922243b32b0665edd97e4596f140add6aa173eb50301ea6abe12c5718c"
    ),
    "app/services/regime/classif_dry_run.py": (
        "f38bd8ddadd6cc29f26ce48ec837d081d6dbbce98d4cdbd3c677ed4f01fba995"
    ),
    "app/services/regime/__init__.py": (
        "ae4137f0f297b0608dc11896f1e966e9415f1ae390383eed53894a957b098e29"
    ),
    "app/services/regime/classifier.py": (
        "af9b5460373e4acb89ce526fe955a96901e154b9b7dc13d0790bf501e72966b0"
    ),
    "app/services/regime/config.py": (
        "06ab349cd7e386c8bce2f8d3bd5ddc9d1434c6e50228aa55433d03c9c6a03805"
    ),
    "app/services/regime/indicators.py": (
        "82f26ed7284b30aa0f0f7853b6432e4b6f9bdc707f0c10dc21cfe4a27e1e805e"
    ),
    "app/services/regime/models.py": (
        "c3c7db47ba16aaf9f4ffd760a75efba066d13972c62b7a22bc65908340c18dd9"
    ),
    "app/services/regime/state.py": (
        "520ec442bb1e4b6017ed6f1c6306bb8af8cb1ed732e14be6258e342c55425797"
    ),
    "scripts/run_classif_dry_run_backtest.py": (
        "bbaa5ea153a6f9658f3b050cb55d4fce1106be3e55701d1886eaa406a648f1f5"
    ),
}
LEGACY_SOURCE_HASHES: Mapping[str, str] = {
    "app/services/regime/classifier.py": (
        "1a763f3a5a79b8bc13d0e52e5255da97ffca16f5380decf9b8c6a0c8c5924e22"
    ),
    "app/services/regime/config.py": (
        "1e115a1e006772942eb164bcef321dd645654e4e64146d2a2c8b391b6b87d32b"
    ),
    "app/services/regime/indicators.py": (
        "68cbf704210a31b704e0e4e0cf8e65799b58cba40ea67b6ca0203e691702b62e"
    ),
    "app/services/regime/models.py": (
        "c3c7db47ba16aaf9f4ffd760a75efba066d13972c62b7a22bc65908340c18dd9"
    ),
    "app/services/regime/state.py": (
        "edf50aa4a55cb13b7a1bda1afb48c816de7cfde19d7ba25a8e32dc1653b915f1"
    ),
    "app/services/regime/storage_lite.py": (
        "e591d1175a3ea39dc2b85d7f0506387f337d9cf8158e11c9cfd2ae78f8c4adc6"
    ),
}
SOURCE_HASHES_BY_REVISION: Mapping[str, Mapping[str, str]] = {
    PINNED_HYPERTRADER_REVISION: PINNED_SOURCE_HASHES,
    LEGACY_HYPERTRADER_REVISION: LEGACY_SOURCE_HASHES,
}

_CANDLE_COLUMNS = ("open", "high", "low", "close", "volume")
_LABEL_COLUMNS = {"primary_code", "secondary_code", "confidence"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source_files(
    backend_root: Path,
    *,
    expected_hashes: Mapping[str, str] = PINNED_SOURCE_HASHES,
    revision: str = PINNED_HYPERTRADER_REVISION,
) -> dict[str, object]:
    """Fail unless every classifier dependency matches the pinned revision."""
    observed: dict[str, str] = {}
    for relative, expected in expected_hashes.items():
        path = backend_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"pinned Hypertrader source is missing: {path}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(
                "Hypertrader source checksum mismatch: "
                f"{relative} expected={expected} actual={actual}"
            )
        observed[relative] = actual
    return {"revision": revision, "files": observed}


def source_hashes_for_revision(revision: str) -> Mapping[str, str]:
    """Return the immutable source boundary for one supported revision."""
    try:
        return SOURCE_HASHES_BY_REVISION[revision]
    except KeyError as exc:
        raise ValueError(
            f"unsupported Hypertrader source revision: {revision}"
        ) from exc


def _validate_datetime_index(frame: pd.DataFrame, label: str) -> None:
    index = frame.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError(f"{label} require a timezone-aware DatetimeIndex")
    if not index.is_monotonic_increasing or not index.is_unique:
        raise ValueError(f"{label} timestamps must be ordered and unique")


def _validate_completed_five_minute_bars(bars: pd.DataFrame) -> None:
    _validate_datetime_index(bars, "five-minute signal bars")
    index = bars.index.tz_convert("UTC")
    misaligned = (
        (index.minute % 5 != 0)
        | (index.second != 0)
        | (index.microsecond != 0)
        | (index.nanosecond != 0)
    )
    if misaligned.any():
        raise ValueError("signal range requires completed five-minute bars")


def load_hyperliquid_candles(paths: Sequence[Path]) -> pd.DataFrame:
    """Load immutable one-minute candle files with uninterrupted UTC cadence."""
    combined = _load_hyperliquid_candle_rows(paths)
    cadence = combined.index.to_series().diff().iloc[1:]
    if not cadence.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("Hyperliquid candles require uninterrupted one-minute cadence")
    return combined


def load_hyperliquid_candle_segments(
    paths: Sequence[Path],
) -> tuple[pd.DataFrame, ...]:
    """Load native candles as complete, five-minute-aligned cadence segments."""
    combined = _load_hyperliquid_candle_rows(paths)
    boundaries = combined.index.to_series().diff().ne(pd.Timedelta(minutes=1))
    groups = boundaries.cumsum()
    segments = tuple(
        aligned
        for _, frame in combined.groupby(groups)
        if not (aligned := _complete_five_minute_slice(frame)).empty
    )
    if not segments:
        raise ValueError("Hyperliquid candles contain no complete five-minute segment")
    return segments


def _load_hyperliquid_candle_rows(paths: Sequence[Path]) -> pd.DataFrame:
    """Load and validate ordered venue candle rows without assuming cadence."""
    if not paths:
        raise ValueError("at least one Hyperliquid candle file is required")
    frames: list[pd.DataFrame] = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"Hyperliquid candle file is missing: {path}")
        frame = pd.read_parquet(path)
        required = {"timestamp", *_CANDLE_COLUMNS}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Hyperliquid candles missing: {sorted(missing)}")
        source = frame.get("source")
        if source is not None and not source.astype(str).str.startswith("hl").all():
            raise ValueError(f"non-Hyperliquid candle source in {path}")
        selected = frame.loc[:, list(_CANDLE_COLUMNS)].astype(float)
        selected.index = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
        frames.append(selected)
    combined = pd.concat(frames).sort_index(kind="stable")
    _validate_datetime_index(combined, "Hyperliquid candles")
    if combined.empty:
        raise ValueError("Hyperliquid candles must not be empty")
    return combined


def _complete_five_minute_slice(frame: pd.DataFrame) -> pd.DataFrame:
    """Trim one continuous minute run to full UTC five-minute groups."""
    start = frame.index[0].ceil("5min")
    end = (frame.index[-1] + pd.Timedelta(minutes=1)).floor("5min")
    if end <= start:
        return frame.iloc[0:0]
    return frame.loc[(frame.index >= start) & (frame.index < end)]


def resample_hyperliquid_5m(candles: pd.DataFrame) -> pd.DataFrame:
    """Aggregate completed one-minute candles into left-labeled five-minute bars."""
    _validate_datetime_index(candles, "Hyperliquid candles")
    missing = set(_CANDLE_COLUMNS).difference(candles.columns)
    if missing:
        raise ValueError(f"Hyperliquid candles missing: {sorted(missing)}")
    if candles.empty or candles.index[0].minute % 5 != 0 or len(candles) % 5:
        raise ValueError("Hyperliquid candles must contain complete five-minute groups")
    cadence = candles.index.to_series().diff().iloc[1:]
    if not cadence.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("Hyperliquid candles require uninterrupted one-minute cadence")
    bars = candles.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    if bars.isna().any(axis=None):
        raise ValueError("five-minute resampling produced incomplete bars")
    return bars.loc[:, list(_CANDLE_COLUMNS)].astype(float)


def _primary_onsets(labels: pd.DataFrame) -> pd.Series:
    primary = labels["primary_code"].fillna("UNKNOWN").astype(str).str.upper()
    return primary.ne(primary.shift(1))


def extract_selective_recipe_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Extract exact source B/C onsets and expose causal decision availability."""
    _validate_datetime_index(labels, "Hypertrader labels")
    missing = _LABEL_COLUMNS.difference(labels.columns)
    if missing:
        raise ValueError(f"Hypertrader labels missing: {sorted(missing)}")
    primary = labels["primary_code"].fillna("UNKNOWN").astype(str).str.upper()
    secondary = labels["secondary_code"].fillna("").astype(str).str.upper()
    confidence = pd.to_numeric(labels["confidence"], errors="raise")
    onsets = _primary_onsets(labels)
    utc_hours = labels.index.tz_convert("UTC").hour
    recipe_b = (
        onsets
        & primary.eq("BREAKOUT")
        & secondary.eq("BK_UPWARD")
        & confidence.ge(0.6)
        & (utc_hours < 8)
    )
    recipe_c = onsets & primary.eq("TREND_DOWN") & (utc_hours >= 7) & (utc_hours < 16)
    rows: list[dict[str, object]] = []
    for recipe_id, active, maximum_hold in (
        ("bk_up_asia_conf06", recipe_b, 14_400.0),
        ("fade_td_eu", recipe_c, 86_400.0),
    ):
        for label_time in labels.index[active]:
            rows.append(
                {
                    "recipe_id": recipe_id,
                    "label_time_utc": label_time.tz_convert("UTC"),
                    "decision_time_utc": label_time.tz_convert("UTC")
                    + pd.Timedelta(minutes=5),
                    "side": "long",
                    "maximum_hold_seconds": maximum_hold,
                    "confidence": float(confidence.loc[label_time]),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "recipe_id",
            "label_time_utc",
            "decision_time_utc",
            "side",
            "maximum_hold_seconds",
            "confidence",
        ],
    ).sort_values("label_time_utc", kind="stable", ignore_index=True)


def trend_aligned_selective_recipe_events(events: pd.DataFrame) -> pd.DataFrame:
    """Flip only the experimental TREND_DOWN fade recipe to trend alignment."""
    required = {"recipe_id", "side"}
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"selective recipe events missing: {sorted(missing)}")
    aligned = events.copy(deep=True)
    fade = aligned["recipe_id"].eq("fade_td_eu")
    if not aligned.loc[fade, "side"].eq("long").all():
        raise ValueError("TREND_DOWN fade source events must be long before alignment")
    aligned.loc[fade, "recipe_id"] = "follow_td_eu"
    aligned.loc[fade, "side"] = "short"
    return aligned


def extract_symmetric_trend_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Preserve source B and emit aligned EU up/down trend onsets."""
    base = trend_aligned_selective_recipe_events(
        extract_selective_recipe_events(labels)
    )
    primary = labels["primary_code"].fillna("UNKNOWN").astype(str).str.upper()
    confidence = pd.to_numeric(labels["confidence"], errors="raise")
    utc_hours = labels.index.tz_convert("UTC").hour
    trend_up = (
        _primary_onsets(labels)
        & primary.eq("TREND_UP")
        & (utc_hours >= 7)
        & (utc_hours < 16)
    )
    additions = pd.DataFrame(
        [
            {
                "recipe_id": "follow_tu_eu",
                "label_time_utc": label_time.tz_convert("UTC"),
                "decision_time_utc": label_time.tz_convert("UTC")
                + pd.Timedelta(minutes=5),
                "side": "long",
                "maximum_hold_seconds": 86_400.0,
                "confidence": float(confidence.loc[label_time]),
            }
            for label_time in labels.index[trend_up]
        ]
    )
    return pd.concat([base, additions], ignore_index=True).sort_values(
        "label_time_utc", kind="stable", ignore_index=True
    )


def extract_four_hour_long_trend_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Limit only mirrored EU trend-up events to the source four-hour hold."""
    events = extract_symmetric_trend_events(labels)
    trend_up = events["recipe_id"].eq("follow_tu_eu")
    if not events.loc[trend_up, "maximum_hold_seconds"].eq(86_400.0).all():
        raise ValueError("EU trend-up control events must use a 24-hour hold")
    events.loc[trend_up, "maximum_hold_seconds"] = 14_400.0
    return events


def extract_source_fade_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Select exact pinned Recipe C events without modifying their fields."""
    events = extract_selective_recipe_events(labels)
    return events.loc[events["recipe_id"].eq("fade_td_eu")].reset_index(drop=True)


def extract_source_breakout_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Select exact pinned Recipe B events without modifying their fields."""
    events = extract_selective_recipe_events(labels)
    return events.loc[events["recipe_id"].eq("bk_up_asia_conf06")].reset_index(
        drop=True
    )


def extract_source_follow_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Select exact pinned Recipe C times and align their side with TREND_DOWN."""
    return trend_aligned_selective_recipe_events(extract_source_fade_events(labels))


def _trend_down_session_events(
    labels: pd.DataFrame,
    *,
    start_hour: int,
    end_hour: int,
    recipe_id: str,
) -> pd.DataFrame:
    _validate_datetime_index(labels, "Hypertrader labels")
    missing = _LABEL_COLUMNS.difference(labels.columns)
    if missing:
        raise ValueError(f"Hypertrader labels missing: {sorted(missing)}")
    if not 0 <= start_hour < end_hour <= 24:
        raise ValueError("session hours require 0 <= start < end <= 24")
    primary = labels["primary_code"].fillna("UNKNOWN").astype(str).str.upper()
    confidence = pd.to_numeric(labels["confidence"], errors="raise")
    hours = labels.index.tz_convert("UTC").hour
    active = (
        _primary_onsets(labels)
        & primary.eq("TREND_DOWN")
        & (hours >= start_hour)
        & (hours < end_hour)
    )
    rows = [
        {
            "recipe_id": recipe_id,
            "label_time_utc": stamp.tz_convert("UTC"),
            "decision_time_utc": stamp.tz_convert("UTC") + pd.Timedelta(minutes=5),
            "side": "short",
            "maximum_hold_seconds": 86_400.0,
            "confidence": float(confidence.loc[stamp]),
        }
        for stamp in labels.index[active]
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "recipe_id",
            "label_time_utc",
            "decision_time_utc",
            "side",
            "maximum_hold_seconds",
            "confidence",
        ],
    )


def extract_source_follow_asia_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Extract the 00:00-07:00 UTC TREND_DOWN onset negative control."""
    return _trend_down_session_events(
        labels, start_hour=0, end_hour=7, recipe_id="follow_td_asia_control"
    )


def extract_source_follow_all_day_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Extract every UTC TREND_DOWN onset for the all-day operational control."""
    return _trend_down_session_events(
        labels, start_hour=0, end_hour=24, recipe_id="follow_td_all_day"
    )


def extract_source_follow_session_06_15_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Extract the 06:00-15:00 UTC neighboring-session sensitivity."""
    return _trend_down_session_events(
        labels, start_hour=6, end_hour=15, recipe_id="follow_td_session_06_15"
    )


def extract_source_follow_session_08_17_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Extract the 08:00-17:00 UTC neighboring-session sensitivity."""
    return _trend_down_session_events(
        labels, start_hour=8, end_hour=17, recipe_id="follow_td_session_08_17"
    )


def extract_source_follow_us_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Extract the 16:00-24:00 UTC TREND_DOWN onset negative control."""
    return _trend_down_session_events(
        labels, start_hour=16, end_hour=24, recipe_id="follow_td_us_control"
    )


def source_recipe_event_policy(candidate_family: str) -> str:
    """Describe the immutable source-event policy for one replay family."""
    policies = {
        "symmetric-trend-aligned": (
            "source_b_asia_breakout_plus_eu_trend_up_down_onsets"
        ),
        "symmetric-trend-aligned-long4h": (
            "source_b_asia_breakout_plus_eu_trend_up_down_onsets_long4h"
        ),
        "source-fade-only": "pinned_source_recipe_c_fade_only",
        "source-follow-only": "pinned_source_recipe_c_follow_only",
        "source-follow-all-day": "trend_down_all_day_operational_control",
        "source-follow-all-day-confidence-70": (
            "trend_down_all_day_minimum_confidence_0_70_development"
        ),
        "source-follow-all-day-opposite-exit": (
            "trend_down_all_day_opposite_source_exit"
        ),
        "source-follow-all-day-margin-stop": "trend_down_all_day_margin_stop_grid",
        "source-follow-all-day-wide-margin-stop": (
            "trend_down_all_day_wide_margin_stop_grid"
        ),
        "source-follow-session-06-15": "trend_down_session_06_15_sensitivity",
        "source-follow-session-05-14-confidence-70": (
            "trend_down_session_05_14_minimum_confidence_0_70_sensitivity"
        ),
        "source-follow-session-06-15-confidence-70": (
            "trend_down_session_06_15_minimum_confidence_0_70_development"
        ),
        "source-follow-session-06-15-confidence-70-peak-activation7": (
            "trend_down_session_06_15_confidence_0_70_peak_activation_7_sensitivity"
        ),
        "source-follow-session-06-15-confidence-70-peak-tier0": (
            "trend_down_session_06_15_confidence_0_70_source_peak_tier0_development"
        ),
        "source-follow-session-06-15-confidence-70-spread-1": (
            "trend_down_session_06_15_confidence_0_70_spread_1_0_development"
        ),
        "source-follow-session-07-16-confidence-70": (
            "trend_down_session_07_16_minimum_confidence_0_70_sensitivity"
        ),
        "source-follow-session-08-17": "trend_down_session_08_17_sensitivity",
        "source-follow-session-08-17-confidence-70": (
            "trend_down_session_08_17_minimum_confidence_0_70_sensitivity"
        ),
        "source-follow-asia-only": "trend_down_asia_negative_control",
        "source-follow-us-only": "trend_down_us_negative_control",
        "source-follow-margin-stop": "pinned_source_recipe_c_follow_only",
        "source-follow-wide-margin-stop": (
            "pinned_source_recipe_c_follow_wide_margin_stop_grid"
        ),
        "source-breakout-only": "pinned_source_recipe_b_breakout_only",
        "source-range-direction": "recipe_c_low_range_follow_high_range_fade",
    }
    return policies.get(candidate_family, "pinned_source_b_c")


def annotate_signal_range_eligibility(
    events: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    maximum_range_bps: float,
) -> pd.DataFrame:
    """Annotate an explicit completed-bar range ceiling without dropping events."""
    if not math.isfinite(maximum_range_bps) or maximum_range_bps <= 0.0:
        raise ValueError("maximum signal range must be finite and positive")
    if "label_time_utc" not in events:
        raise ValueError("selective recipe events require label_time_utc")
    _validate_completed_five_minute_bars(bars)
    missing = {"open", "high", "low"}.difference(bars.columns)
    if missing:
        raise ValueError(f"five-minute signal bars missing: {sorted(missing)}")
    label_times = pd.DatetimeIndex(
        pd.to_datetime(events["label_time_utc"], utc=True, format="mixed")
    )
    aligned = bars.reindex(label_times)
    if aligned[["open", "high", "low"]].isna().any(axis=None):
        raise ValueError("five-minute signal bars do not cover every recipe event")
    opening = pd.to_numeric(aligned["open"], errors="raise").to_numpy(dtype=float)
    high = pd.to_numeric(aligned["high"], errors="raise").to_numpy(dtype=float)
    low = pd.to_numeric(aligned["low"], errors="raise").to_numpy(dtype=float)
    if (opening <= 0.0).any() or (high < low).any():
        raise ValueError("five-minute signal bars contain invalid prices")
    range_bps = 10_000.0 * (high - low) / opening
    output = events.copy(deep=True)
    output["signal_range_bps"] = range_bps
    output["entry_eligible"] = range_bps <= maximum_range_bps
    output["entry_exclusion_reason"] = pd.Series(
        [None if eligible else "signal_range" for eligible in output["entry_eligible"]],
        index=output.index,
        dtype=object,
    )
    return output


def range_split_recipe_c_events(
    events: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    split_bps: float,
) -> pd.DataFrame:
    """Choose Recipe C follow or fade direction from completed-bar range."""
    required = {"recipe_id", "side"}
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"selective recipe events missing: {sorted(missing)}")
    if not events["recipe_id"].eq("fade_td_eu").all():
        raise ValueError("range direction split accepts only source Recipe C events")
    if not events["side"].eq("long").all():
        raise ValueError("source Recipe C events must be long before direction split")
    output = annotate_signal_range_eligibility(
        events,
        bars,
        maximum_range_bps=split_bps,
    )
    follow = output["entry_eligible"]
    output.loc[follow, "recipe_id"] = "follow_td_eu"
    output.loc[follow, "side"] = "short"
    output["entry_eligible"] = True
    output["entry_exclusion_reason"] = pd.Series(
        None,
        index=output.index,
        dtype=object,
    )
    return output


def _maker_decision_pulse(
    event: Mapping[str, object],
    reset_lead: pd.Timedelta,
    eligibility: pd.Timedelta,
) -> tuple[tuple[pd.Timestamp, ...], tuple[dict[str, object], ...]]:
    decision = pd.Timestamp(event["decision_time_utc"])
    signal_index = decision - pd.Timedelta(minutes=1)
    shared = {
        "recipe_id": str(event["recipe_id"]),
        "label_time_utc": pd.Timestamp(event["label_time_utc"]),
    }
    reset = {
        **shared,
        "entry_direction": None,
        "structural_direction": None,
        "maximum_hold_seconds": None,
    }
    eligible = event.get("entry_eligible", True)
    if not isinstance(eligible, bool):
        raise ValueError("selective recipe entry_eligible must be a boolean")
    active = reset
    if eligible:
        active = {
            **shared,
            "entry_direction": str(event["side"]),
            "structural_direction": str(event["side"]),
            "maximum_hold_seconds": float(event["maximum_hold_seconds"]),
        }
    indexes = (signal_index - reset_lead, signal_index, signal_index + eligibility)
    return indexes, (reset, active, reset)


def selective_recipe_maker_decisions(
    events: pd.DataFrame,
    *,
    reset_lead_seconds: float = 5.0,
    entry_eligibility_seconds: float = 300.0,
) -> pd.DataFrame:
    """Project exact B/C events into causal maker-replay decision pulses."""
    required = {
        "recipe_id",
        "label_time_utc",
        "decision_time_utc",
        "side",
        "maximum_hold_seconds",
    }
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"selective recipe maker events missing: {sorted(missing)}")
    if not math.isfinite(reset_lead_seconds) or reset_lead_seconds <= 0.0:
        raise ValueError("selective recipe reset lead must be finite and positive")
    if not math.isfinite(entry_eligibility_seconds) or entry_eligibility_seconds <= 0.0:
        raise ValueError("entry eligibility must be finite and positive")
    ordered = events.sort_values("decision_time_utc", kind="stable")
    rows: list[dict[str, object]] = []
    indexes: list[pd.Timestamp] = []
    reset_lead = pd.Timedelta(seconds=reset_lead_seconds)
    eligibility = pd.Timedelta(seconds=entry_eligibility_seconds)
    for event in ordered.to_dict(orient="records"):
        pulse_indexes, pulse_rows = _maker_decision_pulse(
            event, reset_lead, eligibility
        )
        indexes.extend(pulse_indexes)
        rows.extend(pulse_rows)
    decision_index = (
        pd.DatetimeIndex(indexes) if indexes else pd.DatetimeIndex([], tz="UTC")
    )
    columns = [
        "recipe_id",
        "label_time_utc",
        "entry_direction",
        "structural_direction",
        "maximum_hold_seconds",
    ]
    output = pd.DataFrame(rows, columns=columns, index=decision_index).sort_index(
        kind="stable"
    )
    if output.index.has_duplicates:
        raise ValueError("selective recipe maker decisions collide")
    return output
