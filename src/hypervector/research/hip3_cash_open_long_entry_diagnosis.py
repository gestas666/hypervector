"""Causal development-only attribution for cash-open long entries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from numbers import Real
from statistics import median

import pandas as pd

from hypervector.research.shared_portfolio_models import SharedPortfolioTrade

Record = Mapping[str, object]

_BAR_FIELDS = (
    "signal_open",
    "signal_close",
    "decision_spread_bps",
    "decision_imbalance_10",
    "public_trade_count",
    "signal_volume",
    "source_snapshot_count",
)
_SIGNAL_FIELDS = ("long_entry", "previous_cash_close", "opening_gap_bps")
_FEATURE_FIELDS = (
    "opening_gap_bps",
    "absolute_opening_gap_bps",
    "opening_reversal_bps",
    "gap_recovery_fraction",
    "decision_spread_bps",
    "decision_imbalance_10",
    "public_trade_count",
    "signal_volume",
    "source_snapshot_count",
)
_CAUSE_FIELDS = (
    "full_mark_path_unresolved",
    "entry_slice_unresolved",
    "stale_l2_entry",
    "stale_l2_exit",
    "data_gap_exit",
)


def build_cash_open_long_entry_diagnosis(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    nominal_trades: Sequence[SharedPortfolioTrade],
    stress_trades: Sequence[SharedPortfolioTrade],
    path_detail: Record,
) -> dict[str, object]:
    """Join causal opening features to exact long-only replay outcomes."""
    _validate_frames(bars, signals)
    pairs = _paired_trades(nominal_trades, stress_trades)
    nominal_paths = _path_index(path_detail, "nominal", len(pairs))
    stress_paths = _path_index(path_detail, "stress", len(pairs))
    entries = [
        _entry_record(bars, signals, nominal, stress, nominal_paths, stress_paths)
        for nominal, stress in pairs
    ]
    return {
        "schema_version": "hip3_cash_open_long_entry_diagnosis_v1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "live_change": False,
            "threshold_selection": False,
            "validation_accessed": False,
            "holdout_accessed": False,
        },
        "entry_count": len(entries),
        "entries": entries,
        "stress_outcome_summary": _outcome_summary(entries),
    }


def _entry_record(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    nominal: SharedPortfolioTrade,
    stress: SharedPortfolioTrade,
    nominal_paths: Mapping[tuple[str, str], dict[str, bool]],
    stress_paths: Mapping[tuple[str, str], dict[str, bool]],
) -> dict[str, object]:
    identity = _entry_identity(nominal)
    at = pd.Timestamp(nominal.signal_time_utc)
    if at not in bars.index or at not in signals.index:
        raise ValueError("cash-open diagnosis signal time is absent from source bars")
    signal = signals.loc[at]
    if not bool(signal["long_entry"]):
        raise ValueError("cash-open diagnosis trade lacks a causal long signal")
    features = _features(bars.loc[at], signal)
    nominal_path = nominal_paths.get(identity, {})
    stress_path = stress_paths.get(identity, {})
    return {
        "entry_identity": {
            "signal_time_utc": nominal.signal_time_utc,
            "entry_time_utc": nominal.entry_time_utc,
        },
        "causal_features": features,
        "nominal_outcome": _outcome(nominal),
        "stress_outcome": _outcome(stress),
        "technical_path": {
            "resolved": not (nominal_path or stress_path),
            "nominal_unresolved_causes": nominal_path,
            "stress_unresolved_causes": stress_path,
        },
    }


def _features(bar: pd.Series, signal: pd.Series) -> dict[str, float | int]:
    opening = _finite(bar["signal_open"], "opening price")
    close = _finite(bar["signal_close"], "opening-bar close")
    previous = _finite(signal["previous_cash_close"], "previous cash close")
    gap = _finite(signal["opening_gap_bps"], "opening gap")
    if previous <= opening or close >= previous or gap >= 0.0:
        raise ValueError("cash-open diagnosis source row is not a valid long setup")
    output: dict[str, float | int] = {
        "opening_gap_bps": gap,
        "absolute_opening_gap_bps": abs(gap),
        "opening_reversal_bps": 10_000.0 * (close / opening - 1.0),
        "gap_recovery_fraction": (close - opening) / (previous - opening),
        "decision_spread_bps": _finite(bar["decision_spread_bps"], "spread"),
        "decision_imbalance_10": _finite(bar["decision_imbalance_10"], "imbalance"),
        "public_trade_count": _count(bar["public_trade_count"], "trade count"),
        "signal_volume": _finite(bar["signal_volume"], "signal volume"),
        "source_snapshot_count": _count(bar["source_snapshot_count"], "snapshot count"),
    }
    return output


def _paired_trades(
    nominal: Sequence[SharedPortfolioTrade], stress: Sequence[SharedPortfolioTrade]
) -> list[tuple[SharedPortfolioTrade, SharedPortfolioTrade]]:
    nominal_ids = [_entry_identity(trade) for trade in nominal]
    stress_ids = [_entry_identity(trade) for trade in stress]
    if not nominal_ids or nominal_ids != stress_ids:
        raise ValueError("cash-open nominal and stress entry identities differ")
    if any(trade.direction != "long" for trade in (*nominal, *stress)):
        raise ValueError("cash-open entry diagnosis requires long-only trades")
    return list(zip(nominal, stress, strict=True))


def _path_index(
    path_detail: Record, scenario: str, expected_trades: int
) -> dict[tuple[str, str], dict[str, bool]]:
    row = _mapping(path_detail.get(scenario), f"{scenario} path detail")
    if row.get("completed_trades") != expected_trades:
        raise ValueError("cash-open path detail trade count differs from replay")
    raw = row.get("unresolved_lifecycles")
    if not isinstance(raw, list):
        raise ValueError("cash-open unresolved lifecycles must be an array")
    output: dict[tuple[str, str], dict[str, bool]] = {}
    for item in raw:
        lifecycle = _mapping(item, "unresolved lifecycle")
        identity = (
            _text(lifecycle.get("signal_time_utc"), "path signal time"),
            _text(lifecycle.get("entry_time_utc"), "path entry time"),
        )
        causes = {
            field: _boolean(lifecycle.get(field), field) for field in _CAUSE_FIELDS
        }
        if identity in output or not any(causes.values()):
            raise ValueError("cash-open unresolved lifecycle evidence is invalid")
        output[identity] = causes
    return output


def _outcome(trade: SharedPortfolioTrade) -> dict[str, object]:
    return {
        "exit_time_utc": trade.exit_time_utc,
        "exit_reason": trade.exit_reason,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "target_price": trade.target_price,
        "stop_price": trade.stop_price,
        "fees_usd": trade.fees_usd,
        "funding_cashflow_usd": trade.funding_cashflow_usd,
        "net_pnl_usd": trade.net_pnl_usd,
    }


def _outcome_summary(entries: Sequence[Record]) -> dict[str, object]:
    groups = {
        "wins": [row for row in entries if _stress_net(row) > 0.0],
        "losses": [row for row in entries if _stress_net(row) < 0.0],
        "breakeven": [row for row in entries if _stress_net(row) == 0.0],
    }
    return {name: _group_summary(rows) for name, rows in groups.items()}


def _group_summary(entries: Sequence[Record]) -> dict[str, object]:
    return {
        "count": len(entries),
        "net_pnl_usd": sum(_stress_net(row) for row in entries),
        "feature_medians": {
            field: median(_feature(row, field) for row in entries) if entries else None
            for field in _FEATURE_FIELDS
        },
    }


def _validate_frames(bars: pd.DataFrame, signals: pd.DataFrame) -> None:
    for frame, fields, label in (
        (bars, _BAR_FIELDS, "bars"),
        (signals, _SIGNAL_FIELDS, "signals"),
    ):
        missing = sorted(set(fields).difference(frame.columns))
        valid_index = (
            isinstance(frame.index, pd.DatetimeIndex) and frame.index.tz is not None
        )
        if missing or not valid_index or not frame.index.is_unique:
            raise ValueError(
                f"cash-open diagnosis {label} contract is invalid: {missing}"
            )


def _entry_identity(trade: SharedPortfolioTrade) -> tuple[str, str]:
    return trade.signal_time_utc, trade.entry_time_utc


def _stress_net(entry: Record) -> float:
    return _finite(
        _mapping(entry.get("stress_outcome"), "stress outcome").get("net_pnl_usd"),
        "stress net",
    )


def _feature(entry: Record, name: str) -> float:
    return _finite(
        _mapping(entry.get("causal_features"), "causal features").get(name), name
    )


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be numeric")
    output = float(value)
    if not math.isfinite(output):
        raise ValueError(f"{label} must be finite")
    return output


def _count(value: object, label: str) -> int:
    output = _finite(value, label)
    if output < 0.0 or not output.is_integer():
        raise ValueError(f"{label} must be a non-negative integer")
    return int(output)
