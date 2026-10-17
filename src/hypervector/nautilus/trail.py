"""Trailing stop for ``exits.mode == "trail"`` (pure, no engine): VectorBT parity.

Research trail mode (``sweep.metrics.compute_trial_metrics``) is ONE VectorBT
trailing ``sl_stop`` per position:

* the distance is fixed at entry: ``sl_frac = stop_distance_frac`` on the entry
  bar, i.e. ``trail_atr_mult x ATR / close`` (``sl_pct`` while ATR is still
  warming up), as a fraction of price;
* the anchor starts at the entry bar's close (VectorBT ``stop_entry_price``
  default) and ratchets with the high (long) / low (short) of every later bar;
  the entry bar's own extremes never move it;
* on each bar after the entry the stop level ``anchor x (1 -/+ sl_frac)`` is
  evaluated *before* the anchor takes that bar's extreme, intrabar against the
  bar's open/high/low, and fills as a stop-market order: a bar that opens
  through the level fills at the open, otherwise touching it fills at the level
  (configured slippage applies);
* the bar on which the stop fills ignores the strategy's own signals (VectorBT
  processes the stop instead of that bar's entries/exits);
* every new entry starts a fresh stop.

:func:`trail_step` reproduces that bar recursion exactly. The Nautilus actor
uses :func:`trail_start` / :func:`trail_ratchet` to keep a reduce-only
``STOP_MARKET`` order resting at :func:`grid_stop_price` of the level, so the
bar matching engine triggers it intrabar on the next bar (open -> high -> low
-> close; a gap fills at the open, a touch at the trigger).

Irreducible differences (documented, not modelled):

* the trigger sits on the instrument tick grid (the highest grid price at or
  below a long level, the lowest at or above a short level). Bars are on the
  same grid, so the trigger fires on exactly the bars where VectorBT's float
  level is touched; an intrabar fill is below the float level by less than one
  tick (long), above it for a short;
* a bar that sets a new extreme and closes beyond the ratcheted level leaves
  the next level already through the market. Nautilus rejects a stop there, so
  the actor exits with a market order at the next bar's opening instant (1 ns
  after the close, before that bar trades). It fills at the last price, which
  is the next bar's open whenever the next bar opens at the previous close;
  VectorBT fills the same bar at its open. If the next bar instead opens
  beyond the level in the position's favour, VectorBT does not fill at the
  open (it may fill later at the level, or hold) while the actor has already
  exited: the actor cannot see an open before it trades;
* the isolated-liquidation barrier VectorBT merges into ``sl_stop`` is not
  part of this stop (native liquidation is a reported runner gap); it only
  binds when it is nearer than the trail distance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

TRAIL_EXIT_MODEL = "intrabar_trailing_stop_market_vectorbt_parity"


@dataclass(frozen=True)
class TrailState:
    """Trailing-stop state for one open position."""

    direction: str  # "long" | "short"
    sl_frac: float  # stop distance (fraction of price) fixed at entry
    # Entry-bar close, then the best high (long) / low (short) of the bars
    # evaluated since the entry bar.
    anchor: float

    @property
    def stop_level(self) -> float:
        """Stop price the next bar is evaluated against (nan: no stop)."""
        if self.direction == "long":
            return self.anchor * (1.0 - self.sl_frac)
        return self.anchor * (1.0 + self.sl_frac)


def trail_start(direction: str, *, entry_close: float, sl_frac: float) -> TrailState:
    """State after the entry bar (the entry bar itself is never evaluated)."""
    if direction not in ("long", "short"):
        raise ValueError(f"trail direction must be long|short, got {direction!r}")
    sl_frac = float(sl_frac)
    if sl_frac < 0.0:
        raise ValueError(f"trail stop distance must be >= 0, got {sl_frac!r}")
    return TrailState(direction=direction, sl_frac=sl_frac, anchor=float(entry_close))


def trail_fill_price(
    state: TrailState, *, open: float, high: float, low: float
) -> float | None:
    """Stop-market fill on this bar at the current level (VectorBT ``get_stop_price_nb``).

    Long: ``open <= level`` fills at the open (gap), ``low <= level <= high``
    fills at the level, otherwise no fill. Short mirrors with ``level <= open``.
    """
    level = state.stop_level
    if not math.isfinite(level):
        return None
    if state.direction == "long":
        if open <= level:
            return float(open)
    elif level <= open:
        return float(open)
    if low <= level <= high:
        return float(level)
    return None


def trail_ratchet(state: TrailState, *, high: float, low: float) -> TrailState:
    """Move the anchor to this bar's high (long) / low (short) when it is better."""
    if state.direction == "long":
        anchor = max(state.anchor, float(high))
    else:
        anchor = min(state.anchor, float(low))
    if anchor == state.anchor:
        return state
    return replace(state, anchor=anchor)


def trail_step(
    state: TrailState, *, open: float, high: float, low: float
) -> tuple[TrailState, float | None]:
    """Advance one bar after entry; return ``(new_state, fill_price_or_None)``.

    The bar is evaluated against the level carried in from the previous bars,
    then the anchor ratchets with this bar's extreme (VectorBT order).
    """
    fill = trail_fill_price(state, open=open, high=high, low=low)
    return trail_ratchet(state, high=high, low=low), fill


def level_through_close(state: TrailState, close: float) -> bool:
    """True when the current level is already at/through ``close``.

    A stop cannot rest there; VectorBT fills it at the next bar's open.
    """
    level = state.stop_level
    if not math.isfinite(level):
        return False
    if state.direction == "long":
        return close <= level
    return close >= level


def grid_stop_price(
    level: float, *, increment: float, precision: int, direction: str
) -> float | None:
    """Tick-grid trigger for a stop at ``level`` protecting a ``direction`` position.

    Long (sell stop): the highest grid price ``<= level``; short (buy stop): the
    lowest grid price ``>= level``. Prices on the grid then touch the trigger
    exactly when they touch ``level``. ``None`` when no positive grid price
    exists (a long level below one tick can never be reached).
    """
    if direction not in ("long", "short"):
        raise ValueError(f"trail direction must be long|short, got {direction!r}")
    if not (math.isfinite(level) and increment > 0.0):
        return None
    k = math.floor(level / increment)

    def _px(n: int) -> float:
        return round(n * increment, precision)

    # Correct the float division by at most a step either way.
    while _px(k) > level:
        k -= 1
    while _px(k + 1) <= level:
        k += 1
    if direction == "short" and _px(k) < level:
        k += 1
    price = _px(k)
    return price if price > 0.0 else None
