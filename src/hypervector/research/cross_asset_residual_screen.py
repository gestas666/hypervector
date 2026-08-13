"""Complete-cell cross-asset residual development screen."""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import UTC, datetime
import math

import numpy as np
import pandas as pd

from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
    ResidualPairReport,
    ResidualSignal,
    ResidualTrade,
    declared_residual_pairs,
)
from hypervector.research.cross_asset_residual_gap_audit import (
    build_residual_gap_audit,
)
from hypervector.research.cross_asset_residual_replay import evaluate_residual_pair
from hypervector.research.cross_asset_residual_signal import (
    build_residual_signals,
    build_residual_states,
)
from hypervector.research.low_tf_multi_asset_contract import complete_ohlcv_bars

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_MINUTE_COLUMNS = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "funding_rate",
}


def build_residual_screen(
    *,
    minute_frames: dict[str, pd.DataFrame],
    config: CrossAssetResidualConfig,
    run_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    source_identity: dict[str, dict[str, object]],
) -> tuple[dict[str, object], pd.DataFrame]:
    """Evaluate all six independent pair cells and return immutable payloads."""
    start_utc, end_utc = _validated_window(start, end)
    frames = _validated_frames(minute_frames, start_utc, end_utc)
    _validate_source_identity(source_identity)
    closes = {symbol: _five_minute_close(frame) for symbol, frame in frames.items()}
    reports: list[ResidualPairReport] = []
    diagnostics: list[dict[str, object]] = []
    gap_audits: list[dict[str, object]] = []
    for left, right in declared_residual_pairs():
        states = build_residual_states(closes[left], closes[right], left, right, config)
        scored = _scored_states(states, end_utc)
        signals = build_residual_signals(scored, config)
        pair_frames = {left: frames[left], right: frames[right]}
        report = evaluate_residual_pair(
            minute_bars=pair_frames,
            states=scored.loc[scored["zscore"].notna()],
            signals=signals,
            config=config,
        )
        reports.append(report)
        gap_audits.append(
            build_residual_gap_audit(
                left_symbol=left,
                right_symbol=right,
                minute_frames=pair_frames,
                signals=signals,
                trades=report.trades,
            )
        )
        diagnostics.append(_diagnostic_cell(left, right, scored, signals))
    artifact = _artifact(
        run_id,
        start_utc,
        end_utc,
        config,
        source_identity,
        reports,
        diagnostics,
        gap_audits,
    )
    return artifact, _trade_rows(reports)


def build_residual_exit_surface(
    *,
    minute_frames: dict[str, pd.DataFrame],
    variants: tuple[tuple[str, CrossAssetResidualConfig], ...],
    run_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    source_identity: dict[str, dict[str, object]],
) -> tuple[dict[str, object], pd.DataFrame]:
    """Evaluate one global stop/hold surface without changing signal identity."""
    start_utc, end_utc = _validated_window(start, end)
    declared = _validated_variants(variants)
    frames = _validated_frames(minute_frames, start_utc, end_utc)
    _validate_source_identity(source_identity)
    closes = {symbol: _five_minute_close(frame) for symbol, frame in frames.items()}
    runs: list[tuple[str, ResidualPairReport]] = []
    diagnostics: list[dict[str, object]] = []
    gap_audits: list[dict[str, object]] = []
    signal_config = declared[0][1]
    for left, right in declared_residual_pairs():
        states = build_residual_states(
            closes[left], closes[right], left, right, signal_config
        )
        scored = _scored_states(states, end_utc)
        signals = build_residual_signals(scored, signal_config)
        diagnostics.append(_diagnostic_cell(left, right, scored, signals))
        for trial_id, config in declared:
            pair_frames = {left: frames[left], right: frames[right]}
            report = evaluate_residual_pair(
                minute_bars=pair_frames,
                states=scored.loc[scored["zscore"].notna()],
                signals=signals,
                config=config,
            )
            runs.append((trial_id, report))
            audit = build_residual_gap_audit(
                left_symbol=left,
                right_symbol=right,
                minute_frames=pair_frames,
                signals=signals,
                trades=report.trades,
            )
            gap_audits.append({"trial_id": trial_id, **audit})
    artifact = _surface_artifact(
        run_id,
        start_utc,
        end_utc,
        declared,
        source_identity,
        runs,
        diagnostics,
        gap_audits,
    )
    return artifact, _surface_trade_rows(runs)


