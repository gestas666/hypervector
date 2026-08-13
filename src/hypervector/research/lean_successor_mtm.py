"""Exact-source adapters for lean-successor mark-to-market validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import math

import pandas as pd

from hypervector.research.concurrent_mtm_portfolio import MarkedLifecycle
from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    CohortTradeSpec,
)
from hypervector.research.evidence_selected_portfolio import AcceptedPortfolioOutcome

RouteKey = tuple[str, str]


@dataclass(frozen=True)
class RawLifecycleTerms:
    """One immutable source lifecycle before shared-account scaling."""

    strategy_id: str
    symbol: str
    side: str
    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    exit_price: float
    quantity: float
    source_notional_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    net_pnl_usd: float

    def __post_init__(self) -> None:
        """Reject ambiguous identities and unreconciled source economics."""
        _validate_raw_terms(self)


def scale_cohort_outcomes(
    outcomes: tuple[CohortOutcome, ...], multiplier: float
) -> tuple[CohortOutcome, ...]:
    """Scale a fixed route's economics without changing signals or identity."""
    _positive(multiplier, "multiplier")
    return tuple(
        CohortOutcome(
            row.strategy_id,
            row.side,
            replace(
                row.outcome,
                margin_fraction=row.outcome.margin_fraction * multiplier,
                entry_fee_usd=row.outcome.entry_fee_usd * multiplier,
                net_pnl_usd=row.outcome.net_pnl_usd * multiplier,
            ),
        )
        for row in outcomes
    )


def build_marked_lifecycles(
    accepted: tuple[AcceptedPortfolioOutcome, ...],
    raw_terms: tuple[RawLifecycleTerms, ...],
    specs: Mapping[RouteKey, CohortTradeSpec],
) -> tuple[MarkedLifecycle, ...]:
    """Join priority-accepted rows to exact source prices and cashflows."""
    source_index = _raw_index(raw_terms)
    output: list[MarkedLifecycle] = []
    for row in accepted:
        route = (row.strategy_id, row.symbol)
        spec = specs.get(route)
        if spec is None:
            raise ValueError(f"mark-to-market route spec is missing: {route}")
        raw = source_index.get(_accepted_key(row))
        if raw is None:
            raise ValueError(
                f"accepted lifecycle source terms are missing: {row.trade_id}"
            )
        output.append(_marked_lifecycle(row, raw, spec))
    return tuple(output)


def active_completed_bar_marks(
    bars: pd.DataFrame,
    lifecycles: tuple[RawLifecycleTerms | MarkedLifecycle, ...],
    *,
    bar_minutes: int,
) -> pd.DataFrame:
    """Shift bar-open timestamps to completion and retain only open intervals."""
    if isinstance(bar_minutes, bool) or bar_minutes < 1:
        raise ValueError("bar_minutes must be a positive integer")
    normalized = _normalized_bars(bars, bar_minutes)
    if not lifecycles:
        return normalized.iloc[0:0]
    timestamps_ms = normalized.index.as_unit("ns").asi8 // 1_000_000
    pieces = [
        normalized.loc[
            (timestamps_ms > row.entry_time_ms) & (timestamps_ms <= row.exit_time_ms)
        ]
        for row in lifecycles
    ]
    return pd.concat(pieces).sort_index().loc[lambda frame: ~frame.index.duplicated()]


def _marked_lifecycle(
    accepted: AcceptedPortfolioOutcome,
    raw: RawLifecycleTerms,
    spec: CohortTradeSpec,
) -> MarkedLifecycle:
    accepted_notional = accepted.margin_reserved_usd * spec.leverage
    scale = accepted_notional / raw.source_notional_usd
    total_fees = raw.fees_usd * scale
    exit_fee = total_fees - accepted.entry_fee_usd
    if exit_fee < -0.005:
        raise ValueError(
            f"accepted entry fee exceeds source total: {accepted.trade_id}"
        )
    return MarkedLifecycle(
        accepted.trade_id,
        accepted.strategy_id,
        accepted.symbol,
        accepted.side,
        accepted.entry_time_ms,
        accepted.exit_time_ms,
        raw.entry_price,
        raw.exit_price,
        raw.quantity * scale,
        accepted.entry_fee_usd,
        max(exit_fee, 0.0),
        raw.funding_cashflow_usd * scale,
        accepted.net_pnl_usd,
    )


def _raw_index(
    rows: tuple[RawLifecycleTerms, ...],
) -> dict[tuple[str, str, str, int, int], RawLifecycleTerms]:
    output: dict[tuple[str, str, str, int, int], RawLifecycleTerms] = {}
    for row in rows:
        key = _source_key(row)
        if key in output:
            raise ValueError(f"duplicate raw lifecycle source key: {key}")
        output[key] = row
    return output


def _source_key(row: RawLifecycleTerms) -> tuple[str, str, str, int, int]:
    return (
        row.strategy_id,
        row.symbol,
        row.side,
        row.entry_time_ms,
        row.exit_time_ms,
    )


def _accepted_key(row: AcceptedPortfolioOutcome) -> tuple[str, str, str, int, int]:
    return (
        row.strategy_id,
        row.symbol,
        row.side,
        row.entry_time_ms,
        row.exit_time_ms,
    )


def _normalized_bars(bars: pd.DataFrame, bar_minutes: int) -> pd.DataFrame:
    required = {"close", "high", "low"}
    missing = sorted(required - set(bars.columns))
    if missing:
        raise ValueError(f"completed mark bars are missing columns: {missing}")
    frame = bars.copy()
    if "timestamp" in frame.columns:
        frame.index = pd.to_datetime(frame.pop("timestamp"), utc=True)
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("completed mark bars require aware timestamps")
    frame.index = frame.index + pd.Timedelta(minutes=bar_minutes)
    frame = frame.sort_index()
    if not frame.index.is_unique:
        raise ValueError("completed mark bars must be unique")
    return frame.loc[:, ["close", "high", "low"]].astype(float)


def _validate_raw_terms(row: RawLifecycleTerms) -> None:
    if not row.strategy_id.strip() or not row.symbol.strip():
        raise ValueError("raw lifecycle identities must be non-empty")
    if row.side not in {"long", "short"}:
        raise ValueError("raw lifecycle side must be long or short")
    if row.entry_time_ms < 0 or row.exit_time_ms <= row.entry_time_ms:
        raise ValueError("raw lifecycle timestamps must be causal")
    for value, label in (
        (row.entry_price, "entry_price"),
        (row.exit_price, "exit_price"),
        (row.quantity, "quantity"),
        (row.source_notional_usd, "source_notional_usd"),
    ):
        _positive(value, label)
    _nonnegative(row.fees_usd, "fees_usd")
    _finite(row.funding_cashflow_usd, "funding_cashflow_usd")
    _finite(row.net_pnl_usd, "net_pnl_usd")
    sign = 1.0 if row.side == "long" else -1.0
    expected = sign * row.quantity * (row.exit_price - row.entry_price)
    expected += row.funding_cashflow_usd - row.fees_usd
    if not math.isclose(expected, row.net_pnl_usd, abs_tol=0.01):
        raise ValueError("raw lifecycle does not reconcile to price, fees, and funding")


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be non-negative")


def _finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
