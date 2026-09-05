"""Authenticated return-overlap context for the V58 observer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from pathlib import Path
import statistics

from hypervector.data.jsonl_prefix import read_jsonl_verified_prefix
from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.cohort_observer_identity import canonical_observer_run
from hypervector.research.v58_observer_technical_state import (
    require_reportable_v58_observer_status,
)

Record = Mapping[str, object]
BarValue = tuple[float, float, float, float, float]

_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)


@dataclass(frozen=True)
class ReturnInteractionContext:
    """Execution-incapable synchronized return evidence."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_return_context(
    *, observer: SuccessorObserverEvidence
) -> ReturnInteractionContext:
    """Load exact V58 return overlap from an authenticated observer prefix."""
    _require_observer(observer.status)
    evidence = _mapping(observer.evidence.get("observer_ledger"), "observer ledger")
    path = Path(_text(evidence.get("path"), "observer ledger path"))
    rows = read_jsonl_verified_prefix(
        path,
        "V58 observer ledger",
        length=_integer(evidence.get("stable_bytes"), "stable ledger bytes"),
        expected_sha256=_text(evidence.get("sha256"), "ledger sha256"),
    )
    current_rows, _ = canonical_observer_run(
        rows,
        _text(observer.status.get("run_id"), "observer run ID"),
    )
    activation = _activation_boundary(current_rows, observer.status)
    panel, excluded = _completed_panel(current_rows, observer.status, activation)
    payload = _return_payload(panel, activation, excluded)
    return ReturnInteractionContext(payload, {"observer_ledger": dict(evidence)})


def return_context_payload(context: ReturnInteractionContext) -> dict[str, object]:
    """Serialize descriptive return context without sizing authority."""
    return {
        **context.payload,
        "stable_covariance_claim": False,
        "sizing_input": False,
        "performance_gate": False,
        "execution_authority": context.execution_authority,
    }


