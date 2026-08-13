"""Complete-cell evaluation for bounded low-timeframe research."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

import pandas as pd

from hypervector.research.low_tf_multi_asset_contract import complete_ohlcv_bars
from hypervector.research.low_tf_multi_asset_cells import declared_low_tf_cells
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)
from hypervector.research.low_tf_multi_asset_replay import evaluate_low_tf_replay
from hypervector.research.low_tf_multi_asset_replay_models import LowTfReplayConfig
from hypervector.research.low_tf_multi_asset_features import (
    LowTfFeatureConfig,
    build_low_tf_features,
)
from hypervector.research.low_tf_multi_asset_signals import (
    LowTfSignalConfig,
    build_low_tf_signals,
)

ScreenSegment = Literal["development", "validation", "pseudo_holdout"]


@dataclass(frozen=True)
class LowTfScreenCell:
    """One immutable strategy-cell summary in the research ledger."""

    segment: ScreenSegment
    symbol: str
    family: str
    side: str
    exit_variant: str
    signal_count: int
    completed_trades: int
    wins: int
    losses: int
    initial_equity: float
    final_equity: float
    gross_pnl_usd: float
    total_fees_usd: float
    funding_cashflow_usd: float
    liquidation_penalties_usd: float
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    liquidations: int
    same_minute_ambiguities: int
    rejection_count: int
    trade_records: tuple[dict[str, object], ...]
    execution_authority: str = "none"


@dataclass(frozen=True)
class LowTfScreenAssetInput:
    """Explicit venue-matched paths and leverage identity for one asset."""

    symbol: str
    venue_max_leverage: float
    bars_path: Path
    funding_paths: tuple[Path, ...]


@dataclass(frozen=True)
class LowTfAssetWindowRun:
    """One asset's complete-cell results and immutable source identity."""

    source_identity: dict[str, object]
    cells: tuple[LowTfScreenCell, ...]


def build_low_tf_screen_artifact(
    *,
    run_id: str,
    segment: ScreenSegment,
    start: pd.Timestamp,
    end: pd.Timestamp,
    asset_runs: tuple[LowTfAssetWindowRun, ...],
) -> dict[str, object]:
    """Return a compact complete-cell JSON summary with immutable provenance."""
    start_utc, end_utc = _validated_window(start, end)
    if not run_id.strip() or not asset_runs:
        raise ValueError("screen artifact requires a run ID and asset results")
    cells = tuple(cell for run in asset_runs for cell in run.cells)
    if any(cell.segment != segment for cell in cells):
        raise ValueError("screen artifact cell segment mismatch")
    source_identity = _asset_source_identity(asset_runs)
    summaries = tuple(_compact_cell(cell) for cell in cells)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "segment": segment,
        "start_utc": start_utc.isoformat(),
        "end_utc": end_utc.isoformat(),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "source_identity": source_identity,
        "trial_count": len(summaries),
        "cells": summaries,
        "trade_storage": "DuckDB low_tf_screen_trades",
    }


def _asset_source_identity(
    runs: tuple[LowTfAssetWindowRun, ...],
) -> dict[str, dict[str, object]]:
    """Index unique source identities by explicit symbol."""
    indexed: dict[str, dict[str, object]] = {}
    for run in runs:
        symbol = run.source_identity.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("asset source identity requires a symbol")
        if symbol in indexed:
            raise ValueError(f"duplicate asset source identity: {symbol}")
        indexed[symbol] = run.source_identity
    return indexed


def _compact_cell(cell: LowTfScreenCell) -> dict[str, object]:
    """Return a JSON cell summary while leaving trade rows in DuckDB."""
    values = asdict(cell)
    values.pop("trade_records")
    return values


