"""Full-frame signal precompute for the Phase 2 actor, with a causal probe.

The windowed actor path rebuilds every indicator over the trailing
``max_lookback`` bars on every bar (O(n x window)). Precomputing the strategy
signals and stop/take-profit fractions once over the whole replay (O(n))
gives the same decisions for causal builders. (Trail mode needs nothing
more: its distance is the entry bar's stop fraction, see ``nautilus.trail``.)

Precompute is only trusted after :func:`probe_precomputed` recomputes the
windowed (live-parity) intent on a deterministic sample of bars — every
entry bar (capped), a seeded sample of exit and ordinary bars, the first
bar past ``max_lookback`` and the last bar — and finds no mismatch. A
non-causal builder (lookahead) or one whose output drifts with the window
start shows up as a mismatch; the runner then falls back to the windowed
path (``signal_mode="auto"``) or fails the run (``"precomputed"``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

from hypervector.nautilus.signals import (
    SignalIntent,
    last_bar_intent,
    signals_from_ohlcv,
)
from hypervector.nautilus.sizing import exit_config_from_dict
from hypervector.sweep.exits import stop_distance_frac, tp_distance_frac

_OHLCV_COLS = ("open", "high", "low", "close", "volume")
_FLOAT_RTOL = 1e-9
_FLOAT_ATOL = 1e-12


@dataclass(frozen=True)
class PrecomputedIntents:
    """Per-bar intents and exit distances keyed by research bar-open label (ns)."""

    index_ns: np.ndarray
    entries: np.ndarray
    exits: np.ndarray
    direction: str
    stop_frac: np.ndarray
    tp_frac: np.ndarray
    exit_mode: str
    row_by_ns: dict[int, int] = field(repr=False)

    def __len__(self) -> int:
        return int(len(self.index_ns))

    def row(self, label_ns: int) -> int:
        try:
            return self.row_by_ns[int(label_ns)]
        except KeyError:
            raise KeyError(
                f"no precomputed intent for bar label {pd.Timestamp(int(label_ns), tz='UTC')}"
            ) from None

    def intent(self, row: int) -> SignalIntent:
        return SignalIntent(
            direction=self.direction,
            enter=bool(self.entries[row]),
            exit=bool(self.exits[row]),
            bar_index=int(row),
        )

    def stop_tp(self, row: int) -> tuple[float, float | None]:
        tp = float(self.tp_frac[row])
        return float(self.stop_frac[row]), (None if math.isnan(tp) else tp)


def ohlcv_frame(
    index_ns: Sequence[int] | np.ndarray,
    columns: dict[str, np.ndarray],
) -> pd.DataFrame:
    """Research-style OHLCV frame (UTC ``timestamp`` index, float columns)."""
    index = pd.DatetimeIndex(
        pd.to_datetime(np.asarray(index_ns, dtype=np.int64), unit="ns", utc=True),
        name="timestamp",
    )
    return pd.DataFrame(
        {c: np.asarray(columns[c], dtype=np.float64) for c in _OHLCV_COLS},
        index=index,
    )


def ohlcv_frame_from_bars(bars: Sequence[Any], *, label_offset_ns: int) -> pd.DataFrame:
    """Frame of exactly what the actor sees (instrument-rounded bar values)."""
    n = len(bars)
    labels = np.fromiter((int(b.ts_event) for b in bars), dtype=np.int64, count=n)
    labels -= int(label_offset_ns)
    cols = {
        "open": np.fromiter(
            (b.open.as_double() for b in bars), dtype=np.float64, count=n
        ),
        "high": np.fromiter(
            (b.high.as_double() for b in bars), dtype=np.float64, count=n
        ),
        "low": np.fromiter(
            (b.low.as_double() for b in bars), dtype=np.float64, count=n
        ),
        "close": np.fromiter(
            (b.close.as_double() for b in bars), dtype=np.float64, count=n
        ),
        "volume": np.fromiter(
            (b.volume.as_double() for b in bars), dtype=np.float64, count=n
        ),
    }
    return ohlcv_frame(labels, cols)


def _as_bool(series: Any, n: int, label: str) -> np.ndarray:
    arr = np.asarray(series.to_numpy() if hasattr(series, "to_numpy") else series)
    if arr.shape != (n,):
        raise ValueError(
            f"signal builder returned {label} of shape {arr.shape}, expected ({n},)"
        )
    return arr.astype(bool)


def precompute_intents(
    frame: pd.DataFrame,
    strategy_name: str,
    params: dict[str, Any],
    exits: dict[str, Any] | None,
) -> PrecomputedIntents:
    """Run the signal builder and exit-distance math once over ``frame``."""
    n = len(frame)
    entries, exits_s, direction = signals_from_ohlcv(frame, strategy_name, dict(params))
    cfg = exit_config_from_dict(exits)
    stop = stop_distance_frac(frame, cfg)
    tp = tp_distance_frac(stop, cfg)
    stop_arr = np.asarray(stop.to_numpy(dtype=np.float64))
    tp_arr = np.asarray(tp.to_numpy(dtype=np.float64)).copy()
    if cfg.mode == "trail":
        tp_arr[:] = np.nan
    index_ns = np.asarray(frame.index.as_unit("ns").asi8, dtype=np.int64)
    row_by_ns = {int(ts): i for i, ts in enumerate(index_ns)}
    if len(row_by_ns) != n:
        raise ValueError("bar labels are not unique; cannot key precomputed intents")
    return PrecomputedIntents(
        index_ns=index_ns,
        entries=_as_bool(entries, n, "entries"),
        exits=_as_bool(exits_s, n, "exits"),
        direction=str(direction),
        stop_frac=stop_arr,
        tp_frac=tp_arr,
        exit_mode=str(cfg.mode),
        row_by_ns=row_by_ns,
    )


def _sample_rows(
    intents: PrecomputedIntents,
    *,
    max_lookback: int,
    seed: int,
    max_entry_samples: int,
    max_exit_samples: int,
    random_samples: int,
) -> list[int]:
    n = len(intents)
    if n < 2:
        return []
    rng = np.random.default_rng(seed)
    rows: set[int] = {n - 1}
    if n > max_lookback:
        rows.add(int(max_lookback))
    entry_rows = np.flatnonzero(intents.entries[1:]) + 1
    if len(entry_rows) > max_entry_samples:
        pick = (
            np.linspace(0, len(entry_rows) - 1, max_entry_samples).round().astype(int)
        )
        entry_rows = entry_rows[np.unique(pick)]
    rows.update(int(r) for r in entry_rows)
    exit_rows = np.flatnonzero(intents.exits[1:]) + 1
    if len(exit_rows) > max_exit_samples:
        exit_rows = rng.choice(exit_rows, size=max_exit_samples, replace=False)
    rows.update(int(r) for r in exit_rows)
    k = min(random_samples, n - 1)
    rows.update(int(r) for r in rng.choice(np.arange(1, n), size=k, replace=False))
    return sorted(rows)


def _close(a: float, b: float) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    return math.isclose(a, b, rel_tol=_FLOAT_RTOL, abs_tol=_FLOAT_ATOL)


def probe_precomputed(
    intents: PrecomputedIntents,
    frame: pd.DataFrame,
    strategy_name: str,
    params: dict[str, Any],
    exits: dict[str, Any] | None,
    *,
    max_lookback: int,
    seed: int = 0,
    max_entry_samples: int = 48,
    max_exit_samples: int = 24,
    random_samples: int = 24,
) -> dict[str, Any]:
    """Compare precomputed rows with the windowed actor computation.

    Returns ``{"sampled", "mismatches", "first_mismatch", "seed", ...}``.
    Builder exceptions propagate (a technical failure, not a mismatch).
    """
    from hypervector.nautilus.actor import _stop_tp_fracs

    rows = _sample_rows(
        intents,
        max_lookback=max_lookback,
        seed=seed,
        max_entry_samples=max_entry_samples,
        max_exit_samples=max_exit_samples,
        random_samples=random_samples,
    )
    mismatches: list[dict[str, Any]] = []
    for i in rows:
        window = frame.iloc[max(0, i + 1 - int(max_lookback)) : i + 1]
        live = last_bar_intent(window, strategy_name, dict(params))
        pre = intents.intent(i)
        problems: list[str] = []
        if (live.enter, live.exit, live.direction) != (
            pre.enter,
            pre.exit,
            pre.direction,
        ):
            problems.append(
                f"intent windowed=(enter={live.enter},exit={live.exit},dir={live.direction}) "
                f"precomputed=(enter={pre.enter},exit={pre.exit},dir={pre.direction})"
            )
        w_stop, w_tp = _stop_tp_fracs(window, exits)
        p_stop, p_tp = intents.stop_tp(i)
        if (
            not _close(w_stop, p_stop)
            or (w_tp is None) != (p_tp is None)
            or (w_tp is not None and p_tp is not None and not _close(w_tp, p_tp))
        ):
            problems.append(
                f"stop/tp windowed=({w_stop},{w_tp}) precomputed=({p_stop},{p_tp})"
            )
        if problems:
            mismatches.append(
                {
                    "row": int(i),
                    "bar": str(frame.index[i]),
                    "window_bars": int(len(window)),
                    "problems": problems,
                }
            )
    return {
        "sampled": len(rows),
        "mismatches": len(mismatches),
        "first_mismatch": mismatches[0] if mismatches else None,
        "seed": int(seed),
        "max_lookback": int(max_lookback),
    }
