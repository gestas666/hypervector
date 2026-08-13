"""Meta-labels for strategy entries: TP-first → 1 else 0.

Labels use the **same** exit distances as research ExitConfig so metalabel
targets match the strategy that will be paper/live sized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from hypervector.ml.feature_matrix import FEATURE_NAMES, build_feature_matrix
from hypervector.sweep.exits import ExitConfig, stop_distance_frac, tp_distance_frac


@dataclass(frozen=True)
class LabelRow:
    entry_idx: int
    entry_ts_ms: int
    outcome_ts_ms: int
    label: int
    exit_reason: str
    features: dict[str, float]


def _bar_ts_ms(df: pd.DataFrame, i: int) -> int:
    if "timestamp" in df.columns:
        t = pd.Timestamp(df["timestamp"].iloc[i])
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        return int(t.timestamp() * 1000)
    if isinstance(df.index, pd.DatetimeIndex):
        t = pd.Timestamp(df.index[i])
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        return int(t.timestamp() * 1000)
    return int(i) * 60_000


def resolve_barrier_outcome(
    *,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    entry_idx: int,
    entry_price: float,
    sl_frac: float,
    tp_frac: float,
    direction: str,
    max_hold: int,
) -> tuple[int, str, int]:
    """Return (exit_idx, reason, outcome_ts_proxy_idx).

    reason ∈ {tp, sl, timeout}. Long: TP above / SL below; short mirrored.
    """
    n = len(close)
    if entry_price <= 0 or entry_idx >= n - 1:
        return entry_idx, "timeout", entry_idx

    if direction == "long":
        tp = entry_price * (1.0 + float(tp_frac))
        sl = entry_price * (1.0 - float(sl_frac))
    else:
        tp = entry_price * (1.0 - float(tp_frac))
        sl = entry_price * (1.0 + float(sl_frac))

    end = min(n - 1, entry_idx + max(1, int(max_hold)))
    for j in range(entry_idx + 1, end + 1):
        hi = float(high[j])
        lo = float(low[j])
        if direction == "long":
            hit_sl = lo <= sl
            hit_tp = hi >= tp
        else:
            hit_sl = hi >= sl
            hit_tp = lo <= tp
        if hit_sl and hit_tp:
            # Conservative: same bar both → SL first (no free lunch)
            return j, "sl", j
        if hit_tp:
            return j, "tp", j
        if hit_sl:
            return j, "sl", j
    return end, "timeout", end


def build_strategy_labels(
    df: pd.DataFrame,
    entries: pd.Series,
    *,
    direction: str,
    exit_cfg: ExitConfig,
    max_hold_bars: int = 120,
    feature_matrix: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Label every True entry bar; return DataFrame for training.

    Columns: entry_idx, entry_ts_ms, outcome_ts_ms, label, exit_reason, + FEATURE_NAMES
    """
    if direction not in ("long", "short"):
        raise ValueError("direction must be long|short")

    ent = entries.reindex(df.index).fillna(False).astype(bool)
    feats = feature_matrix if feature_matrix is not None else build_feature_matrix(df)
    sl_frac = stop_distance_frac(df, exit_cfg).to_numpy(dtype=float)
    tp_frac = tp_distance_frac(pd.Series(sl_frac, index=df.index), exit_cfg).to_numpy(
        dtype=float
    )
    # trail mode has NaN TP — use rr * sl as soft target for metalabel
    if exit_cfg.mode == "trail":
        tp_frac = sl_frac * float(exit_cfg.rr)

    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    close = df["close"].astype(float).to_numpy()

    rows: list[dict[str, Any]] = []
    entry_idxs = np.flatnonzero(ent.to_numpy())
    for i in entry_idxs:
        i = int(i)
        if i < 30 or i >= len(df) - 2:
            continue
        ep = float(close[i])
        s = float(sl_frac[i]) if np.isfinite(sl_frac[i]) else float(exit_cfg.sl_pct)
        t = float(tp_frac[i]) if np.isfinite(tp_frac[i]) else s * float(exit_cfg.rr)
        exit_idx, reason, _ = resolve_barrier_outcome(
            high=high,
            low=low,
            close=close,
            entry_idx=i,
            entry_price=ep,
            sl_frac=max(s, 1e-6),
            tp_frac=max(t, 1e-6),
            direction=direction,
            max_hold=max_hold_bars,
        )
        label = 1 if reason == "tp" else 0
        frow = feats.iloc[i]
        if frow.isna().any():
            continue
        row: dict[str, Any] = {
            "entry_idx": i,
            "entry_ts_ms": _bar_ts_ms(df, i),
            "outcome_ts_ms": _bar_ts_ms(df, int(exit_idx)),
            "label": label,
            "exit_reason": reason,
        }
        for name in FEATURE_NAMES:
            row[name] = float(frow[name])
        rows.append(row)

    if not rows:
        return pd.DataFrame(
            columns=[
                "entry_idx",
                "entry_ts_ms",
                "outcome_ts_ms",
                "label",
                "exit_reason",
                *FEATURE_NAMES,
            ]
        )
    return pd.DataFrame(rows)
