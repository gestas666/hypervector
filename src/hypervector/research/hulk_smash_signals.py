"""Corrected, report-only Hulk Smash formation fingerprints."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


HULK_CURRENT_LONG: tuple[frozenset[str], ...] = (
    frozenset({"ST", "wOS", "wSlN", "wxU"}),
    frozenset({"ST", "bT", "rD", "wSlN"}),
    frozenset({"ST", "wSlN", "wxU"}),
    frozenset({"ST", "wOS", "wSlN"}),
)
HULK_CURRENT_SHORT: tuple[frozenset[str], ...] = (
    frozenset({"ST", "wSlP"}),
    frozenset({"ST", "rD", "wxD"}),
)
HULK_EXTENDED_LONG: tuple[frozenset[str], ...] = HULK_CURRENT_LONG + (
    frozenset({"ST", "rD", "wSlN"}),
    frozenset({"ST", "rD", "wSlN", "wxU"}),
    frozenset({"ST", "mSlP", "wOS", "wxU"}),
    frozenset({"ST", "bT", "mSlP", "wxU"}),
)
_REQUIRED = {"wt1", "wave_cross", "money_flow_value", "ema_11", "ema_15", "rsi_14"}
_OUTPUT_COLUMNS = [
    "candidate",
    "signal_time_utc",
    "side",
    "formation",
    "fingerprint",
    "quality_score",
    "eligible",
    "reason",
]


def evaluate_hulk_smash_signals(
    components: pd.DataFrame,
    supertrend: pd.Series,
    quality_score: pd.Series,
    *,
    quality_threshold: int,
    lookback_bars: int = 5,
    formation_set: Literal["current", "extended"] = "current",
) -> pd.DataFrame:
    """Return every exact formation match with quality outcome retained."""
    _validate_inputs(
        components, supertrend, quality_score, quality_threshold, lookback_bars
    )
    long_forms = HULK_CURRENT_LONG if formation_set == "current" else HULK_EXTENDED_LONG
    rows: list[dict[str, object]] = []
    for position in range(lookback_bars - 1, len(components)):
        direction = int(supertrend.iloc[position])
        if direction not in {-1, 1}:
            continue
        side = "long" if direction == 1 else "short"
        fingerprint = hulk_fingerprint(
            components, direction, position, lookback_bars, side
        )
        forms = long_forms if side == "long" else HULK_CURRENT_SHORT
        if fingerprint in forms:
            rows.append(
                _decision(
                    components.index[position],
                    side,
                    fingerprint,
                    int(quality_score.iloc[position]),
                    quality_threshold,
                    formation_set,
                )
            )
    return pd.DataFrame(rows, columns=_OUTPUT_COLUMNS)


def hulk_fingerprint(
    components: pd.DataFrame,
    supertrend_direction: int,
    position: int,
    lookback_bars: int,
    side: Literal["long", "short"],
) -> frozenset[str]:
    """Build one corrected exact-match formation fingerprint."""
    start = position - lookback_bars + 1
    if start < 0 or position >= len(components):
        raise IndexError("Hulk fingerprint window is outside component history")
    window = components.iloc[start : position + 1]
    wave = window["wt1"].to_numpy(dtype=np.float64)
    crosses = window["wave_cross"]
    flags = _long_flags(window, wave, crosses, supertrend_direction)
    if side == "short":
        flags = _short_flags(window, wave, crosses, supertrend_direction)
    return frozenset(name for name, active in flags.items() if active)


def _long_flags(
    window: pd.DataFrame,
    wave: np.ndarray,
    crosses: pd.Series,
    supertrend: int,
) -> dict[str, bool]:
    """Return corrected long-side formation flags."""
    flow = window["money_flow_value"].to_numpy(dtype=np.float64)
    return {
        "wxU": bool(crosses.eq(1).any()),
        "wOS": bool(np.isfinite(wave).any() and np.nanmin(wave) < -40.0),
        "rD": bool(crosses.eq(-1).any()),
        "bT": _crossed_up(window["ema_11"], window["ema_15"]),
        "ST": supertrend == 1,
        "wSlN": _finite_slope(wave, positive=False),
        "mSlP": _finite_slope(flow, positive=True),
    }


def _short_flags(
    window: pd.DataFrame,
    wave: np.ndarray,
    crosses: pd.Series,
    supertrend: int,
) -> dict[str, bool]:
    """Return current short-side formation flags."""
    return {
        "wxD": bool(crosses.eq(-1).any()),
        "wOB": bool(np.isfinite(wave).any() and np.nanmax(wave) > 40.0),
        "rD": bool(crosses.eq(-1).any()),
        "ST": supertrend == -1,
        "wSlP": _finite_slope(wave, positive=True),
        "rOB": bool(float(window.iloc[-1]["rsi_14"]) > 70.0),
    }


def _decision(
    timestamp: object,
    side: str,
    fingerprint: frozenset[str],
    score: int,
    threshold: int,
    formation_set: str,
) -> dict[str, object]:
    """Return one formation match with explicit quality disposition."""
    eligible = score >= threshold
    return {
        "candidate": f"hulk_{formation_set}_q{threshold}",
        "signal_time_utc": timestamp,
        "side": side,
        "formation": "+".join(sorted(fingerprint)),
        "fingerprint": tuple(sorted(fingerprint)),
        "quality_score": score,
        "eligible": eligible,
        "reason": "eligible" if eligible else f"quality_below_{threshold}",
    }


def _crossed_up(fast: pd.Series, slow: pd.Series) -> bool:
    """Return whether fast crossed above slow anywhere in the window."""
    valid = fast.notna() & slow.notna()
    event = valid & valid.shift(1, fill_value=False)
    event &= fast.gt(slow) & fast.shift(1).le(slow.shift(1))
    return bool(event.any())


def _finite_slope(values: np.ndarray, *, positive: bool) -> bool:
    """Compare finite window endpoints in the requested direction."""
    if len(values) < 2 or not np.isfinite(values[[0, -1]]).all():
        return False
    return bool(values[-1] > values[0] if positive else values[-1] < values[0])


def _validate_inputs(
    components: pd.DataFrame,
    supertrend: pd.Series,
    quality: pd.Series,
    threshold: int,
    lookback: int,
) -> None:
    """Validate aligned Hulk formation inputs."""
    missing = sorted(_REQUIRED.difference(components.columns))
    if missing:
        raise ValueError(f"Hulk Smash components missing columns: {missing}")
    if components.empty or not components.index.equals(supertrend.index):
        raise ValueError("Hulk Smash supertrend must align with components")
    if not components.index.equals(quality.index):
        raise ValueError("Hulk Smash quality scores must align with components")
    if threshold not in {3, 4} or lookback < 2:
        raise ValueError("Hulk Smash requires q3/q4 and at least two lookback bars")
