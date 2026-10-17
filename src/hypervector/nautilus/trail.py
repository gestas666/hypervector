"""Close-evaluated trailing stop for ``exits.mode == "trail"`` (pure, no engine).

Research (VectorBT) trail mode combines two stops, both evaluated on bar
closes because the research portfolio is built from closes only:

* ``sl_stop`` with ``sl_trail=True``: the stop distance fixed at entry
  (``trail_atr_mult x ATR / close``) trails the best close since entry; it is
  hit when a close reaches ``peak_close x (1 - sl_frac)`` (long).
* ``sweep.exits._trail_exits``: an ATR stop ``extreme - trail_atr_mult x ATR``
  that ratchets with the bar high (long) / low (short) since entry; it is hit
  when a close crosses it.

:func:`trail_step` reproduces both, anchored at the real entry (research's
``_trail_exits`` can keep a stale anchor across stop-outs; the sim resets the
trail on every actual entry). An entry during the ATR warm-up (ATR not yet
finite on the entry bar) keeps the ATR stop disabled for that position, as in
``_trail_exits`` where ``max(nan, x)`` stays ``nan``; the percent trail still
protects it. A hit closes the position with a market order at that bar's
close, which is where VectorBT fills these exits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TrailState:
    """Trailing-stop state for one open position."""

    direction: str  # "long" | "short"
    sl_frac: float  # stop distance (fraction of price) fixed at entry
    peak_close: float  # best close since entry (VectorBT sl_trail anchor)
    extreme: float  # best high (long) / low (short) since entry
    # Ratcheting ATR stop level; nan when ATR was not finite on the entry bar
    # (ATR warm-up), in which case it stays disabled for this position.
    atr_stop: float

    @property
    def sl_level(self) -> float:
        if self.direction == "long":
            return self.peak_close * (1.0 - self.sl_frac)
        return self.peak_close * (1.0 + self.sl_frac)

    @property
    def stop_level(self) -> float:
        """Effective (tightest) stop level currently protecting the position."""
        levels = [self.sl_level]
        if math.isfinite(self.atr_stop):
            levels.append(self.atr_stop)
        return max(levels) if self.direction == "long" else min(levels)


def trail_start(
    direction: str,
    *,
    high: float,
    low: float,
    close: float,
    trail_dist: float,
    sl_frac: float,
) -> TrailState:
    """State on the entry bar (the entry bar itself is never evaluated)."""
    if direction not in ("long", "short"):
        raise ValueError(f"trail direction must be long|short, got {direction!r}")
    extreme = float(high) if direction == "long" else float(low)
    if math.isfinite(trail_dist):
        atr_stop = extreme - trail_dist if direction == "long" else extreme + trail_dist
    else:
        atr_stop = math.nan
    return TrailState(
        direction=direction,
        sl_frac=float(sl_frac),
        peak_close=float(close),
        extreme=extreme,
        atr_stop=atr_stop,
    )


def trail_step(
    state: TrailState,
    *,
    high: float,
    low: float,
    close: float,
    trail_dist: float,
) -> tuple[TrailState, bool]:
    """Advance one bar after entry; return ``(new_state, hit)``."""
    close = float(close)
    finite = math.isfinite(trail_dist)
    if state.direction == "long":
        # VectorBT checks the trailing sl against the anchor before updating it.
        sl_hit = close <= state.sl_level
        extreme = max(state.extreme, float(high))
        atr_stop = state.atr_stop
        if finite and math.isfinite(atr_stop):
            atr_stop = max(atr_stop, extreme - trail_dist)
        atr_hit = math.isfinite(atr_stop) and close < atr_stop
        peak_close = max(state.peak_close, close)
    else:
        sl_hit = close >= state.sl_level
        extreme = min(state.extreme, float(low))
        atr_stop = state.atr_stop
        if finite and math.isfinite(atr_stop):
            atr_stop = min(atr_stop, extreme + trail_dist)
        atr_hit = math.isfinite(atr_stop) and close > atr_stop
        peak_close = min(state.peak_close, close)
    new_state = replace(
        state, peak_close=peak_close, extreme=extreme, atr_stop=atr_stop
    )
    return new_state, bool(sl_hit or atr_hit)
