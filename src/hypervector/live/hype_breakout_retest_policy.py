"""Causal breakout-direction retest policy for HYPE entry timing."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

_MINUTE_MS = 60_000

RetestState = Literal["idle", "unavailable", "armed", "pending", "confirmed", "expired"]
RetestMode = Literal["continuation", "fade"]


@dataclass(frozen=True)
class BreakoutRetestBar:
    """One completed 1-minute bar carrying authoritative breakout context."""

    decision_time_ms: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    state_5m: str
    breakout_side: str | None
    structural_side: str | None

    def __post_init__(self) -> None:
        """Reject incomplete, noncausal, or malformed bar observations."""
        if (
            isinstance(self.decision_time_ms, bool)
            or not isinstance(self.decision_time_ms, int)
            or self.decision_time_ms < 0
        ):
            raise ValueError("retest decision_time_ms must be a nonnegative integer")
        prices = (self.open_price, self.high_price, self.low_price, self.close_price)
        if not all(math.isfinite(value) and value > 0.0 for value in prices):
            raise ValueError("retest OHLC prices must be positive and finite")
        if self.low_price > min(self.open_price, self.high_price, self.close_price):
            raise ValueError("retest low_price exceeds the observed bar body")
        if self.high_price < max(self.open_price, self.low_price, self.close_price):
            raise ValueError("retest high_price is below the observed bar body")
        if not self.state_5m.strip():
            raise ValueError("retest state_5m must be non-empty")
        if self.breakout_side not in {None, "long", "short"}:
            raise ValueError("retest breakout_side must be long, short, or unavailable")
        if self.structural_side not in {None, "long", "short"}:
            raise ValueError(
                "retest structural_side must be long, short, or unavailable"
            )


@dataclass(frozen=True)
class BreakoutRetestResult:
    """One observable policy transition with no execution side effects."""

    state: RetestState
    reason: str
    side: str | None
    breakout_side: str | None
    structural_side: str | None
    mode: RetestMode | None
    eligible: bool
    boundary_price: float | None
    age_bars: int | None

    def __post_init__(self) -> None:
        """Enforce that only an explicit confirmation can become eligible."""
        if self.eligible != (self.state == "confirmed"):
            raise ValueError("only confirmed retest state may be eligible")
        if self.side not in {None, "long", "short"}:
            raise ValueError("retest result side must be long, short, or unavailable")
        if self.breakout_side not in {None, "long", "short"}:
            raise ValueError("retest breakout side is invalid")
        if self.structural_side not in {None, "long", "short"}:
            raise ValueError("retest structural side is invalid")
        if self.mode not in {None, "continuation", "fade"}:
            raise ValueError("retest mode is invalid")
        if not self.reason.strip():
            raise ValueError("retest result reason must be non-empty")
        if self.boundary_price is not None and (
            not math.isfinite(self.boundary_price) or self.boundary_price <= 0.0
        ):
            raise ValueError("retest boundary_price must be positive and finite")
        if self.age_bars is not None and self.age_bars < 0:
            raise ValueError("retest age_bars must be nonnegative")


@dataclass(frozen=True)
class _PendingRetest:
    side: Literal["long", "short"]
    breakout_side: Literal["long", "short"]
    structural_side: Literal["long", "short"]
    mode: RetestMode
    onset_time_ms: int
    boundary_price: float


class HypeBreakoutRetestPolicy:
    """Arm fresh breakouts and confirm only bounded 1-minute retest rejections."""

    def __init__(self, *, window_bars: int = 3) -> None:
        """Configure the causal confirmation window and empty symbol state."""
        if isinstance(window_bars, bool) or not isinstance(window_bars, int):
            raise TypeError("retest window_bars must be an integer")
        if window_bars < 1:
            raise ValueError("retest window_bars must be positive")
        self._window_bars = window_bars
        self._pending: dict[str, _PendingRetest] = {}

    @property
    def window_bars(self) -> int:
        """Return the immutable confirmation window in completed bars."""
        return self._window_bars

    def evaluate(
        self,
        *,
        symbol: str,
        bar: BreakoutRetestBar,
        breakout_onset: bool,
        breakout_boundary_price: float | None,
    ) -> BreakoutRetestResult:
        """Advance one symbol without permitting immediate onset execution."""
        normalized = _symbol(symbol)
        if not isinstance(breakout_onset, bool):
            raise TypeError("breakout_onset must be boolean")
        pending = self._pending.get(normalized)
        if pending is not None:
            return self._advance(normalized, pending, bar)
        if not breakout_onset:
            return _result(
                "idle",
                "no_pending_breakout",
                bar.breakout_side,
                breakout_side=bar.breakout_side,
                structural_side=bar.structural_side,
            )
        return self._arm(normalized, bar, breakout_boundary_price)

    def _arm(
        self,
        symbol: str,
        bar: BreakoutRetestBar,
        boundary: float | None,
    ) -> BreakoutRetestResult:
        if bar.breakout_side not in {"long", "short"}:
            return _result("unavailable", "breakout_direction_unavailable", None)
        if bar.structural_side not in {"long", "short"}:
            return _result(
                "unavailable",
                "structural_direction_unavailable",
                None,
                breakout_side=bar.breakout_side,
            )
        if boundary is None:
            return _result(
                "unavailable",
                "breakout_boundary_unavailable",
                bar.breakout_side,
                breakout_side=bar.breakout_side,
                structural_side=bar.structural_side,
            )
        if not math.isfinite(boundary) or boundary <= 0.0:
            raise ValueError("breakout_boundary_price must be positive and finite")
        aligned = bar.breakout_side == bar.structural_side
        mode: RetestMode = "continuation" if aligned else "fade"
        side = bar.breakout_side if aligned else bar.structural_side
        pending = _PendingRetest(
            side,
            bar.breakout_side,
            bar.structural_side,
            mode,
            bar.decision_time_ms,
            boundary,
        )
        self._pending[symbol] = pending
        return _result(
            "armed",
            _pending_reason(mode),
            pending.side,
            breakout_side=pending.breakout_side,
            structural_side=pending.structural_side,
            mode=pending.mode,
            boundary=pending.boundary_price,
            age=0,
        )

    def _advance(
        self,
        symbol: str,
        pending: _PendingRetest,
        bar: BreakoutRetestBar,
    ) -> BreakoutRetestResult:
        age = _age_bars(pending, bar)
        if pending.mode == "continuation" and bar.state_5m != "BREAKOUT":
            return self._expire(symbol, pending, age, "breakout_state_lost")
        if (
            pending.mode == "continuation"
            and bar.breakout_side != pending.breakout_side
        ):
            return self._expire(symbol, pending, age, "breakout_direction_changed")
        if bar.structural_side != pending.structural_side:
            return self._expire(symbol, pending, age, "structural_direction_changed")
        if age > self._window_bars:
            return self._expire(symbol, pending, age, "retest_window_expired")
        if _confirmed(pending, bar):
            del self._pending[symbol]
            return _result(
                "confirmed",
                _confirmed_reason(pending.mode),
                pending.side,
                breakout_side=pending.breakout_side,
                structural_side=pending.structural_side,
                mode=pending.mode,
                boundary=pending.boundary_price,
                age=age,
            )
        if age == self._window_bars:
            return self._expire(symbol, pending, age, "retest_window_expired")
        return _result(
            "pending",
            _pending_reason(pending.mode),
            pending.side,
            breakout_side=pending.breakout_side,
            structural_side=pending.structural_side,
            mode=pending.mode,
            boundary=pending.boundary_price,
            age=age,
        )

    def _expire(
        self,
        symbol: str,
        pending: _PendingRetest,
        age: int,
        reason: str,
    ) -> BreakoutRetestResult:
        del self._pending[symbol]
        return _result(
            "expired",
            reason,
            pending.side,
            breakout_side=pending.breakout_side,
            structural_side=pending.structural_side,
            mode=pending.mode,
            boundary=pending.boundary_price,
            age=age,
        )


def _age_bars(pending: _PendingRetest, bar: BreakoutRetestBar) -> int:
    elapsed = bar.decision_time_ms - pending.onset_time_ms
    if elapsed <= 0 or elapsed % _MINUTE_MS != 0:
        raise ValueError("retest decisions must advance in completed 1-minute bars")
    return elapsed // _MINUTE_MS


def _confirmed(pending: _PendingRetest, bar: BreakoutRetestBar) -> bool:
    boundary = pending.boundary_price
    if pending.side == "long":
        touched = bar.low_price <= boundary
        rejected = bar.close_price > boundary and bar.close_price > bar.open_price
        return touched and rejected
    touched = bar.high_price >= boundary
    rejected = bar.close_price < boundary and bar.close_price < bar.open_price
    return touched and rejected


def _result(
    state: RetestState,
    reason: str,
    side: str | None,
    *,
    breakout_side: str | None = None,
    structural_side: str | None = None,
    mode: RetestMode | None = None,
    boundary: float | None = None,
    age: int | None = None,
) -> BreakoutRetestResult:
    return BreakoutRetestResult(
        state=state,
        reason=reason,
        side=side,
        breakout_side=breakout_side,
        structural_side=structural_side,
        mode=mode,
        eligible=state == "confirmed",
        boundary_price=boundary,
        age_bars=age,
    )


def _pending_reason(mode: RetestMode) -> str:
    return (
        "awaiting_breakout_retest"
        if mode == "continuation"
        else "awaiting_failed_breakout_reclaim"
    )


def _confirmed_reason(mode: RetestMode) -> str:
    return (
        "breakout_retest_confirmed"
        if mode == "continuation"
        else "failed_breakout_reclaim_confirmed"
    )


def _symbol(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("retest symbol must be non-empty text")
    return value.strip().upper()
