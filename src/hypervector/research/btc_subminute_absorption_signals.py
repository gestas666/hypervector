"""Frozen BTC subminute sell-flow absorption signal construction."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

import numpy as np
import pandas as pd


_REQUIRED_COLUMNS = frozenset(
    {
        "bucket_ms",
        "bucket_start_utc",
        "available_at_utc",
        "snapshot_count",
        "sell_notional_usd",
        "sell_share",
        "adverse_midpoint_bps",
        "bid_depletion_fraction",
        "bid_recovery_fraction",
        "terminal_imbalance_10",
        "maximum_spread_bps",
        "prior_60m_trend_bps",
        "last_mid",
    }
)
_NUMERIC_COLUMNS = tuple(
    sorted(_REQUIRED_COLUMNS.difference({"bucket_start_utc", "available_at_utc"}))
)
_SIGNAL_COLUMNS = (
    "event_id",
    "arm",
    "symbol",
    "side",
    "bucket_ms",
    "bucket_start_utc",
    "available_at_utc",
    "reference_price",
    "sell_notional_usd",
    "sell_share",
    "adverse_midpoint_bps",
    "bid_depletion_fraction",
    "bid_recovery_fraction",
    "terminal_imbalance_10",
    "maximum_spread_bps",
    "prior_60m_trend_bps",
)


@dataclass(frozen=True)
class BtcAbsorptionSignalConfig:
    """Exact preregistered signal and cooldown thresholds."""

    minimum_book_snapshots: int = 5
    minimum_sell_notional_usd: float = 5_500_000.0
    minimum_sell_share: float = 0.75
    maximum_adverse_midpoint_bps: float = 3.0
    minimum_bid_depletion: float = 0.20
    minimum_bid_recovery: float = 0.75
    minimum_terminal_imbalance: float = 0.0
    maximum_spread_bps: float = 5.0
    minimum_prior_60m_trend_bps: float = 25.0
    cooldown_minutes: int = 60

    def __post_init__(self) -> None:
        values = tuple(float(value) for value in self.__dict__.values())
        if not all(math.isfinite(value) for value in values):
            raise ValueError("BTC absorption thresholds must be finite")
        if self.minimum_book_snapshots < 1 or self.cooldown_minutes < 1:
            raise ValueError("BTC absorption counts must be positive")
        if self.minimum_sell_notional_usd <= 0.0 or self.maximum_spread_bps <= 0.0:
            raise ValueError("BTC absorption price thresholds must be positive")


@dataclass(frozen=True)
class BtcAbsorptionSignalReport:
    """Candidate, mechanism control, and complete blocker evidence."""

    candidate: pd.DataFrame
    control: pd.DataFrame
    candidate_blockers: dict[str, int]
    control_blockers: dict[str, int]
    execution_authority: str = "none"
    orders_attempted: bool = False


def build_btc_absorption_signals(
    features: pd.DataFrame,
    config: BtcAbsorptionSignalConfig | None = None,
) -> BtcAbsorptionSignalReport:
    """Build exact long-only candidate and extreme-sell control signals."""
    cfg = config or BtcAbsorptionSignalConfig()
    frame = _validated_features(features)
    candidate_rows, candidate_blockers = _build_arm(frame, cfg, candidate=True)
    control_rows, control_blockers = _build_arm(frame, cfg, candidate=False)
    return BtcAbsorptionSignalReport(
        pd.DataFrame(candidate_rows, columns=_SIGNAL_COLUMNS),
        pd.DataFrame(control_rows, columns=_SIGNAL_COLUMNS),
        candidate_blockers,
        control_blockers,
    )


def _validated_features(features: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED_COLUMNS.difference(features.columns))
    if missing:
        raise ValueError(f"BTC absorption features missing columns: {missing}")
    frame = features.loc[:, sorted(_REQUIRED_COLUMNS)].copy()
    frame["bucket_start_utc"] = pd.to_datetime(frame["bucket_start_utc"], utc=True)
    frame["available_at_utc"] = pd.to_datetime(frame["available_at_utc"], utc=True)
    numeric = frame.loc[:, _NUMERIC_COLUMNS].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("BTC absorption features must be finite")
    if frame["available_at_utc"].duplicated().any():
        raise ValueError("BTC absorption feature times are duplicated")
    if not frame["available_at_utc"].is_monotonic_increasing:
        raise ValueError("BTC absorption features must be chronological")
    return frame


def _build_arm(
    frame: pd.DataFrame,
    config: BtcAbsorptionSignalConfig,
    *,
    candidate: bool,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    rows: list[dict[str, object]] = []
    blockers = _empty_blockers(candidate)
    next_available = pd.Timestamp.min.tz_localize("UTC")
    for row in frame.itertuples(index=False):
        reason = (
            _candidate_reason(row, config)
            if candidate
            else _control_reason(row, config)
        )
        if reason is not None:
            blockers[reason] += 1
            continue
        available = pd.Timestamp(getattr(row, "available_at_utc"))
        if available < next_available:
            blockers[_cooldown_reason(candidate)] += 1
            continue
        rows.append(_signal_record(row, candidate))
        next_available = available + pd.Timedelta(minutes=config.cooldown_minutes)
    return rows, blockers


def _control_reason(row: object, config: BtcAbsorptionSignalConfig) -> str | None:
    if int(getattr(row, "snapshot_count")) < config.minimum_book_snapshots:
        return "insufficient_book_snapshots"
    if float(getattr(row, "sell_notional_usd")) < config.minimum_sell_notional_usd:
        return "sell_notional_below_minimum"
    if float(getattr(row, "sell_share")) < config.minimum_sell_share:
        return "sell_share_below_minimum"
    if float(getattr(row, "prior_60m_trend_bps")) < config.minimum_prior_60m_trend_bps:
        return "prior_trend_below_minimum"
    return None


def _candidate_reason(row: object, config: BtcAbsorptionSignalConfig) -> str | None:
    primary = _control_reason(row, config)
    if primary is not None:
        return primary
    checks = (
        (
            float(getattr(row, "adverse_midpoint_bps"))
            > config.maximum_adverse_midpoint_bps,
            "midpoint_impact_above_maximum",
        ),
        (
            float(getattr(row, "bid_depletion_fraction"))
            < config.minimum_bid_depletion,
            "bid_depletion_below_minimum",
        ),
        (
            float(getattr(row, "bid_recovery_fraction")) < config.minimum_bid_recovery,
            "bid_recovery_below_minimum",
        ),
        (
            float(getattr(row, "terminal_imbalance_10"))
            < config.minimum_terminal_imbalance,
            "terminal_imbalance_below_minimum",
        ),
        (
            float(getattr(row, "maximum_spread_bps")) > config.maximum_spread_bps,
            "spread_above_maximum",
        ),
    )
    return next((reason for failed, reason in checks if failed), None)


def _signal_record(row: object, candidate: bool) -> dict[str, object]:
    arm = (
        "sell_flow_absorption_candidate"
        if candidate
        else "extreme_sell_uptrend_control"
    )
    bucket_ms = int(getattr(row, "bucket_ms"))
    identity = hashlib.sha256(f"{arm}|BTC|long|{bucket_ms}".encode()).hexdigest()
    return {
        "event_id": f"btc-absorption-{identity[:24]}",
        "arm": arm,
        "symbol": "BTC",
        "side": "long",
        "bucket_ms": bucket_ms,
        "bucket_start_utc": getattr(row, "bucket_start_utc"),
        "available_at_utc": getattr(row, "available_at_utc"),
        "reference_price": float(getattr(row, "last_mid")),
        **{name: float(getattr(row, name)) for name in _SIGNAL_COLUMNS[8:]},
    }


def _empty_blockers(candidate: bool) -> dict[str, int]:
    reasons = [
        "insufficient_book_snapshots",
        "sell_notional_below_minimum",
        "sell_share_below_minimum",
        "prior_trend_below_minimum",
        _cooldown_reason(candidate),
    ]
    if candidate:
        reasons.extend(
            [
                "midpoint_impact_above_maximum",
                "bid_depletion_below_minimum",
                "bid_recovery_below_minimum",
                "terminal_imbalance_below_minimum",
                "spread_above_maximum",
            ]
        )
    return dict.fromkeys(reasons, 0)


def _cooldown_reason(candidate: bool) -> str:
    return "candidate_cooldown_active" if candidate else "control_cooldown_active"
