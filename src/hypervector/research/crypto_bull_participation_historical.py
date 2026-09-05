"""Verified historical inputs and controls for crypto bull participation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.research.crypto_bull_participation_models import (
    CryptoBullParticipationConfig,
    CryptoBullPortfolioReport,
    CryptoBullTrade,
)
from hypervector.research.crypto_bull_participation_experiment import (
    CryptoBullExperimentCell,
    CryptoBullExperimentResult,
    PartitionName,
    ScenarioName,
    build_crypto_bull_experiment_report,
)
from hypervector.research.crypto_bull_participation_replay import (
    evaluate_crypto_bull_portfolio,
)
from hypervector.research.crypto_bull_participation_signals import (
    build_crypto_bull_decisions,
)
from hypervector.research.market_cipher_data import load_verified_hourly_funding

_OHLC = ("open", "high", "low", "close")
_START = pd.Timestamp("2025-07-28T00:00:00Z")
_END = pd.Timestamp("2026-07-28T00:00:00Z")
_FUNDING_WINDOW = "20250728T000000000000Z_20260728T000000000000Z_funding"


@dataclass(frozen=True)
class CryptoBullHistoricalInputs:
    """Aligned year-long minute, hourly decision, and funding inputs."""

    minutes: dict[str, pd.DataFrame]
    decisions: dict[str, pd.DataFrame]
    funding: dict[str, pd.Series]
    source_paths: tuple[Path, ...]
    source_identity: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class CryptoBullHistoricalPartition:
    """One exact chronological evaluation window."""

    name: PartitionName
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp


def frozen_crypto_bull_partitions() -> tuple[CryptoBullHistoricalPartition, ...]:
    """Return the single preregistered chronological partition contract."""
    return (
        CryptoBullHistoricalPartition(
            "development", _START, pd.Timestamp("2026-01-28T00:00:00Z")
        ),
        CryptoBullHistoricalPartition(
            "validation",
            pd.Timestamp("2026-01-28T00:00:00Z"),
            pd.Timestamp("2026-04-28T00:00:00Z"),
        ),
        CryptoBullHistoricalPartition(
            "pseudo_holdout", pd.Timestamp("2026-04-28T00:00:00Z"), _END
        ),
    )


def run_crypto_bull_participation_historical(
    inputs: CryptoBullHistoricalInputs,
    config: CryptoBullParticipationConfig | None = None,
) -> CryptoBullExperimentResult:
    """Run every frozen partition and cost scenario without performance aborts."""
    cfg = config or CryptoBullParticipationConfig()
    cells: list[CryptoBullExperimentCell] = []
    for partition in frozen_crypto_bull_partitions():
        market, decisions, funding = _partition_inputs(inputs, partition, cfg)
        for scenario, slippage in _cost_scenarios():
            scenario_config = replace(cfg, adverse_slippage_bps_per_side=slippage)
            candidate = evaluate_crypto_bull_portfolio(
                market, decisions, funding, scenario_config
            )
            baseline = evaluate_continuous_long_baseline(
                market, funding, scenario_config
            )
            cells.append(
                CryptoBullExperimentCell(partition.name, scenario, candidate, baseline)
            )
    return build_crypto_bull_experiment_report(cells)


def load_crypto_bull_historical_inputs(
    project_root: Path,
    config: CryptoBullParticipationConfig | None = None,
) -> CryptoBullHistoricalInputs:
    """Load the four exact preregistered market and funding archives."""
    cfg = config or CryptoBullParticipationConfig()
    minutes: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.Series] = {}
    source_identity: dict[str, dict[str, object]] = {}
    paths: list[Path] = []
    for symbol in cfg.symbols:
        minute_path = project_root / "data" / "cache" / f"{symbol}_1m_365d.parquet"
        funding_path = _funding_path(project_root, symbol)
        minutes[symbol] = load_verified_crypto_minutes(minute_path, _START, _END)
        source_identity[symbol] = {
            "source_counts": minutes[symbol].attrs["source_counts"],
            "maximum_gap_fill_run": minutes[symbol].attrs["maximum_gap_fill_run"],
        }
        funding[symbol] = load_verified_hourly_funding([funding_path], _START, _END)
        paths.extend((minute_path, funding_path))
    hourly = {
        symbol: build_completed_hour_bars(frame) for symbol, frame in minutes.items()
    }
    decisions = build_crypto_bull_decisions(hourly, cfg)
    return CryptoBullHistoricalInputs(
        minutes, decisions, funding, tuple(paths), source_identity
    )


def load_verified_crypto_minutes(
    path: Path, start_utc: pd.Timestamp, end_utc: pd.Timestamp
) -> pd.DataFrame:
    """Load one exact, contiguous, authentic Hyperliquid minute grid."""
    start, end = _validated_window(start_utc, end_utc)
    if not path.is_file():
        raise FileNotFoundError(f"crypto minute parquet does not exist: {path}")
    frame = pd.read_parquet(path)
    required = {"timestamp", "source", *_OHLC}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"crypto minute parquet missing columns: {missing}")
    output = frame.loc[:, ["timestamp", *_OHLC, "source"]].copy()
    output["timestamp"] = pd.to_datetime(output["timestamp"], utc=True)
    output = output.loc[output["timestamp"].between(start, end, inclusive="left")]
    output = output.set_index("timestamp")
    _validate_minute_values(output)
    expected = pd.date_range(start, end, freq="min", inclusive="left")
    if not output.index.equals(expected):
        raise ValueError("crypto minute grid differs from the required exact coverage")
    prices = output.loc[:, _OHLC].astype(float)
    prices.attrs["source_counts"] = {
        source: int(count)
        for source, count in output["source"].value_counts().sort_index().items()
    }
    prices.attrs["maximum_gap_fill_run"] = _maximum_gap_fill_run(output["source"])
    return prices


def build_completed_hour_bars(minutes: pd.DataFrame) -> pd.DataFrame:
    """Aggregate complete left-labeled half-open sixty-minute bars."""
    if not isinstance(minutes.index, pd.DatetimeIndex) or minutes.index.tz is None:
        raise ValueError("minute frame requires a timezone-aware index")
    grouped = minutes.resample("1h", label="left", closed="left")
    counts = grouped["close"].count()
    if counts.empty or not counts.eq(60).all():
        raise ValueError("completed hourly bars require exactly sixty source minutes")
    return grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )


def evaluate_continuous_long_baseline(
    minute_by_symbol: Mapping[str, pd.DataFrame],
    funding_by_symbol: Mapping[str, pd.Series],
    config: CryptoBullParticipationConfig,
) -> CryptoBullPortfolioReport:
    """Evaluate the nonselectable equal-weight buy-and-hold beta control."""
    minutes, funding = _validated_baseline_inputs(
        minute_by_symbol, funding_by_symbol, config
    )
    positions = _baseline_positions(minutes, config)
    funding_cashflows = _baseline_funding(positions, minutes, funding)
    trades = _baseline_trades(positions, minutes, funding_cashflows, config)
    marked = _baseline_marked_equity(positions, minutes, funding, config)
    final_equity = config.initial_equity_usd + sum(
        trade.net_pnl_usd for trade in trades
    )
    return CryptoBullPortfolioReport(
        initial_equity_usd=config.initial_equity_usd,
        final_equity_usd=final_equity,
        net_pnl_usd=final_equity - config.initial_equity_usd,
        maximum_drawdown_pct=_maximum_drawdown_pct(marked, final_equity),
        maximum_concurrent_positions=len(config.symbols),
        maximum_margin_fraction=config.margin_fraction_per_position
        * len(config.symbols),
        simultaneous_stop_wave_loss_usd=0.0,
        turnover_usd=sum(
            trade.notional_usd + trade.quantity * trade.exit_price for trade in trades
        ),
        exposure_minutes=len(next(iter(minutes.values()))),
        available_minutes=len(next(iter(minutes.values()))),
        trades=trades,
    )


@dataclass(frozen=True)
class _BaselinePosition:
    symbol: str
    entry_price: float
    raw_entry_price: float
    quantity: float
    margin_usd: float
    notional_usd: float
    entry_fee_usd: float


def _baseline_positions(
    minutes: Mapping[str, pd.DataFrame], config: CryptoBullParticipationConfig
) -> tuple[_BaselinePosition, ...]:
    output: list[_BaselinePosition] = []
    for symbol in config.symbols:
        raw = float(minutes[symbol].iloc[0]["open"])
        entry = raw * (1.0 + config.adverse_slippage_bps_per_side / 10_000.0)
        margin = config.initial_equity_usd * config.margin_fraction_per_position
        notional = margin * config.leverage
        output.append(
            _BaselinePosition(
                symbol,
                entry,
                raw,
                notional / entry,
                margin,
                notional,
                notional * config.entry_fee_bps / 10_000.0,
            )
        )
    return tuple(output)


def _baseline_funding(
    positions: tuple[_BaselinePosition, ...],
    minutes: Mapping[str, pd.DataFrame],
    funding: Mapping[str, pd.Series],
) -> dict[str, float]:
    output: dict[str, float] = {}
    first = next(iter(minutes.values())).index[0]
    for position in positions:
        rates = funding[position.symbol].loc[funding[position.symbol].index > first]
        marks = minutes[position.symbol].loc[rates.index, "open"].astype(float)
        output[position.symbol] = float((-position.quantity * marks * rates).sum())
    return output


def _baseline_trades(
    positions: tuple[_BaselinePosition, ...],
    minutes: Mapping[str, pd.DataFrame],
    funding_cashflows: Mapping[str, float],
    config: CryptoBullParticipationConfig,
) -> tuple[CryptoBullTrade, ...]:
    running_equity = config.initial_equity_usd
    output: list[CryptoBullTrade] = []
    for position in positions:
        trade = _baseline_trade(
            position, minutes, funding_cashflows, config, running_equity
        )
        running_equity += trade.net_pnl_usd
        output.append(trade)
    return tuple(output)


def _baseline_trade(
    position: _BaselinePosition,
    minutes: Mapping[str, pd.DataFrame],
    funding_cashflows: Mapping[str, float],
    config: CryptoBullParticipationConfig,
    equity_before: float,
) -> CryptoBullTrade:
    frame = minutes[position.symbol]
    raw_exit = float(frame.iloc[-1]["close"])
    exit_price = raw_exit * (1.0 - config.adverse_slippage_bps_per_side / 10_000.0)
    exit_fee = position.quantity * exit_price * config.exit_fee_bps / 10_000.0
    gross = position.quantity * (exit_price - position.entry_price)
    fees = position.entry_fee_usd + exit_fee
    funding = funding_cashflows[position.symbol]
    net = gross - fees + funding
    slippage = position.quantity * (
        position.entry_price - position.raw_entry_price + raw_exit - exit_price
    )
    return CryptoBullTrade(
        symbol=position.symbol,
        entry_time_utc=frame.index[0].isoformat(),
        exit_time_utc=frame.index[-1].isoformat(),
        entry_price=position.entry_price,
        exit_price=exit_price,
        quantity=position.quantity,
        margin_usd=position.margin_usd,
        notional_usd=position.notional_usd,
        gross_pnl_usd=gross,
        fees_usd=fees,
        funding_cashflow_usd=funding,
        slippage_cost_usd=slippage,
        net_pnl_usd=net,
        holding_minutes=len(frame) - 1,
        exit_reason="end_of_data",
        initial_stop_price=0.0,
        final_stop_price=0.0,
        highest_completed_hour_price=float(frame["high"].max()),
        equity_before_usd=equity_before,
        equity_after_usd=equity_before + net,
    )


def _baseline_marked_equity(
    positions: tuple[_BaselinePosition, ...],
    minutes: Mapping[str, pd.DataFrame],
    funding: Mapping[str, pd.Series],
    config: CryptoBullParticipationConfig,
) -> pd.Series:
    index = next(iter(minutes.values())).index
    marked = pd.Series(config.initial_equity_usd, index=index, dtype=float)
    for position in positions:
        marked -= position.entry_fee_usd
        marked += position.quantity * (
            minutes[position.symbol]["close"].astype(float) - position.entry_price
        )
        events = pd.Series(0.0, index=index)
        rates = funding[position.symbol].loc[funding[position.symbol].index > index[0]]
        marks = minutes[position.symbol].loc[rates.index, "open"].astype(float)
        events.loc[rates.index] = -position.quantity * marks * rates
        marked += events.cumsum()
    return marked


def _maximum_drawdown_pct(marked: pd.Series, final_equity: float) -> float:
    combined = pd.concat([marked, pd.Series([final_equity])], ignore_index=True)
    peaks = combined.cummax()
    return float((100.0 * (combined / peaks - 1.0)).min())


def _validated_baseline_inputs(
    minute_values: Mapping[str, pd.DataFrame],
    funding_values: Mapping[str, pd.Series],
    config: CryptoBullParticipationConfig,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.Series]]:
    expected = set(config.symbols)
    if set(minute_values) != expected or set(funding_values) != expected:
        raise ValueError("baseline inputs differ from the configured symbols")
    minutes = {symbol: minute_values[symbol].copy() for symbol in config.symbols}
    funding = {symbol: funding_values[symbol].copy() for symbol in config.symbols}
    index = minutes[config.symbols[0]].index
    for symbol in config.symbols:
        _validate_replay_frame(minutes[symbol], symbol)
        if not minutes[symbol].index.equals(index):
            raise ValueError("baseline minute indexes must be aligned")
        if len(funding[symbol].index.difference(index)):
            raise ValueError(f"{symbol} funding timestamps are outside minute coverage")
    return minutes, funding


def _validate_replay_frame(frame: pd.DataFrame, symbol: str) -> None:
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f"{symbol} minute index must be timezone-aware")
    if (
        frame.empty
        or frame.index.has_duplicates
        or not frame.index.is_monotonic_increasing
    ):
        raise ValueError(
            f"{symbol} minute frame must be unique, ordered, and non-empty"
        )
    missing = sorted(set(_OHLC).difference(frame.columns))
    if missing:
        raise ValueError(f"{symbol} minute frame missing columns: {missing}")


def _validate_minute_values(frame: pd.DataFrame) -> None:
    if (
        frame.empty
        or frame.index.has_duplicates
        or not frame.index.is_monotonic_increasing
    ):
        raise ValueError("crypto minutes must be unique, ordered, and non-empty")
    sources = set(frame["source"].astype(str))
    unsupported = sorted(sources.difference({"hl", "hl_gap_fill"}))
    if unsupported:
        raise ValueError(
            f"crypto minute parquet contains unsupported source: {unsupported}"
        )
    if _maximum_gap_fill_run(frame["source"]) > 30:
        raise ValueError("crypto minute gap-fill run exceeds thirty minutes")
    numeric = frame.loc[:, _OHLC].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(numeric.to_numpy()).all() or (numeric <= 0.0).any().any():
        raise ValueError("crypto minute OHLC must be finite and positive")


def _validated_window(
    start_utc: pd.Timestamp, end_utc: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = pd.Timestamp(start_utc), pd.Timestamp(end_utc)
    if start.tz is None or end.tz is None:
        raise ValueError("crypto historical window must be timezone-aware")
    start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
    if start >= end:
        raise ValueError("crypto historical start must precede end")
    return start, end


def _funding_path(project_root: Path, symbol: str) -> Path:
    return (
        project_root
        / "data"
        / "cache"
        / "vendor"
        / "hyperliquid"
        / symbol
        / _FUNDING_WINDOW
        / "funding.parquet"
    )


def _maximum_gap_fill_run(source: pd.Series) -> int:
    gap = source.astype(str).eq("hl_gap_fill")
    if not bool(gap.any()):
        return 0
    runs = gap.groupby((~gap).cumsum()).sum()
    return int(runs.max())


def _partition_inputs(
    inputs: CryptoBullHistoricalInputs,
    partition: CryptoBullHistoricalPartition,
    config: CryptoBullParticipationConfig,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.Series]]:
    market: dict[str, pd.DataFrame] = {}
    decisions: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.Series] = {}
    for symbol in config.symbols:
        market[symbol] = inputs.minutes[symbol].loc[
            partition.start_utc : partition.end_utc - pd.Timedelta(minutes=1)
        ]
        index = market[symbol].index
        decisions[symbol] = inputs.decisions[symbol].loc[
            inputs.decisions[symbol].index.intersection(index)
        ]
        funding[symbol] = inputs.funding[symbol].loc[
            (inputs.funding[symbol].index >= partition.start_utc)
            & (inputs.funding[symbol].index < partition.end_utc)
        ]
    return market, decisions, funding


def _cost_scenarios() -> tuple[tuple[ScenarioName, float], ...]:
    return (("nominal", 2.0), ("stress", 10.0))