def _activation_boundary(rows: Sequence[Record], status: Record) -> int:
    matches = []
    for row in rows:
        if (
            not _current_row(row, status)
            or row.get("event_type") != "configuration_identity"
        ):
            continue
        _require_authority_none(row, "configuration identity")
        payload = _mapping(row.get("payload"), "configuration identity payload")
        if payload.get("enabled_symbols") != list(_SYMBOLS):
            raise ValueError("V58 return context symbol identity is invalid")
        matches.append(_timestamp(row.get("observed_at_utc"), "activation time"))
    if len(matches) != 1:
        raise ValueError("V58 return context requires one configuration identity")
    return ((matches[0] + 59_999) // 60_000) * 60_000


def _completed_panel(
    rows: Sequence[Record], status: Record, activation: int
) -> tuple[dict[str, dict[int, BarValue]], int]:
    panel = {symbol: {} for symbol in _SYMBOLS}
    excluded: set[tuple[str, int]] = set()
    for row in rows:
        if not _current_row(row, status) or row.get("event_type") != "market_candles":
            continue
        _require_authority_none(row, "market candle")
        payload = _mapping(row.get("payload"), "market candle payload")
        if payload.get("timeframe") != "1m":
            raise ValueError("V58 return context candle timeframe is invalid")
        _merge_bars(panel, excluded, payload.get("bars"), activation)
    _require_common_panel(panel)
    return panel, len(excluded)


def _merge_bars(
    panel: dict[str, dict[int, BarValue]],
    excluded: set[tuple[str, int]],
    value: object,
    activation: int,
) -> None:
    groups = _mapping(value, "market candle groups")
    if not set(groups).issubset(_SYMBOLS):
        raise ValueError("V58 return context contains an unexpected symbol")
    for symbol, raw_bars in groups.items():
        if not isinstance(raw_bars, list):
            raise ValueError(f"{symbol} market candles must be an array")
        for raw_bar in raw_bars:
            timestamp, bar = _bar(raw_bar, str(symbol))
            if timestamp < activation:
                excluded.add((str(symbol), timestamp))
                continue
            previous = panel[str(symbol)].get(timestamp)
            if previous is not None and previous != bar:
                raise ValueError("V58 return context contains conflicting candles")
            panel[str(symbol)][timestamp] = bar


def _bar(value: object, symbol: str) -> tuple[int, BarValue]:
    row = _mapping(value, f"{symbol} candle")
    timestamp = _integer(row.get("timestamp_ms"), f"{symbol} candle timestamp")
    if timestamp % 60_000:
        raise ValueError(f"{symbol} candle timestamp is off cadence")
    prices = tuple(
        _positive_number(row.get(field), f"{symbol} candle {field}")
        for field in ("open", "high", "low", "close")
    )
    volume = _nonnegative_number(row.get("volume"), f"{symbol} candle volume")
    open_price, high, low, close = prices
    if high < max(open_price, close) or low > min(open_price, close) or low > high:
        raise ValueError(f"{symbol} candle OHLC is inconsistent")
    return timestamp, (open_price, high, low, close, volume)


def _require_common_panel(panel: Mapping[str, Mapping[int, BarValue]]) -> None:
    timestamp_sets = [set(panel[symbol]) for symbol in _SYMBOLS]
    if any(not values for values in timestamp_sets):
        raise ValueError("V58 return context has missing symbol candles")
    if any(values != timestamp_sets[0] for values in timestamp_sets[1:]):
        raise ValueError("V58 return context is not synchronized across symbols")
    timestamps = sorted(timestamp_sets[0])
    if any(right - left != 60_000 for left, right in zip(timestamps, timestamps[1:])):
        raise ValueError("V58 return context common panel contains a gap")


def _return_payload(
    panel: Mapping[str, Mapping[int, BarValue]], activation: int, excluded: int
) -> dict[str, object]:
    timestamps = sorted(panel[_SYMBOLS[0]])
    one_minute = _returns(panel, timestamps)
    five_timestamps = _complete_five_minute_timestamps(timestamps)
    five_minute = _returns(panel, five_timestamps)
    return {
        "prospective_start_utc": _iso(activation),
        "prospective_end_utc": _iso(timestamps[-1] + 60_000),
        "symbols": list(_SYMBOLS),
        "common_completed_bars": len(timestamps),
        "one_minute_return_observations": _return_count(one_minute),
        "five_minute_return_observations": _return_count(five_minute),
        "one_minute_pairwise_correlations": _pairwise(one_minute),
        "five_minute_pairwise_correlations": _pairwise(five_minute),
        "historical_warmup_bars_excluded": excluded,
        "return_definition": "consecutive_completed_close_log_return",
        "interpretation": "descriptive_short_window_not_stable_covariance",
    }


def _complete_five_minute_timestamps(timestamps: Sequence[int]) -> list[int]:
    available = set(timestamps)
    output = []
    for bucket in sorted({value // 300_000 * 300_000 for value in timestamps}):
        expected = {bucket + offset * 60_000 for offset in range(5)}
        if expected.issubset(available):
            output.append(bucket + 4 * 60_000)
    return output


def _returns(
    panel: Mapping[str, Mapping[int, BarValue]], timestamps: Sequence[int]
) -> dict[str, list[float]]:
    output = {symbol: [] for symbol in _SYMBOLS}
    for previous, current in zip(timestamps, timestamps[1:]):
        for symbol in _SYMBOLS:
            prior_close = panel[symbol][previous][3]
            current_close = panel[symbol][current][3]
            output[symbol].append(math.log(current_close / prior_close))
    return output


def _pairwise(returns: Mapping[str, Sequence[float]]) -> list[dict[str, object]]:
    output = []
    for index, left in enumerate(_SYMBOLS):
        for right in _SYMBOLS[index + 1 :]:
            output.append(
                {
                    "left": left,
                    "right": right,
                    "correlation": _correlation(returns[left], returns[right]),
                }
            )
    return output


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean, right_mean = statistics.fmean(left), statistics.fmean(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_delta)
        * sum(value * value for value in right_delta)
    )
    if denominator == 0.0:
        return None
    return sum(a * b for a, b in zip(left_delta, right_delta)) / denominator


def _return_count(returns: Mapping[str, Sequence[float]]) -> int:
    counts = {len(values) for values in returns.values()}
    if len(counts) != 1:
        raise ValueError("V58 return counts do not reconcile")
    return counts.pop()


def _current_row(row: Record, status: Record) -> bool:
    if row.get("run_id") != status.get("run_id"):
        return False
    if row.get("profile_fingerprint") != status.get("profile_fingerprint"):
        raise ValueError("V58 return row profile fingerprint is invalid")
    return True


def _require_authority_none(row: Record, label: str) -> None:
    expected = {
        "execution_authority": "none",
        "profile_id": _PROFILE_ID,
    }
    if any(row.get(field) != value for field, value in expected.items()):
        raise ValueError(f"V58 {label} authority or profile is invalid")


def _require_observer(status: Record) -> None:
    expected = {
        "profile_id": _PROFILE_ID,
        "freshness_status": "fresh",
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
    if any(status.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 return observer contract is invalid")
    require_reportable_v58_observer_status(status, "V58 return observer")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return number


def _number(value: object, label: str) -> float:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _timestamp(value: object, label: str) -> int:
    text = _text(value, label)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return int(parsed.astimezone(UTC).timestamp() * 1000)


def _iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000.0, tz=UTC).isoformat()
