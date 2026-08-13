"""Friction-aware, report-only screen for causal Cipher suite entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import math
import numpy as np
import pandas as pd
from numpy.typing import NDArray

from hypervector.research.cipher_suite_signals import (
    ALL_CIPHER_VARIANTS,
    CIPHER_VARIANTS,
)


@dataclass(frozen=True)
class CipherExitSpec:
    """One frozen target, stop, and maximum-hold combination."""

    target_bps: float
    stop_bps: float
    horizon_bars: int

    def __post_init__(self) -> None:
        distances = (self.target_bps, self.stop_bps)
        if not all(math.isfinite(value) and value > 0.0 for value in distances):
            raise ValueError("Cipher exit distances must be finite and positive")
        if self.horizon_bars < 1:
            raise ValueError("Cipher exit horizon must be positive")

    @property
    def identity(self) -> str:
        """Return a stable compact identity for serialized trials."""
        return f"tp{self.target_bps:g}_sl{self.stop_bps:g}_h{self.horizon_bars}"


FROZEN_EXIT_GRID: tuple[CipherExitSpec, ...] = tuple(
    CipherExitSpec(target, stop, horizon)
    for target in (20.0, 30.0, 40.0)
    for stop in (15.0, 25.0, 35.0)
    for horizon in (6, 12, 24)
)

FROZEN_15M_EXIT_GRID: tuple[CipherExitSpec, ...] = tuple(
    CipherExitSpec(target, stop, horizon)
    for target in (40.0, 60.0, 80.0)
    for stop in (25.0, 40.0, 60.0)
    for horizon in (8, 16, 32)
)


@dataclass(frozen=True)
class CipherScreenConfig:
    """Frozen candidates, friction, and exit grid for unit-notional research."""

    candidates: tuple[str, ...] = CIPHER_VARIANTS
    exit_specs: tuple[CipherExitSpec, ...] = FROZEN_EXIT_GRID
    maker_entry_fee_bps: float = 1.5
    maker_exit_fee_bps: float = 1.5
    taker_exit_fee_bps: float = 4.5
    bar_minutes: int = 5

    def __post_init__(self) -> None:
        if not self.candidates or len(set(self.candidates)) != len(self.candidates):
            raise ValueError("Cipher candidates must be non-empty and unique")
        if not set(self.candidates).issubset(ALL_CIPHER_VARIANTS):
            raise ValueError("Cipher screen contains an unknown candidate")
        if not self.exit_specs or len(set(self.exit_specs)) != len(self.exit_specs):
            raise ValueError("Cipher exit specifications must be non-empty and unique")
        fees = (
            self.maker_entry_fee_bps,
            self.maker_exit_fee_bps,
            self.taker_exit_fee_bps,
        )
        if not all(math.isfinite(value) and value >= 0.0 for value in fees):
            raise ValueError("Cipher fees must be finite and non-negative")
        if self.bar_minutes not in {5, 15}:
            raise ValueError("Cipher bar duration must be 5 or 15 minutes")

    @property
    def maker_round_trip_fee_bps(self) -> float:
        """Return maker entry plus resting maker target fees."""
        return self.maker_entry_fee_bps + self.maker_exit_fee_bps

    @property
    def taker_round_trip_fee_bps(self) -> float:
        """Return maker entry plus aggressive stop/timeout fees."""
        return self.maker_entry_fee_bps + self.taker_exit_fee_bps


@dataclass(frozen=True)
class CipherScreenTrade:
    """One unit-notional trade produced by a frozen Cipher trial."""

    signal_ts_ms: int
    entry_ts_ms: int
    outcome_ts_ms: int
    side: str
    entry_price: float
    exit_price: float
    status: str
    gross_return_bps: float
    fee_bps: float
    net_return_bps: float
    ambiguous: bool


@dataclass(frozen=True)
class CipherScreenTrial:
    """Economic result for one candidate and exit specification."""

    candidate: str
    exit_spec: CipherExitSpec
    trades: tuple[CipherScreenTrade, ...]
    trade_count: int
    wins: int
    losses: int
    net_pnl_bps: float
    profit_factor: float | None
    max_drawdown_bps: float
    total_fee_bps: float
    expired_occupied_signals: int
    censored_signals: int
    timeout_trades: int
    ambiguous_trades: int
    monthly_net_bps: dict[str, float]


@dataclass(frozen=True)
class CipherScreenReport:
    """All frozen trials with execution authority explicitly denied."""

    trials: tuple[CipherScreenTrial, ...]
    report_only: bool = True
    execution_authority: str = "none"
    place_attempted: bool = False


def screen_cipher_suite(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: CipherScreenConfig | None = None,
) -> CipherScreenReport:
    """Evaluate every candidate/exit pair with causal fills and one position."""
    resolved = config or CipherScreenConfig()
    times = _validate_inputs(bars, signals, resolved)
    prices = bars[["open", "high", "low", "close"]].to_numpy(dtype=np.float64)
    trials = tuple(
        _screen_trial(prices, times, signals, candidate, spec, resolved)
        for candidate in resolved.candidates
        for spec in resolved.exit_specs
    )
    return CipherScreenReport(trials=trials)


def _validate_inputs(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: CipherScreenConfig,
) -> pd.DatetimeIndex:
    required_bars = {"bar_open_at", "open", "high", "low", "close"}
    required_signals = {"candidate", "signal_time_utc", "side"}
    missing_bars = sorted(required_bars.difference(bars.columns))
    missing_signals = sorted(required_signals.difference(signals.columns))
    if missing_bars or missing_signals:
        raise ValueError(
            f"Cipher inputs missing bars={missing_bars}, signals={missing_signals}"
        )
    times = pd.DatetimeIndex(bars["bar_open_at"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError(
            "Cipher bars must have ordered unique timezone-aware timestamps"
        )
    if bars.empty:
        raise ValueError("Cipher bars must be non-empty")
    prices = bars[["open", "high", "low", "close"]].to_numpy(dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0.0).any():
        raise ValueError("Cipher OHLC prices must be finite and positive")
    if not signals.empty:
        signal_times = pd.DatetimeIndex(signals["signal_time_utc"])
        if signal_times.tz is None or not signal_times.isin(times).all():
            raise ValueError(
                "Cipher signals must reference observed timezone-aware bars"
            )
        if not set(signals["candidate"]).issubset(config.candidates):
            raise ValueError("Cipher signals contain an unconfigured candidate")
        if not set(signals["side"]).issubset({"long", "short"}):
            raise ValueError("Cipher signal sides must be long or short")
    return times


def _screen_trial(
    prices: NDArray[np.float64],
    times: pd.DatetimeIndex,
    signals: pd.DataFrame,
    candidate: str,
    spec: CipherExitSpec,
    config: CipherScreenConfig,
) -> CipherScreenTrial:
    selected = signals.loc[signals["candidate"].eq(candidate)].sort_values(
        "signal_time_utc"
    )
    positions = {stamp: index for index, stamp in enumerate(times)}
    trades: list[CipherScreenTrade] = []
    occupied_until = pd.Timestamp.min.tz_localize(UTC)
    expired = censored = 0
    for row in selected.itertuples(index=False):
        signal_time = pd.Timestamp(row.signal_time_utc)
        if signal_time < occupied_until:
            expired += 1
            continue
        trade = _resolve_trade(
            prices,
            times,
            positions[signal_time],
            str(row.side),
            spec,
            config.maker_round_trip_fee_bps,
            config.taker_round_trip_fee_bps,
            config.bar_minutes,
        )
        if trade is None:
            censored += 1
            continue
        trades.append(trade)
        occupied_until = pd.Timestamp(trade.outcome_ts_ms, unit="ms", tz=UTC)
    return _summarize(candidate, spec, trades, expired, censored)


def _resolve_trade(
    prices: NDArray[np.float64],
    times: pd.DatetimeIndex,
    signal_position: int,
    side: str,
    spec: CipherExitSpec,
    maker_fee_bps: float,
    taker_fee_bps: float,
    bar_minutes: int,
) -> CipherScreenTrade | None:
    entry_position = signal_position + 1
    signal_time = times[signal_position]
    duration = pd.Timedelta(minutes=bar_minutes)
    expected_entry = signal_time + duration
    if entry_position >= len(prices) or times[entry_position] != expected_entry:
        return None
    entry = float(prices[entry_position, 0])
    sign = 1.0 if side == "long" else -1.0
    target = entry * (1.0 + sign * spec.target_bps / 10_000.0)
    stop = entry * (1.0 - sign * spec.stop_bps / 10_000.0)
    end = min(entry_position + spec.horizon_bars, len(prices))
    for position in range(entry_position, end):
        target_hit, stop_hit = _touches(prices[position], side, target, stop)
        outcome_time = times[position] + duration
        if target_hit and stop_hit:
            return _trade(
                signal_time,
                expected_entry,
                outcome_time,
                side,
                entry,
                stop,
                "ambiguous_stop_first",
                taker_fee_bps,
                True,
            )
        if stop_hit:
            return _trade(
                signal_time,
                expected_entry,
                outcome_time,
                side,
                entry,
                stop,
                "stop",
                taker_fee_bps,
                False,
            )
        if target_hit:
            return _trade(
                signal_time,
                expected_entry,
                outcome_time,
                side,
                entry,
                target,
                "target",
                maker_fee_bps,
                False,
            )
    if end - entry_position < spec.horizon_bars:
        return None
    outcome_time = times[end - 1] + duration
    exit_price = float(prices[end - 1, 3])
    return _trade(
        signal_time,
        expected_entry,
        outcome_time,
        side,
        entry,
        exit_price,
        "timeout",
        taker_fee_bps,
        False,
    )


def _touches(
    prices: NDArray[np.float64],
    side: str,
    target: float,
    stop: float,
) -> tuple[bool, bool]:
    high = float(prices[1])
    low = float(prices[2])
    if side == "long":
        return high >= target, low <= stop
    return low <= target, high >= stop


def _trade(
    signal_time: pd.Timestamp,
    entry_time: pd.Timestamp,
    outcome_time: pd.Timestamp,
    side: str,
    entry: float,
    exit_price: float,
    status: str,
    fee_bps: float,
    ambiguous: bool,
) -> CipherScreenTrade:
    sign = 1.0 if side == "long" else -1.0
    gross = sign * (exit_price / entry - 1.0) * 10_000.0
    return CipherScreenTrade(
        _timestamp_ms(signal_time),
        _timestamp_ms(entry_time),
        _timestamp_ms(outcome_time),
        side,
        entry,
        exit_price,
        status,
        gross,
        fee_bps,
        gross - fee_bps,
        ambiguous,
    )


def _summarize(
    candidate: str,
    spec: CipherExitSpec,
    trades: list[CipherScreenTrade],
    expired: int,
    censored: int,
) -> CipherScreenTrial:
    net = [trade.net_return_bps for trade in trades]
    profits = sum(value for value in net if value > 0.0)
    losses = -sum(value for value in net if value < 0.0)
    return CipherScreenTrial(
        candidate,
        spec,
        tuple(trades),
        len(trades),
        sum(value > 0.0 for value in net),
        sum(value < 0.0 for value in net),
        sum(net),
        profits / losses if losses > 0.0 else None,
        _max_drawdown(net),
        sum(trade.fee_bps for trade in trades),
        expired,
        censored,
        sum(trade.status == "timeout" for trade in trades),
        sum(trade.ambiguous for trade in trades),
        _monthly_net(trades),
    )


def _max_drawdown(returns: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _monthly_net(trades: list[CipherScreenTrade]) -> dict[str, float]:
    output: dict[str, float] = {}
    for trade in trades:
        month = datetime.fromtimestamp(trade.outcome_ts_ms / 1_000.0, tz=UTC).strftime(
            "%Y-%m"
        )
        output[month] = output.get(month, 0.0) + trade.net_return_bps
    return output


def _timestamp_ms(timestamp: pd.Timestamp) -> int:
    return int(timestamp.timestamp() * 1_000)