def evaluate_low_tf_asset_window(
    *,
    asset: LowTfScreenAssetInput,
    start: pd.Timestamp,
    end: pd.Timestamp,
    segment: ScreenSegment,
    feature_config: LowTfFeatureConfig,
    signal_config: LowTfSignalConfig,
    replay_config: LowTfReplayConfig,
) -> LowTfAssetWindowRun:
    """Load, validate, feature, signal, and replay one explicit asset window."""
    start_utc, end_utc = _validated_window(start, end)
    _validate_asset_input(asset, replay_config)
    complete_minutes, all_minutes = _load_asset_bars(
        asset.bars_path, start_utc, end_utc
    )
    funding = load_verified_hourly_funding(
        list(asset.funding_paths), start_utc, end_utc
    )
    replay_minutes = attach_hourly_funding(
        complete_minutes.set_index("timestamp"), funding
    ).reset_index()
    features, signals = _window_features_signals(
        all_minutes,
        start_utc,
        end_utc,
        asset.symbol,
        feature_config,
        signal_config,
    )
    cells = evaluate_low_tf_cells(
        minute_bars=replay_minutes,
        features=features,
        signals=signals,
        symbol=asset.symbol,
        segment=segment,
        config=replay_config,
    )
    identity = _source_identity(
        asset,
        complete_minutes,
        all_minutes,
        funding,
        start_utc,
        feature_config,
        signal_config,
        replay_config,
    )
    return LowTfAssetWindowRun(identity, cells)


