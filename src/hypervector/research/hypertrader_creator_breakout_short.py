"""Creator-published BK_DOWN short recipe as report-only research events."""

from __future__ import annotations

import pandas as pd

from hypervector.research.maker_replay_models import FillRule, MakerReplayConfig

CREATOR_RECIPE_REVISION = "5010d6b0ca9384decd0d74026160a1f2d5ed4dd9"
CREATOR_RESEARCH_REVISION = "53cd1f15437b49ba1fdfac09279ea324343dbb3d"
CREATOR_MINIMUM_CONFIDENCE = 0.70
CREATOR_MAXIMUM_HOLD_SECONDS = 86_400.0
CREATOR_MARGIN_FRACTION = 0.10
CREATOR_LEVERAGE = 40.0
CREATOR_TARGET_MARGIN_PCT = 8.0
CREATOR_TARGET_PRICE_POINTS = 130.0

_EVENT_COLUMNS = [
    "recipe_id",
    "label_time_utc",
    "decision_time_utc",
    "side",
    "maximum_hold_seconds",
    "confidence",
]
_REQUIRED_LABEL_COLUMNS = {"primary_code", "secondary_code", "confidence"}
_LEVERAGE_SURFACE = (20.0, 25.0, 30.0, 35.0, 40.0)


def extract_creator_breakout_short_events(labels: pd.DataFrame) -> pd.DataFrame:
    """Return causal confidence-qualified BREAKOUT/BK_DOWNWARD onsets."""
    _validate_labels(labels)
    primary = labels["primary_code"].fillna("UNKNOWN").astype(str).str.upper()
    secondary = labels["secondary_code"].fillna("").astype(str).str.upper()
    confidence = pd.to_numeric(labels["confidence"], errors="raise")
    onsets = primary.ne(primary.shift(1))
    selected = (
        onsets
        & primary.eq("BREAKOUT")
        & secondary.isin(("BK_DOWNWARD", "BK_DOWN"))
        & confidence.ge(CREATOR_MINIMUM_CONFIDENCE)
    )
    rows = [
        _event(stamp, float(confidence.loc[stamp])) for stamp in labels.index[selected]
    ]
    return pd.DataFrame(rows, columns=_EVENT_COLUMNS).sort_values(
        "label_time_utc", kind="stable", ignore_index=True
    )


def creator_breakout_short_leverage_configs(
    *,
    initial_equity: float,
    entry_eligibility_seconds: float,
    fill_rule: FillRule,
) -> dict[str, MakerReplayConfig]:
    """Return the frozen no-stop leverage surface for the creator challenger."""
    configs: dict[str, MakerReplayConfig] = {}
    for leverage in _LEVERAGE_SURFACE:
        name = f"lev{int(leverage)}"
        if leverage == CREATOR_LEVERAGE:
            name += "_source_control"
        configs[name] = MakerReplayConfig(
            initial_equity=initial_equity,
            margin_fraction=CREATOR_MARGIN_FRACTION,
            leverage=leverage,
            target_margin_pct=CREATOR_TARGET_MARGIN_PCT,
            target_price_points=CREATOR_TARGET_PRICE_POINTS,
            fill_rule=fill_rule,
            entry_ttl_seconds=entry_eligibility_seconds,
            reentry_cooldown_seconds=60.0,
            same_direction_reentry_policy="regime_reset",
        )
    return configs


def _event(stamp: pd.Timestamp, confidence: float) -> dict[str, object]:
    label_time = stamp.tz_convert("UTC")
    return {
        "recipe_id": "creator_bk_down_short_conf70",
        "label_time_utc": label_time,
        "decision_time_utc": label_time + pd.Timedelta(minutes=5),
        "side": "short",
        "maximum_hold_seconds": CREATOR_MAXIMUM_HOLD_SECONDS,
        "confidence": confidence,
    }


def _validate_labels(labels: pd.DataFrame) -> None:
    missing = _REQUIRED_LABEL_COLUMNS.difference(labels.columns)
    if missing:
        raise ValueError(f"Hypertrader labels missing: {sorted(missing)}")
    index = labels.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("Hypertrader labels require a timezone-aware DatetimeIndex")
    if not index.is_monotonic_increasing or not index.is_unique:
        raise ValueError("Hypertrader label timestamps must be ordered and unique")
