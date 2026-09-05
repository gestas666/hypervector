"""Causal sampled net-return economics for one V58 ETH lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvent,
    EligiblePolicyFundingEvidence,
    covered_funding_bps,
)

Record = Mapping[str, object]

_SYMBOL = "ETH"
_NET_SCOPE = "exact_depth_fee_and_funding"


def sampled_eth_net_path(
    status: Record,
    contract: Record,
    attempt: Record,
    *,
    times_ms: Sequence[int],
    prices: Sequence[float],
    gross_returns_bps: Sequence[float],
) -> dict[str, object]:
    """Return exact sampled net economics without implying executable fills."""
    _require_sample_arrays(times_ms, prices, gross_returns_bps)
    entry_time = _integer(attempt.get("entry_time_ms"), "ETH entry time")
    notional = _positive(attempt.get("entry_notional_usd"), "ETH entry notional")
    quantity = _positive(attempt.get("position_quantity"), "ETH quantity")
    fee_rate = _positive(contract.get("taker_fee_rate"), "ETH taker fee rate")
    side = _side(attempt.get("side"))
    funding = _funding_evidence(status, entry_time, times_ms[-1])
    net_rows = tuple(
        _net_row(
            funding,
            side,
            entry_time,
            timestamp,
            price,
            gross,
            notional,
            quantity,
            fee_rate,
        )
        for timestamp, price, gross in zip(
            times_ms, prices, gross_returns_bps, strict=True
        )
    )
    return _net_summary(net_rows, entry_time, notional)


def _net_summary(
    rows: Sequence[Record], entry_time: int, notional: float
) -> dict[str, object]:
    maximum = max(rows, key=lambda row: float(row["net_return_bps"]))
    minimum = min(rows, key=lambda row: float(row["net_return_bps"]))
    first_profit = next(
        (row for row in rows if float(row["net_return_bps"]) > 0.0), None
    )
    latest = rows[-1]
    maximum_net = float(maximum["net_return_bps"])
    latest_net = float(latest["net_return_bps"])
    return {
        "maximum_sampled_net_return_bps": maximum_net,
        "maximum_sampled_net_return_time_ms": maximum["timestamp_ms"],
        "seconds_to_maximum_sampled_net_return": (
            int(maximum["timestamp_ms"]) - entry_time
        )
        / 1_000.0,
        "maximum_sampled_net_pnl_usd": notional * maximum_net / 10_000.0,
        "minimum_sampled_net_return_bps": minimum["net_return_bps"],
        "minimum_sampled_net_return_time_ms": minimum["timestamp_ms"],
        "first_sampled_net_profit_time_ms": (
            None if first_profit is None else first_profit["timestamp_ms"]
        ),
        "seconds_to_first_sampled_net_profit": (
            None
            if first_profit is None
            else (int(first_profit["timestamp_ms"]) - entry_time) / 1_000.0
        ),
        "sampled_net_return_giveback_bps": maximum_net - latest_net,
        "sampled_net_profit_observed": maximum_net > 0.0,
        "sampled_net_return_scope": _NET_SCOPE,
    }


def _net_row(
    funding: EligiblePolicyFundingEvidence,
    side: str,
    entry_time: int,
    timestamp: int,
    price: float,
    gross_bps: float,
    notional: float,
    quantity: float,
    fee_rate: float,
) -> dict[str, object]:
    fee_usd = fee_rate * (notional + quantity * price)
    fee_bps = fee_usd / notional * 10_000.0
    funding_bps = covered_funding_bps(
        funding,
        symbol=_SYMBOL,
        side=side,
        start_ms=entry_time,
        end_ms=timestamp,
    )
    if funding_bps is None:
        raise ValueError("V58 ETH sampled funding path is not fully covered")
    net = gross_bps - fee_bps + funding_bps
    if not all(math.isfinite(value) for value in (fee_bps, funding_bps, net)):
        raise ValueError("V58 ETH sampled economics are nonfinite")
    return {"timestamp_ms": timestamp, "net_return_bps": net}


def _funding_evidence(
    status: Record, entry_time: int, current_time: int
) -> EligiblePolicyFundingEvidence:
    source = _mapping(status.get("source_evidence"), "ETH source evidence")
    row = _mapping(source.get("funding"), "ETH funding evidence")
    expected = {
        "source": "hl_funding_history",
        "status": "covered",
        "symbol": _SYMBOL,
    }
    if any(row.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 ETH funding evidence identity is invalid")
    events = _events(row.get("events"))
    evidence = EligiblePolicyFundingEvidence(
        symbol=_SYMBOL,
        requested_start_ms=_integer(row.get("requested_start_ms"), "funding start"),
        requested_end_ms=_integer(row.get("requested_end_ms"), "funding end"),
        events=events,
    )
    if (
        evidence.requested_start_ms > entry_time
        or evidence.requested_end_ms < current_time
    ):
        raise ValueError("V58 ETH sampled funding bounds are incomplete")
    return evidence


def _events(value: object) -> tuple[EligiblePolicyFundingEvent, ...]:
    if not isinstance(value, list):
        raise ValueError("V58 ETH funding events must be an array")
    return tuple(
        EligiblePolicyFundingEvent(
            _integer(row.get("timestamp_ms"), "funding event time"),
            _number(row.get("funding_rate"), "funding event rate"),
        )
        for item in value
        for row in (_mapping(item, "ETH funding event"),)
    )


def _require_sample_arrays(
    times: Sequence[int], prices: Sequence[float], gross: Sequence[float]
) -> None:
    if not times or len(times) != len(prices) or len(times) != len(gross):
        raise ValueError("V58 ETH sampled economics arrays are incomplete")
    if any(type(value) is not int or value <= 0 for value in times):
        raise ValueError("V58 ETH sampled times must be positive integers")
    if list(times) != sorted(times) or len(times) != len(set(times)):
        raise ValueError("V58 ETH sampled times must be ordered and unique")
    if any(not math.isfinite(value) or value <= 0.0 for value in prices):
        raise ValueError("V58 ETH sampled prices must be positive and finite")
    if any(not math.isfinite(value) for value in gross):
        raise ValueError("V58 ETH sampled returns must be finite")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"V58 {label} must be an object")
    return value


def _side(value: object) -> str:
    if value not in {"long", "short"}:
        raise ValueError("V58 ETH sampled side is invalid")
    return str(value)


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"V58 {label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"V58 {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"V58 {label} must be finite")
    return number


def _positive(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"V58 {label} must be positive")
    return number