def _validated_window(
    start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return ordered UTC window endpoints or reject ambiguity."""
    start_utc, end_utc = pd.Timestamp(start), pd.Timestamp(end)
    if start_utc.tz is None or end_utc.tz is None:
        raise ValueError("low-timeframe screen window must be timezone-aware")
    start_utc = start_utc.tz_convert("UTC")
    end_utc = end_utc.tz_convert("UTC")
    if start_utc >= end_utc:
        raise ValueError("low-timeframe screen start must precede end")
    return start_utc, end_utc


def _validate_asset_input(
    asset: LowTfScreenAssetInput, config: LowTfReplayConfig
) -> None:
    """Validate explicit paths, symbol, and venue leverage consistency."""
    if not asset.symbol or asset.symbol != asset.symbol.upper():
        raise ValueError("screen asset symbol must be non-empty uppercase text")
    if asset.venue_max_leverage != config.venue_max_leverage:
        raise ValueError("screen asset and replay venue leverage must match")
    if not asset.bars_path.is_file():
        raise FileNotFoundError(f"screen bars do not exist: {asset.bars_path}")
    if not asset.funding_paths:
        raise ValueError("screen requires explicit funding paths")


def _load_asset_bars(
    path: Path, start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load venue bars and require an exact one-minute scored window."""
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume", "source"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"screen bars missing columns: {missing}")
    times = pd.DatetimeIndex(frame["timestamp"])
    if times.tz is None or not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("screen bars require ordered unique aware timestamps")
    if not frame["source"].isin({"hl", "hl_gap_fill"}).all():
        raise ValueError("screen bars contain a non-Hyperliquid source")
    window = frame.loc[(times >= start) & (times < end)].copy()
    expected = pd.date_range(start, end, freq="1min", inclusive="left")
    if not pd.DatetimeIndex(window["timestamp"]).equals(expected):
        raise ValueError("screen bars do not cover the exact one-minute window")
    return window.reset_index(drop=True), frame.reset_index(drop=True)


def _window_features_signals(
    minutes: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    symbol: str,
    feature_config: LowTfFeatureConfig,
    signal_config: LowTfSignalConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build full-history features then retain causal decisions in the window."""
    bars = complete_ohlcv_bars(minutes, source_minutes=1, bar_minutes=5)
    features = build_low_tf_features(bars, feature_config)
    signals = build_low_tf_signals(features, symbol=symbol, config=signal_config)
    scored_features = features.loc[
        features["bar_open_at"].ge(start) & features["bar_open_at"].lt(end)
    ].copy()
    decision_times = pd.to_datetime(signals["decision_time_utc"], utc=True)
    scored_signals = signals.loc[
        decision_times.ge(start) & decision_times.lt(end)
    ].copy()
    return scored_features.reset_index(drop=True), scored_signals.reset_index(drop=True)


def _source_identity(
    asset: LowTfScreenAssetInput,
    window: pd.DataFrame,
    all_minutes: pd.DataFrame,
    funding: pd.Series,
    start: pd.Timestamp,
    feature_config: LowTfFeatureConfig,
    signal_config: LowTfSignalConfig,
    replay_config: LowTfReplayConfig,
) -> dict[str, object]:
    """Return immutable input and configuration provenance for one asset."""
    first = pd.Timestamp(all_minutes["timestamp"].iloc[0])
    return {
        "symbol": asset.symbol,
        "bars_path": str(asset.bars_path.resolve()),
        "bars_sha256": _file_sha256(asset.bars_path),
        "funding_paths": [str(path.resolve()) for path in asset.funding_paths],
        "funding_sha256": [_file_sha256(path) for path in asset.funding_paths],
        "bar_rows": len(window),
        "gap_fill_rows": int(window["source"].eq("hl_gap_fill").sum()),
        "funding_events": len(funding),
        "leading_warmup_minutes": max(0, int((start - first).total_seconds() // 60)),
        "feature_config": asdict(feature_config),
        "signal_config": asdict(signal_config),
        "replay_config": asdict(replay_config),
        "execution_authority": "none",
    }


def _file_sha256(path: Path) -> str:
    """Return the SHA-256 identity of one immutable source file."""
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_low_tf_cells(
    *,
    minute_bars: pd.DataFrame,
    features: pd.DataFrame,
    signals: pd.DataFrame,
    symbol: str,
    segment: ScreenSegment,
    config: LowTfReplayConfig,
) -> tuple[LowTfScreenCell, ...]:
    """Evaluate every declared cell and preserve explicit zero-signal rows."""
    _validate_screen_inputs(signals, symbol)
    cells: list[LowTfScreenCell] = []
    for family, side, variant in declared_low_tf_cells():
        selected = signals.loc[
            signals["family"].eq(family)
            & signals["side"].eq(side)
            & signals["exit_variant"].eq(variant)
        ].copy()
        if selected.empty:
            cells.append(_empty_cell(segment, symbol, family, side, variant, config))
            continue
        report = evaluate_low_tf_replay(minute_bars, features, selected, config)
        cells.append(
            LowTfScreenCell(
                segment,
                symbol,
                family,
                side,
                variant,
                len(selected),
                report.completed_trades,
                report.wins,
                report.losses,
                report.initial_equity,
                report.final_equity,
                report.gross_pnl_usd,
                report.total_fees_usd,
                report.funding_cashflow_usd,
                report.liquidation_penalties_usd,
                report.net_pnl_usd,
                report.profit_factor,
                report.maximum_drawdown_pct,
                report.liquidations,
                report.same_minute_ambiguities,
                len(report.rejections),
                tuple(asdict(trade) for trade in report.trades),
            )
        )
    return tuple(cells)


def _validate_screen_inputs(signals: pd.DataFrame, symbol: str) -> None:
    """Reject ambiguous symbol identities and incomplete signal columns."""
    if not symbol or symbol != symbol.upper():
        raise ValueError("screen symbol must be non-empty uppercase text")
    required = {"symbol", "family", "side", "exit_variant"}
    missing = sorted(required.difference(signals.columns))
    if missing:
        raise ValueError(f"screen signals missing identity columns: {missing}")
    if not signals.empty and not signals["symbol"].eq(symbol).all():
        raise ValueError("screen signals contain a different symbol")


def _empty_cell(
    segment: ScreenSegment,
    symbol: str,
    family: str,
    side: str,
    variant: str,
    config: LowTfReplayConfig,
) -> LowTfScreenCell:
    """Return an explicit zero-signal cell without fabricating a replay."""
    return LowTfScreenCell(
        segment,
        symbol,
        family,
        side,
        variant,
        0,
        0,
        0,
        0,
        config.initial_equity,
        config.initial_equity,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        None,
        0.0,
        0,
        0,
        0,
        (),
    )
