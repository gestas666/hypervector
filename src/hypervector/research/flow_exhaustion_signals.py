"""Causal five-minute aggressive-flow exhaustion and book-replenishment signals."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


_REQUIRED_COLUMNS = frozenset(
    {
        "bar_open_at",
        "last_book_at",
        "open",
        "high",
        "low",
        "close",
        "buy_volume",
        "sell_volume",
        "final_60_buy_volume",
        "final_60_sell_volume",
        "imbalance_5_last",
    }
)
_PRICE_COLUMNS = ("open", "high", "low", "close")
_FLOW_COLUMNS = (
    "buy_volume",
    "sell_volume",
    "final_60_buy_volume",
    "final_60_sell_volume",
)


@dataclass(frozen=True)
class FlowExhaustionSignalConfig:
    """Frozen percentile, edge, and stop assumptions for signal generation."""

    lookback_bars: int = 2_016
    shock_quantile: float = 0.975
    flow_quantile: float = 0.75
    minimum_target_bps: float = 26.0
    stop_clearance_bps: float = 2.0

    def __post_init__(self) -> None:
        if isinstance(self.lookback_bars, bool) or self.lookback_bars < 4:
            raise ValueError("flow-exhaustion lookback must be at least four bars")
        for name in ("shock_quantile", "flow_quantile"):
            value = float(getattr(self, name))
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} must be strictly between zero and one")
        for name in ("minimum_target_bps", "stop_clearance_bps"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class FlowExhaustionSignalReport:
    """Eligible signals plus mutually exclusive causal blocker attribution."""

    signals: pd.DataFrame
    evaluated_bars: int
    blockers: dict[str, int]
    report_only: bool = True
    execution_authority: str = "none"
    place_attempted: bool = False


def build_flow_exhaustion_signals(
    rows: pd.DataFrame,
    symbol: str,
    config: FlowExhaustionSignalConfig | None = None,
) -> FlowExhaustionSignalReport:
    """Build symmetric contrarian signals from completed venue-native inputs."""
    cfg = config or FlowExhaustionSignalConfig()
    frame = _validated_rows(rows, symbol)
    prepared = _add_causal_fields(frame, cfg)
    eligible = prepared.loc[prepared["shock_threshold_bps"].notna()].copy()
    blockers = _empty_blockers()
    signals: list[dict[str, object]] = []
    for row in eligible.itertuples(index=False):
        reason = _blocker(row, cfg)
        if reason is not None:
            blockers[reason] += 1
            continue
        signals.append(_signal_record(row, symbol, cfg))
    return FlowExhaustionSignalReport(
        pd.DataFrame(signals, columns=_signal_columns()),
        len(eligible),
        blockers,
    )


def build_segmented_flow_exhaustion_signals(
    rows: pd.DataFrame,
    symbol: str,
    config: FlowExhaustionSignalConfig | None = None,
) -> FlowExhaustionSignalReport:
    """Build signals while resetting causal history after every data gap."""
    cfg = config or FlowExhaustionSignalConfig()
    frame = _validated_rows(rows, symbol, require_contiguous=False)
    times = pd.DatetimeIndex(frame["bar_open_at"])
    segment_ids = (
        times.to_series(index=frame.index).diff().ne(pd.Timedelta(minutes=5)).cumsum()
    )
    reports = [
        build_flow_exhaustion_signals(segment, symbol, cfg)
        for _, segment in frame.groupby(segment_ids, sort=False)
    ]
    blockers = _empty_blockers()
    for report in reports:
        for reason, count in report.blockers.items():
            blockers[reason] += count
    signals = pd.concat(
        [report.signals for report in reports],
        ignore_index=True,
    )
    return FlowExhaustionSignalReport(
        signals,
        sum(report.evaluated_bars for report in reports),
        blockers,
    )


def _validated_rows(
    rows: pd.DataFrame,
    symbol: str,
    *,
    require_contiguous: bool = True,
) -> pd.DataFrame:
    missing = sorted(_REQUIRED_COLUMNS.difference(rows.columns))
    if missing:
        raise ValueError(f"flow-exhaustion rows missing columns: {missing}")
    normalized_symbol = symbol.strip().upper()
    if normalized_symbol not in {"BTC", "SOL"}:
        raise ValueError("flow-exhaustion historical symbol must be BTC or SOL")
    if rows.empty:
        raise ValueError("flow-exhaustion rows must be non-empty")
    frame = rows.loc[:, sorted(_REQUIRED_COLUMNS)].copy()
    times = pd.DatetimeIndex(frame["bar_open_at"])
    if times.tz is None or times.has_duplicates or not times.is_monotonic_increasing:
        raise ValueError("flow-exhaustion bars require ordered unique aware times")
    if (
        require_contiguous
        and len(times) > 1
        and (times[1:] - times[:-1] != pd.Timedelta(minutes=5)).any()
    ):
        raise ValueError("flow-exhaustion input must have exact five-minute cadence")
    _validate_numeric(frame)
    _validate_book_times(frame)
    return frame


def _validate_numeric(frame: pd.DataFrame) -> None:
    numeric = frame.loc[:, [*_PRICE_COLUMNS, *_FLOW_COLUMNS]].to_numpy(float)
    if not np.isfinite(numeric).all():
        raise ValueError("flow-exhaustion price and flow values must be finite")
    if (frame.loc[:, _PRICE_COLUMNS].to_numpy(float) <= 0.0).any():
        raise ValueError("flow-exhaustion prices must be positive")
    if (frame.loc[:, _FLOW_COLUMNS].to_numpy(float) < 0.0).any():
        raise ValueError("flow-exhaustion volumes must be non-negative")
    if ((frame["buy_volume"] + frame["sell_volume"]) <= 0.0).any():
        raise ValueError("five-minute aggressor volume must be positive")


def _validate_book_times(frame: pd.DataFrame) -> None:
    present = frame.loc[frame["last_book_at"].notna()]
    observed = pd.DatetimeIndex(present["last_book_at"])
    if not observed.empty and observed.tz is None:
        raise ValueError("flow-exhaustion book times must be timezone-aware")
    available = pd.DatetimeIndex(present["bar_open_at"]) + pd.Timedelta(minutes=5)
    if (observed > available).any():
        raise ValueError("future book observation would leak into signal")


def _add_causal_fields(
    frame: pd.DataFrame, config: FlowExhaustionSignalConfig
) -> pd.DataFrame:
    output = frame.copy()
    output["shock_bps"] = (output["close"] / output["open"] - 1.0) * 10_000.0
    output["flow_imbalance"] = _imbalance(output["buy_volume"], output["sell_volume"])
    output["final_60_flow_imbalance"] = _imbalance(
        output["final_60_buy_volume"], output["final_60_sell_volume"]
    )
    prior_shock = output["shock_bps"].abs().shift(1)
    prior_flow = output["flow_imbalance"].abs().shift(1)
    output["shock_threshold_bps"] = prior_shock.rolling(config.lookback_bars).quantile(
        config.shock_quantile
    )
    output["flow_threshold"] = prior_flow.rolling(config.lookback_bars).quantile(
        config.flow_quantile
    )
    return output


def _imbalance(buy: pd.Series, sell: pd.Series) -> pd.Series:
    total = buy + sell
    return (buy.astype(float) - sell.astype(float)) / total.where(total > 0.0)


def _blocker(row: object, config: FlowExhaustionSignalConfig) -> str | None:
    shock = float(getattr(row, "shock_bps"))
    shock_sign = float(np.sign(shock))
    threshold = max(
        config.minimum_target_bps,
        float(getattr(row, "shock_threshold_bps")),
    )
    if shock_sign == 0.0 or abs(shock) < threshold:
        return "shock_below_threshold"
    flow = float(getattr(row, "flow_imbalance"))
    flow_threshold = float(getattr(row, "flow_threshold"))
    if shock_sign * flow <= 0.0 or abs(flow) < flow_threshold:
        return "flow_not_aligned_or_extreme"
    final_flow = float(getattr(row, "final_60_flow_imbalance"))
    if not math.isfinite(final_flow):
        return "final_flow_unavailable"
    if shock_sign * final_flow >= 0.0:
        return "final_flow_not_reversed"
    book = float(getattr(row, "imbalance_5_last"))
    if not math.isfinite(book):
        return "terminal_book_missing"
    if shock_sign * book >= 0.0:
        return "terminal_book_not_opposing"
    return None


def _signal_record(
    row: object,
    symbol: str,
    config: FlowExhaustionSignalConfig,
) -> dict[str, object]:
    shock = float(getattr(row, "shock_bps"))
    long = shock < 0.0
    clearance = config.stop_clearance_bps / 10_000.0
    stop = (
        float(getattr(row, "low")) * (1.0 - clearance)
        if long
        else float(getattr(row, "high")) * (1.0 + clearance)
    )
    threshold = max(
        config.minimum_target_bps,
        float(getattr(row, "shock_threshold_bps")),
    )
    bar_open = pd.Timestamp(getattr(row, "bar_open_at"))
    return {
        "symbol": symbol.strip().upper(),
        "bar_open_at": bar_open,
        "available_at_utc": bar_open + pd.Timedelta(minutes=5),
        "side": "long" if long else "short",
        "shock_bps": shock,
        "shock_threshold_bps": float(getattr(row, "shock_threshold_bps")),
        "flow_imbalance": float(getattr(row, "flow_imbalance")),
        "flow_threshold": float(getattr(row, "flow_threshold")),
        "final_60_flow_imbalance": float(getattr(row, "final_60_flow_imbalance")),
        "imbalance_5_last": float(getattr(row, "imbalance_5_last")),
        "target_price": float(getattr(row, "open")),
        "stop_price": stop,
        "rank_score": abs(shock) / threshold,
    }


def _empty_blockers() -> dict[str, int]:
    return {
        "shock_below_threshold": 0,
        "flow_not_aligned_or_extreme": 0,
        "final_flow_unavailable": 0,
        "final_flow_not_reversed": 0,
        "terminal_book_missing": 0,
        "terminal_book_not_opposing": 0,
    }


def _signal_columns() -> list[str]:
    return [
        "symbol",
        "bar_open_at",
        "available_at_utc",
        "side",
        "shock_bps",
        "shock_threshold_bps",
        "flow_imbalance",
        "flow_threshold",
        "final_60_flow_imbalance",
        "imbalance_5_last",
        "target_price",
        "stop_price",
        "rank_score",
    ]
