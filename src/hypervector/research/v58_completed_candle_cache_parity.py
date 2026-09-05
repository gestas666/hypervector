"""Exact report-only V58 live-versus-cached-observer candle parity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import math

Record = Mapping[str, object]
Bar = tuple[float, float, float, float, float]
BarKey = tuple[str, int]

_MINUTE_MS = 60_000
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
_SYMBOL_INDEX = {symbol: index for index, symbol in enumerate(_SYMBOLS)}
_BAR_FIELDS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class _SourcePanel:
    bars: dict[BarKey, Bar]
    duplicate_consistent_rows: int
    event_sequences: tuple[int, ...]
    observed_times: tuple[str, ...]
    profile_fingerprint: str
    run_fingerprint: str


def build_v58_completed_candle_cache_parity(
    *,
    live_rows: Sequence[Record],
    observer_rows: Sequence[Record],
    live_run_id: str,
    observer_run_id: str,
    prospective_start_ms: int,
    minimum_contiguous_minutes: int,
    generated_at_utc: str,
) -> dict[str, object]:
    """Build an authority-free exact OHLCV parity report."""
    start = _minute_timestamp(prospective_start_ms, "prospective start")
    minimum = _positive_integer(minimum_contiguous_minutes, "minimum minutes")
    _timestamp_ms(generated_at_utc, "generation time")
    live = _source_panel(live_rows, live_run_id, "live", start)
    observer = _source_panel(observer_rows, observer_run_id, "observer", start)
    comparison, exact_keys = _comparison(live.bars, observer.bars)
    coverage = _coverage(comparison, exact_keys, start, minimum)
    return {
        "schema_version": 1,
        "mode": "v58_completed_candle_cache_parity",
        "generated_at_utc": generated_at_utc,
        "contract": _contract(),
        "scope": {
            "profile_id": _PROFILE_ID,
            "symbols": list(_SYMBOLS),
            "prospective_start_ms": start,
            "minimum_contiguous_minutes": minimum,
        },
        "sources": {
            "live": _source_summary(live, live_run_id),
            "observer": _source_summary(observer, observer_run_id),
        },
        "comparison": comparison,
        "coverage": coverage,
        "evidence_scope": {
            "first_published_completed_bar_ohlcv_only": True,
            "same_timestamp_late_revision_observable": False,
            "provider_decision_parity_proven": False,
            "profit_lock_cache_cutover_supported": False,
        },
        "limitations": [
            "telemetry emits only the first published value for each candle timestamp",
            "a later correction to an emitted timestamp is not observable here",
            "candle equality does not establish provider-decision parity",
            "shared upstream candle defects can remain equal across both sources",
            "this report has no execution or promotion authority",
        ],
    }


def _source_panel(
    rows: Sequence[Record], run_id: str, kind: str, start: int
) -> _SourcePanel:
    expected_run = _text(run_id, f"{kind} run ID")
    selected = [
        row
        for row in rows
        if row.get("run_id") == expected_run
        and row.get("event_type") == "market_candles"
    ]
    if not selected:
        raise ValueError(f"{kind} source has no market candles for selected run")
    bars: dict[BarKey, Bar] = {}
    duplicates = 0
    profiles: set[str] = set()
    runs: set[str] = set()
    sequences: list[int] = []
    observed: list[str] = []
    for row in selected:
        _require_authority(row, kind)
        profiles.add(
            _text(row.get("profile_fingerprint"), f"{kind} profile fingerprint")
        )
        runs.add(_text(row.get("run_fingerprint"), f"{kind} run fingerprint"))
        sequences.append(_nonnegative_integer(row.get("sequence"), f"{kind} sequence"))
        observed_text = _text(row.get("observed_at_utc"), f"{kind} observed time")
        observed.append(observed_text)
        duplicates += _merge_event(bars, row, kind, start, observed_text)
    if len(profiles) != 1 or len(runs) != 1:
        raise ValueError(f"{kind} source identity changed inside selected run")
    return _SourcePanel(
        bars=bars,
        duplicate_consistent_rows=duplicates,
        event_sequences=tuple(sequences),
        observed_times=tuple(observed),
        profile_fingerprint=profiles.pop(),
        run_fingerprint=runs.pop(),
    )


def _require_authority(row: Record, kind: str) -> None:
    expected = (
        ("live", True, "hyperliquid_mainnet")
        if kind == "live"
        else ("observe", False, "none")
    )
    actual = (
        row.get("execution_mode"),
        row.get("live_armed"),
        row.get("execution_authority"),
    )
    if actual != expected:
        raise ValueError(f"{kind} authority contract is invalid")
    if row.get("profile_id") != _PROFILE_ID:
        raise ValueError(f"{kind} profile ID is not V58")


def _merge_event(
    output: dict[BarKey, Bar],
    row: Record,
    kind: str,
    start: int,
    observed_at_utc: str,
) -> int:
    payload = _mapping(row.get("payload"), f"{kind} candle payload")
    if payload.get("timeframe") != "1m":
        raise ValueError(f"{kind} candle timeframe is not 1m")
    groups = _mapping(payload.get("bars"), f"{kind} candle groups")
    unexpected = set(groups).difference(_SYMBOLS)
    if unexpected:
        raise ValueError(
            f"{kind} source contains unexpected symbols: {sorted(unexpected)}"
        )
    observed_ms = _timestamp_ms(observed_at_utc, f"{kind} observed time")
    duplicates = 0
    for symbol, values in groups.items():
        if not isinstance(values, list):
            raise ValueError(f"{kind} {symbol} candles must be an array")
        for raw in values:
            key, bar = _bar(str(symbol), raw, observed_ms)
            if key[1] < start:
                continue
            prior = output.get(key)
            if prior is not None and prior != bar:
                raise ValueError(
                    f"{kind} source contains a conflicting duplicate candle"
                )
            if prior is not None:
                duplicates += 1
            output[key] = bar
    return duplicates


def _bar(symbol: str, value: object, observed_ms: int) -> tuple[BarKey, Bar]:
    row = _mapping(value, f"{symbol} candle")
    timestamp = _minute_timestamp(row.get("timestamp_ms"), f"{symbol} candle time")
    if timestamp + _MINUTE_MS > observed_ms:
        raise ValueError(f"{symbol} candle was not completed before observation")
    values = tuple(
        _finite_number(row.get(field), f"{symbol} {field}") for field in _BAR_FIELDS
    )
    open_price, high, low, close, volume = values
    if min(open_price, high, low, close) <= 0.0 or volume < 0.0:
        raise ValueError(f"{symbol} candle values are outside their valid domain")
    if high < max(open_price, close) or low > min(open_price, close) or low > high:
        raise ValueError(f"{symbol} candle OHLC is inconsistent")
    return (symbol, timestamp), values


def _comparison(
    live: Mapping[BarKey, Bar], observer: Mapping[BarKey, Bar]
) -> tuple[dict[str, object], set[BarKey]]:
    live_keys, observer_keys = set(live), set(observer)
    shared_cutoff = min(_latest_timestamp(live_keys), _latest_timestamp(observer_keys))
    live_scope = {key for key in live_keys if key[1] <= shared_cutoff}
    observer_scope = {key for key in observer_keys if key[1] <= shared_cutoff}
    common = sorted(live_scope & observer_scope, key=_bar_key_order)
    mismatches: list[dict[str, object]] = []
    exact_keys: set[BarKey] = set()
    for key in common:
        differences = _bar_differences(key, live[key], observer[key])
        mismatches.extend(differences)
        if not differences:
            exact_keys.add(key)
    return {
        "common_ohlcv_rows": len(common),
        "exact_ohlcv_rows": len(exact_keys),
        "mismatches": mismatches,
        "observer_missing_rows": _missing_rows(live_scope - observer_scope),
        "live_missing_rows": _missing_rows(observer_scope - live_scope),
        "trailing_live_only_rows": _missing_rows(live_keys - live_scope),
        "trailing_observer_only_rows": _missing_rows(observer_keys - observer_scope),
        "shared_cutoff_ms": shared_cutoff,
    }, exact_keys


def _bar_differences(key: BarKey, live: Bar, observer: Bar) -> list[dict[str, object]]:
    symbol, timestamp = key
    return [
        {
            "symbol": symbol,
            "timestamp_ms": timestamp,
            "field": field,
            "live": left,
            "observer": right,
        }
        for field, left, right in zip(_BAR_FIELDS, live, observer, strict=True)
        if left != right
    ]


def _missing_rows(keys: set[BarKey]) -> list[dict[str, object]]:
    return [
        {"symbol": symbol, "timestamp_ms": timestamp}
        for symbol, timestamp in sorted(keys, key=_bar_key_order)
    ]


def _latest_timestamp(keys: set[BarKey]) -> int:
    if not keys:
        raise ValueError("candle parity source has no prospective bars")
    return max(timestamp for _symbol, timestamp in keys)


def _bar_key_order(key: BarKey) -> tuple[int, int]:
    symbol, timestamp = key
    return timestamp, _SYMBOL_INDEX[symbol]


def _coverage(
    comparison: Record, exact: set[BarKey], start: int, minimum: int
) -> dict[str, object]:
    minutes = 0
    while all((symbol, start + minutes * _MINUTE_MS) in exact for symbol in _SYMBOLS):
        minutes += 1
    mismatch = bool(comparison["mismatches"])
    missing = bool(
        comparison["observer_missing_rows"] or comparison["live_missing_rows"]
    )
    status = (
        "mismatch"
        if mismatch
        else "incomplete"
        if missing
        else "satisfied"
        if minutes >= minimum
        else "collecting"
    )
    return {
        "contiguous_exact_minutes": minutes,
        "minimum_contiguous_minutes": minimum,
        "prospective_end_exclusive_ms": start + minutes * _MINUTE_MS,
        "gate_status": status,
        "gate_satisfied": status == "satisfied",
    }


def _source_summary(panel: _SourcePanel, run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "profile_fingerprint": panel.profile_fingerprint,
        "run_fingerprint": panel.run_fingerprint,
        "market_candle_events": len(panel.event_sequences),
        "unique_candle_rows": len(panel.bars),
        "duplicate_consistent_rows": panel.duplicate_consistent_rows,
        "first_sequence": min(panel.event_sequences),
        "last_sequence": max(panel.event_sequences),
        "first_observed_at_utc": min(panel.observed_times),
        "last_observed_at_utc": max(panel.observed_times),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "promotion_authority": "none",
    }


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _positive_integer(value: object, label: str) -> int:
    number = _nonnegative_integer(value, label)
    if number == 0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _minute_timestamp(value: object, label: str) -> int:
    timestamp = _nonnegative_integer(value, label)
    if timestamp % _MINUTE_MS:
        raise ValueError(f"{label} must align to one minute")
    return timestamp


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _timestamp_ms(value: object, label: str) -> int:
    text = _text(value, label)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return int(parsed.astimezone(UTC).timestamp() * 1_000)
