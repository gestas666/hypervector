"""Source contracts for selective target pullback-transition re-entry."""

from __future__ import annotations

from collections.abc import Mapping
import math

import pandas as pd

from hypervector.research.hypervelocity_margin_stop_compare import (
    summarize_margin_stop_grid,
)
from hypervector.research.maker_replay_models import (
    MakerReplayConfig,
    MakerReplayReport,
    SameDirectionReentryPolicy,
)
from hypervector.research.maker_replay_signals import available_reentry_events

CONTROL_CANDIDATE = "regime_reset_60s"
PULLBACK_CANDIDATE = "target_pullback_transition_cap6_mature30"
_CANDIDATES = (CONTROL_CANDIDATE, PULLBACK_CANDIDATE)
_SOURCE_COLUMNS = {
    "open_time_utc",
    "close_time_utc",
    "side",
    "entry_price",
    "exit_price",
}


def _replay_config(policy: SameDirectionReentryPolicy) -> MakerReplayConfig:
    target_policy = policy == "target_pullback_transition"
    return MakerReplayConfig(
        initial_equity=10_000.0,
        maker_fee_rate=0.00015,
        taker_fee_rate=0.00045,
        fill_rule="trade-through",
        entry_ttl_seconds=300.0,
        reentry_cooldown_seconds=60.0,
        same_direction_reentry_policy=policy,
        target_continuation_limit_per_episode=6 if target_policy else None,
        target_continuation_minimum_episode_seconds=(1_800.0 if target_policy else 0.0),
    )


def target_pullback_candidate_configs() -> dict[str, MakerReplayConfig]:
    """Return the frozen reset control and selective pullback challenger."""
    return {
        CONTROL_CANDIDATE: _replay_config("regime_reset"),
        PULLBACK_CANDIDATE: _replay_config("target_pullback_transition"),
    }


def _source_positions(positions: pd.DataFrame, leverage: float) -> pd.DataFrame:
    missing = _SOURCE_COLUMNS.difference(positions.columns)
    if missing:
        raise ValueError(f"pullback source positions missing: {sorted(missing)}")
    frame = positions.copy()
    frame["open_ts"] = pd.to_datetime(
        frame["open_time_utc"], utc=True, format="ISO8601"
    )
    frame["close_ts"] = pd.to_datetime(
        frame["close_time_utc"], utc=True, errors="coerce", format="ISO8601"
    )
    frame["entry_price"] = pd.to_numeric(frame["entry_price"], errors="coerce")
    frame["exit_price"] = pd.to_numeric(frame["exit_price"], errors="coerce")
    frame["side"] = frame["side"].astype(str).str.lower()
    if frame["open_ts"].isna().any() or frame["entry_price"].isna().any():
        raise ValueError("pullback source positions contain invalid entries")
    if not frame["side"].isin(("long", "short")).all():
        raise ValueError("pullback source sides must be long or short")
    sign = frame["side"].map({"long": 1.0, "short": -1.0})
    price_return = (frame["exit_price"] - frame["entry_price"]) / frame["entry_price"]
    frame["gross_margin_pct"] = price_return * sign * leverage * 100.0
    return frame.sort_values("open_ts", kind="stable").reset_index(drop=True)


def _available_structural(decisions: pd.DataFrame) -> pd.Series:
    if "structural_direction" not in decisions:
        raise ValueError("pullback decisions require structural_direction")
    index = decisions.index
    valid = isinstance(index, pd.DatetimeIndex) and index.tz is not None
    valid &= index.is_unique and index.is_monotonic_increasing
    if not valid:
        raise ValueError("pullback decisions require a causal DatetimeIndex")
    values = decisions["structural_direction"].astype(object).copy()
    values.index = values.index + pd.Timedelta(minutes=1)
    return values


def _window_row(
    previous: pd.Series,
    current: pd.Series,
    structural: pd.Series,
    events: pd.Series,
) -> dict[str, object]:
    close_value = previous["close_ts"]
    close_time = None if pd.isna(close_value) else pd.Timestamp(close_value)
    base: dict[str, object] = {
        "anchor_open_time_utc": pd.Timestamp(previous["open_ts"]).isoformat(),
        "anchor_close_time_utc": None if close_time is None else close_time.isoformat(),
        "next_open_time_utc": pd.Timestamp(current["open_ts"]).isoformat(),
        "side": str(current["side"]),
        "anchor_gross_margin_pct": float(previous["gross_margin_pct"]),
    }
    if close_time is None:
        return {
            **base,
            "structural_reset_observed": None,
            "pullback_transition_observed": None,
            "first_pullback_transition_utc": None,
        }
    end = pd.Timestamp(current["open_ts"])
    structural_window = structural.loc[
        (structural.index > close_time) & (structural.index <= end)
    ]
    event_window = events.loc[(events.index > close_time) & (events.index <= end)]
    matches = event_window.loc[event_window.eq(current["side"])]
    return {
        **base,
        "structural_reset_observed": bool(structural_window.ne(current["side"]).any()),
        "pullback_transition_observed": not matches.empty,
        "first_pullback_transition_utc": (
            None if matches.empty else pd.Timestamp(matches.index[0]).isoformat()
        ),
    }


def source_pullback_compatibility(
    positions: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    leverage: float = 40.0,
    target_like_margin_pct: float = 6.0,
) -> dict[str, object]:
    """Measure pullback events between visible target-like same-side trades."""
    if not math.isfinite(leverage) or leverage <= 0.0:
        raise ValueError("pullback source leverage must be finite and positive")
    if not math.isfinite(target_like_margin_pct) or target_like_margin_pct <= 0.0:
        raise ValueError("target-like margin threshold must be finite and positive")
    source = _source_positions(positions, leverage)
    structural = _available_structural(decisions)
    events = available_reentry_events(decisions)
    windows = [
        _window_row(source.iloc[index - 1], source.iloc[index], structural, events)
        for index in range(1, len(source))
        if source.iloc[index - 1]["side"] == source.iloc[index]["side"]
        and source.iloc[index - 1]["gross_margin_pct"] >= target_like_margin_pct
    ]
    observable = [row for row in windows if row["anchor_close_time_utc"] is not None]
    pullbacks = [row for row in observable if row["pullback_transition_observed"]]
    return {
        "target_like_margin_threshold_pct": target_like_margin_pct,
        "target_like_same_side_windows": len(windows),
        "observable_windows": len(observable),
        "censored_missing_close": len(windows) - len(observable),
        "pullback_transition_windows": len(pullbacks),
        "pullback_without_structural_reset": sum(
            not bool(row["structural_reset_observed"]) for row in pullbacks
        ),
        "structural_reset_windows": sum(
            bool(row["structural_reset_observed"]) for row in observable
        ),
        "windows": windows,
    }


def summarize_target_pullback(
    reports: Mapping[str, MakerReplayReport],
    configs: Mapping[str, MakerReplayConfig],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment_days: int = 30,
) -> dict[str, object]:
    """Summarize the exact frozen control and pullback candidate pair."""
    if tuple(configs) != _CANDIDATES or set(reports) != set(_CANDIDATES):
        raise ValueError(f"pullback candidates must be exactly {_CANDIDATES}")
    return summarize_margin_stop_grid(
        reports,
        configs,
        start=start,
        end=end,
        segment_days=segment_days,
    )
