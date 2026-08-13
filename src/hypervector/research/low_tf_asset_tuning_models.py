"""Typed identities for bounded ETH/SOL low-timeframe tuning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import product
import json
import math
from typing import Literal

import pandas as pd

TuningSide = Literal["long", "short"]


@dataclass(frozen=True)
class TrendEntryShape:
    """One causal 5m entry shape with completed 15m context."""

    breakout_lookback: int
    ema_fast: int
    ema_slow: int
    compression_percentile: float
    clearance_bps: float

    def __post_init__(self) -> None:
        """Reject malformed entry parameters."""
        _positive_integer(self.breakout_lookback, "breakout_lookback")
        _positive_integer(self.ema_fast, "ema_fast")
        _positive_integer(self.ema_slow, "ema_slow")
        if self.ema_fast >= self.ema_slow:
            raise ValueError("ema_fast must be below ema_slow")
        _percentile(self.compression_percentile, "compression_percentile")
        _positive(self.clearance_bps, "clearance_bps")


@dataclass(frozen=True)
class TrendExitShape:
    """One runtime-mappable fixed stop, reward, and hold contract."""

    stop_bps: float
    target_r_multiple: float
    maximum_hold_bars: int

    def __post_init__(self) -> None:
        """Reject non-positive exit parameters."""
        _positive(self.stop_bps, "stop_bps")
        _positive(self.target_r_multiple, "target_r_multiple")
        _positive_integer(self.maximum_hold_bars, "maximum_hold_bars")


@dataclass(frozen=True)
class LowTfAssetTrial:
    """One asset, direction, entry, and exit hypothesis."""

    symbol: str
    side: TuningSide
    entry: TrendEntryShape
    exit: TrendExitShape

    def __post_init__(self) -> None:
        """Require supported explicit asset and side identities."""
        if self.symbol not in {"ETH", "SOL"}:
            raise ValueError("tuning symbol must be ETH or SOL")
        if self.side not in {"long", "short"}:
            raise ValueError("tuning side must be long or short")

    @property
    def trial_id(self) -> str:
        """Return a stable content-derived trial identifier."""
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        digest = sha256(payload.encode()).hexdigest()[:16]
        return f"lowtf-{self.symbol.lower()}-{self.side}-{digest}"


@dataclass(frozen=True)
class TuningWindow:
    """One ordered chronological evaluation window."""

    name: str
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp

    def __post_init__(self) -> None:
        """Require a named, timezone-aware, ordered window."""
        start = pd.Timestamp(self.start_utc)
        end = pd.Timestamp(self.end_utc)
        if not self.name.strip() or start.tz is None or end.tz is None or start >= end:
            raise ValueError("tuning window must be named, aware, and ordered")


@dataclass(frozen=True)
class TuningScenario:
    """One explicit all-in round-trip friction assumption."""

    name: str
    round_trip_cost_bps: float

    def __post_init__(self) -> None:
        """Require a named positive finite friction scenario."""
        if not self.name.strip():
            raise ValueError("tuning scenario name is required")
        _positive(self.round_trip_cost_bps, "round_trip_cost_bps")


@dataclass(frozen=True)
class TuningTrialResult:
    """One complete trial result for a segment and friction scenario."""

    trial_id: str
    symbol: str
    side: TuningSide
    segment: str
    scenario: str
    signal_count: int
    completed_trades: int
    wins: int
    losses: int
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    total_fees_usd: float
    funding_cashflow_usd: float
    liquidations: int
    rejection_count: int
    monthly_net_pnl_usd: tuple[tuple[str, float], ...]
    trade_records: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class DevelopmentTrialSummary:
    """Transparent development ranking for one asset and side."""

    trial_id: str
    symbol: str
    side: TuningSide
    rank: int
    positive_months: int
    total_months: int
    worst_month_usd: float
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    completed_trades: int
    trades_per_30_days: float
    liquidations: int


def default_entry_shapes() -> tuple[TrendEntryShape, ...]:
    """Return the predeclared 36-shape entry search surface."""
    dimensions = product(
        (24, 48, 120),
        ((9, 21), (13, 34), (21, 55)),
        (20.0, 35.0),
        (4.0, 8.0),
    )
    return tuple(
        TrendEntryShape(lookback, fast, slow, compression, clearance)
        for lookback, (fast, slow), compression, clearance in dimensions
    )


def default_exit_shapes() -> tuple[TrendExitShape, ...]:
    """Return the predeclared 12-shape execution-contract surface."""
    return tuple(
        TrendExitShape(stop, reward, hold)
        for stop, reward, hold in product(
            (40.0, 80.0),
            (1.5, 2.0, 3.0),
            (12, 24),
        )
    )


def default_tuning_windows() -> tuple[TuningWindow, ...]:
    """Return the frozen development and later chronological windows."""
    return (
        TuningWindow(
            "development",
            pd.Timestamp("2025-07-28", tz="UTC"),
            pd.Timestamp("2026-01-28", tz="UTC"),
        ),
        TuningWindow(
            "validation",
            pd.Timestamp("2026-01-28", tz="UTC"),
            pd.Timestamp("2026-04-28", tz="UTC"),
        ),
        TuningWindow(
            "pseudo_holdout",
            pd.Timestamp("2026-04-28", tz="UTC"),
            pd.Timestamp("2026-07-28", tz="UTC"),
        ),
    )


def default_tuning_scenarios() -> tuple[TuningScenario, ...]:
    """Return nominal and adverse all-in friction assumptions."""
    return (
        TuningScenario("nominal", 13.0),
        TuningScenario("stress", 20.0),
    )


def _positive(value: float, name: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0.0:
        raise ValueError(f"{name} must be positive and finite")


def _positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _percentile(value: float, name: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    if not 0.0 <= value <= 100.0:
        raise ValueError(f"{name} must be within [0, 100]")
