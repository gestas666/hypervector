"""Shared exact funding-event valuation for HYPE research lifecycles."""

from __future__ import annotations

import math

import pandas as pd

from hypervector.data.hl_funding_evidence import HlFundingEvidence
from hypervector.research.oracle_price_series import CausalOraclePriceSeries


def build_hype_funding_events(
    funding: HlFundingEvidence,
    oracle_prices: pd.DataFrame,
    *,
    side: str,
    quantity: float,
    entry_time_ms: int,
    exit_time_ms: int,
    maximum_oracle_staleness_ms: int,
) -> list[dict[str, object]]:
    """Value official open-interval HYPE settlements with causal oracle prices."""
    _require_contract(funding, side, quantity, entry_time_ms, exit_time_ms)
    funding.require_covers(entry_time_ms, exit_time_ms)
    oracle = CausalOraclePriceSeries(
        oracle_prices,
        maximum_staleness_ms=maximum_oracle_staleness_ms,
    )
    sign = 1.0 if side == "long" else -1.0
    output: list[dict[str, object]] = []
    prior_event = -1
    for raw in funding.rows:
        event_ms = _integer(raw.get("event_ts_ms"), "funding event time")
        if event_ms <= prior_event:
            raise ValueError("HYPE funding events must be ordered and unique")
        prior_event = event_ms
        if not entry_time_ms < event_ms < exit_time_ms:
            continue
        rate = _number(raw.get("funding_rate"), "funding rate")
        observed = oracle.at_or_before(event_ms)
        output.append(
            {
                "event_ts_ms": event_ms,
                "funding_rate": rate,
                "oracle_observed_ts_ms": observed.timestamp_ms,
                "oracle_price": observed.oracle_price,
                "oracle_staleness_ms": observed.staleness_ms,
                "cashflow_usd": -sign * quantity * observed.oracle_price * rate,
            }
        )
    return output


def _require_contract(
    funding: HlFundingEvidence,
    side: str,
    quantity: float,
    entry_time_ms: int,
    exit_time_ms: int,
) -> None:
    if funding.symbol != "HYPE":
        raise ValueError("funding evidence must have exact HYPE identity")
    if side not in {"long", "short"}:
        raise ValueError("HYPE funding side must be long or short")
    if not math.isfinite(quantity) or quantity <= 0.0:
        raise ValueError("HYPE funding quantity must be positive and finite")
    if entry_time_ms < 0 or exit_time_ms <= entry_time_ms:
        raise ValueError("HYPE funding exit must follow entry")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result