def _validated_window(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_utc, end_utc = pd.Timestamp(start), pd.Timestamp(end)
    if start_utc.tz is None or end_utc.tz is None:
        raise ValueError("residual screen window must be timezone-aware")
    start_utc, end_utc = start_utc.tz_convert("UTC"), end_utc.tz_convert("UTC")
    if start_utc >= end_utc:
        raise ValueError("residual screen start must precede end")
    return start_utc, end_utc


def _validated_frames(
    frames: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    if tuple(frames) != _SYMBOLS:
        raise ValueError("residual screen requires ordered BTC/ETH/SOL/HYPE frames")
    expected = pd.date_range(start, end, freq="1min", inclusive="left")
    return {
        symbol: _validated_frame(frame, symbol, expected)
        for symbol, frame in frames.items()
    }


def _validated_frame(
    frame: pd.DataFrame,
    symbol: str,
    expected: pd.DatetimeIndex,
) -> pd.DataFrame:
    missing = sorted(_MINUTE_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"{symbol} residual source missing columns: {missing}")
    times = pd.DatetimeIndex(frame["timestamp"])
    if not times.equals(expected):
        raise ValueError(f"{symbol} residual source does not cover the exact window")
    if not frame["source"].isin({"hl", "hl_gap_fill"}).all():
        raise ValueError(f"{symbol} residual source is not Hyperliquid-native")
    values = frame[["open", "high", "low", "close", "volume", "funding_rate"]]
    numeric = values.to_numpy(float)
    if not np.isfinite(numeric).all() or (numeric[:, :4] <= 0.0).any():
        raise ValueError(f"{symbol} residual source contains invalid values")
    return frame.copy().reset_index(drop=True)


def _validate_source_identity(identity: dict[str, dict[str, object]]) -> None:
    if tuple(identity) != _SYMBOLS:
        raise ValueError("residual source identity must cover all four symbols")
    if any(not values for values in identity.values()):
        raise ValueError("residual source identity entries cannot be empty")


def _five_minute_close(frame: pd.DataFrame) -> pd.Series:
    bars = complete_ohlcv_bars(frame, source_minutes=1, bar_minutes=5)
    return bars.set_index("bar_open_at")["close"].astype(float)


def _scored_states(states: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    decisions = pd.to_datetime(states["decision_time_utc"], utc=True)
    return states.loc[decisions.lt(end)].copy().reset_index(drop=True)


def _diagnostic_cell(
    left: str,
    right: str,
    states: pd.DataFrame,
    signals: tuple[ResidualSignal, ...],
) -> dict[str, object]:
    admitted = states["stationarity_admitted"].fillna(False).astype(bool)
    finite_z = states["zscore"].map(lambda value: math.isfinite(float(value)))
    directions = [signal.direction for signal in signals]
    return {
        "left_symbol": left,
        "right_symbol": right,
        "state_rows": len(states),
        "resolved_state_rows": int(finite_z.sum()),
        "stationarity_admitted_rows": int(admitted.sum()),
        "long_spread_signals": directions.count("long_spread"),
        "short_spread_signals": directions.count("short_spread"),
    }


def _artifact(
    run_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    config: CrossAssetResidualConfig,
    source_identity: dict[str, dict[str, object]],
    reports: list[ResidualPairReport],
    diagnostics: list[dict[str, object]],
    gap_audits: list[dict[str, object]],
) -> dict[str, object]:
    if not run_id.strip():
        raise ValueError("residual screen run ID cannot be empty")
    return {
        "schema_version": "cross_asset_residual_development_v2",
        "run_id": run_id,
        "segment": "development",
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "independent_pair_accounts": True,
        "trial_count": len(reports),
        "config": asdict(config),
        "source_identity": source_identity,
        "diagnostics": diagnostics,
        "gap_audits": gap_audits,
        "cells": [_compact_report(report) for report in reports],
        "trade_storage": "Parquet sidecar declared by command runner",
        "limitations": [
            "pair cells use independent research accounts and cannot be summed",
            "fixed friction does not reconstruct queue position or asynchronous leg risk",
            "development evidence cannot establish out-of-sample profitability",
            "gap audits identify dependence but cannot reconstruct missing venue paths",
        ],
    }


def _compact_report(report: ResidualPairReport) -> dict[str, object]:
    values = report.to_dict()
    values.pop("trades")
    return values


def _trade_rows(reports: list[ResidualPairReport]) -> pd.DataFrame:
    rows = [asdict(trade) for report in reports for trade in report.trades]
    columns = [value.name for value in fields(ResidualTrade)]
    return pd.DataFrame.from_records(rows, columns=columns)


def _validated_variants(
    variants: tuple[tuple[str, CrossAssetResidualConfig], ...],
) -> tuple[tuple[str, CrossAssetResidualConfig], ...]:
    if not variants or any(not trial_id.strip() for trial_id, _ in variants):
        raise ValueError("residual exit surface requires named variants")
    identifiers = [trial_id for trial_id, _ in variants]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("residual exit surface trial IDs must be unique")
    expected = _signal_contract(variants[0][1])
    if any(_signal_contract(config) != expected for _, config in variants[1:]):
        raise ValueError("residual exit variants must share one signal contract")
    return variants


def _signal_contract(config: CrossAssetResidualConfig) -> dict[str, object]:
    values = asdict(config)
    values.pop("stop_z")
    values.pop("maximum_hold_bars")
    return values


def _surface_artifact(
    run_id: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    variants: tuple[tuple[str, CrossAssetResidualConfig], ...],
    source_identity: dict[str, dict[str, object]],
    runs: list[tuple[str, ResidualPairReport]],
    diagnostics: list[dict[str, object]],
    gap_audits: list[dict[str, object]],
) -> dict[str, object]:
    if not run_id.strip():
        raise ValueError("residual exit surface run ID cannot be empty")
    return {
        "schema_version": "cross_asset_residual_exit_surface_v2",
        "run_id": run_id,
        "segment": "development",
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "independent_pair_accounts": True,
        "trial_count": len(runs),
        "signal_contract": _signal_contract(variants[0][1]),
        "variants": [
            {
                "trial_id": trial_id,
                "stop_z": config.stop_z,
                "maximum_hold_bars": config.maximum_hold_bars,
            }
            for trial_id, config in variants
        ],
        "source_identity": source_identity,
        "diagnostics": diagnostics,
        "gap_audits": gap_audits,
        "cells": [
            {"trial_id": trial_id, **_compact_report(report)}
            for trial_id, report in runs
        ],
        "trade_storage": "Parquet sidecar declared by command runner",
        "limitations": [
            "the exit surface is post-hoc development tuning",
            "pair cells use independent research accounts and cannot be summed",
            "all reported cells are development evidence only",
            "gap audits identify dependence but cannot reconstruct missing venue paths",
        ],
    }


def _surface_trade_rows(
    runs: list[tuple[str, ResidualPairReport]],
) -> pd.DataFrame:
    rows = [
        {"trial_id": trial_id, **asdict(trade)}
        for trial_id, report in runs
        for trade in report.trades
    ]
    columns = ["trial_id", *(value.name for value in fields(ResidualTrade))]
    return pd.DataFrame.from_records(rows, columns=columns)
