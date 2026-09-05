"""Report-only HIP-3 index source and decision transport parity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import cast

import pandas as pd

from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)
from hypervector.research.hip3_index_rest_ledger_parity import (
    reconcile_observer_rest_ledger,
)

Record = dict[str, object]
_BAR_MS = 900_000
_MAXIMUM_PRESSURE_AGE_MS = 15_000
_PRICE_TOLERANCE = 1e-9
_CONTRACT = {
    "report_only": True,
    "execution_authority": "none",
    "automatic_promotion": False,
    "runtime_strategy_changed": False,
}
_LIMITATIONS = [
    "0xArchive evidence has exchange time but no fabricated receive time",
    "raw imbalance values may differ when REST and WebSocket sample times differ",
    "technical source parity does not establish after-cost profitability",
]


@dataclass(frozen=True)
class Hip3IndexSourceParityConfig:
    """Exact route identity and bounded comparison interval."""

    symbol: str
    provider_id: str
    profile_id: str
    start_ms: int
    end_ms: int
    breakout: Hip3BreakoutPressureConfig

    def __post_init__(self) -> None:
        """Reject aliased identities and incomplete 15-minute bounds."""
        validate_market_symbol(self.symbol, "hip3")
        if not self.provider_id.strip() or not self.profile_id.strip():
            raise ValueError("index source parity requires route identity")
        if self.start_ms % _BAR_MS or self.end_ms % _BAR_MS:
            raise ValueError("index source parity bounds must be 15m aligned")
        if self.end_ms <= self.start_ms:
            raise ValueError("index source parity end must follow start")


def build_hip3_index_source_transport_parity(
    *,
    trades: pd.DataFrame,
    archive_books: pd.DataFrame,
    venue_candles: pd.DataFrame,
    rest_book_rows: list[Record],
    observer_rows: list[Record],
    config: Hip3IndexSourceParityConfig,
) -> dict[str, object]:
    """Compare archive and live source decisions without execution authority."""
    candles = _venue_bars(venue_candles, config)
    tape = _trade_bars(trades, config)
    archive_pressure = _archive_pressure(archive_books, config)
    observers = _observer_decisions(observer_rows, config)
    reconcile_observer_rest_ledger(rest_book_rows, observers, config.symbol)
    signals = _archive_signals(candles, archive_pressure, config)
    candle_mismatches = _candle_mismatches(tape, candles)
    pressure_mismatches = _pressure_mismatches(archive_pressure, observers, config)
    signal_mismatches = _signal_mismatches(signals, observers)
    coverage = _coverage(candles, tape, archive_pressure, observers, signals)
    assessment = _assessment(
        coverage, candle_mismatches, pressure_mismatches, signal_mismatches
    )
    return {
        "schema_version": "hip3_index_source_transport_parity_v1",
        "contract": _CONTRACT.copy(),
        "scope": {
            "symbol": config.symbol,
            "provider_id": config.provider_id,
            "profile_id": config.profile_id,
            "start_ms": config.start_ms,
            "end_ms": config.end_ms,
            "breakout": asdict(config.breakout),
        },
        "coverage": coverage,
        "technical_assessment": assessment,
        "mismatches": {
            "candle_ohlc": candle_mismatches,
            "pressure_threshold": pressure_mismatches,
            "signal_decision": signal_mismatches,
        },
        "limitations": _LIMITATIONS.copy(),
    }


def _venue_bars(
    frame: pd.DataFrame, config: Hip3IndexSourceParityConfig
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"venue candle source missing columns: {sorted(missing)}")
    values = frame.loc[:, list(required)].copy()
    values["timestamp"] = pd.to_datetime(values["timestamp"], utc=True)
    values = values.set_index("timestamp").sort_index()
    expected = _expected_index(config)
    values = values.loc[expected[0] : expected[-1]]
    if not values.index.is_unique or not values.index.equals(expected):
        raise ValueError("venue candle source does not cover exact 15m scope")
    output = values[["open", "high", "low", "close"]].astype(float)
    _validate_ohlc(output, "venue")
    return output


def _trade_bars(
    frame: pd.DataFrame, config: Hip3IndexSourceParityConfig
) -> pd.DataFrame:
    required = {"ts_ms", "trade_id", "price", "size"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"trade source missing columns: {sorted(missing)}")
    values = frame.loc[:, list(required)].copy()
    values = values[
        values["ts_ms"].ge(config.start_ms) & values["ts_ms"].lt(config.end_ms)
    ]
    values = values.sort_values(["ts_ms", "trade_id"], kind="stable")
    if values["trade_id"].duplicated().any():
        raise ValueError("trade source contains duplicate trade IDs")
    values["bar_open"] = pd.to_datetime(values["ts_ms"], unit="ms", utc=True).dt.floor(
        "15min"
    )
    grouped = values.groupby("bar_open", sort=True).agg(
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        trades=("price", "size"),
    )
    output = grouped.reindex(_expected_index(config))
    observed = output["trades"].fillna(0).astype(int).gt(0)
    if not observed.all():
        raise ValueError("trade source has a completed 15m bar without prints")
    _validate_ohlc(output[["open", "high", "low", "close"]], "trade")
    return output


def _archive_pressure(
    frame: pd.DataFrame, config: Hip3IndexSourceParityConfig
) -> pd.DataFrame:
    required = {"ts_ms", "obi_10"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"archive pressure missing columns: {sorted(missing)}")
    values = frame.loc[:, ["ts_ms", "obi_10"]].copy()
    values = values[
        values["ts_ms"].ge(config.start_ms) & values["ts_ms"].lt(config.end_ms)
    ].sort_values("ts_ms", kind="stable")
    if values["ts_ms"].duplicated().any():
        raise ValueError("archive pressure contains duplicate exchange timestamps")
    values["bar_open"] = pd.to_datetime(values["ts_ms"], unit="ms", utc=True).dt.floor(
        "15min"
    )
    grouped = values.groupby("bar_open", sort=True).agg(
        snapshot_count=("ts_ms", "size"),
        last_exchange_ts_ms=("ts_ms", "last"),
        imbalance_10=("obi_10", "last"),
    )
    output = grouped.reindex(_expected_index(config))
    close_ms = output.index.as_unit("ms").asi8 + _BAR_MS
    output["end_boundary_age_ms"] = close_ms - output["last_exchange_ts_ms"]
    output["fresh"] = output["snapshot_count"].ge(2) & output[
        "end_boundary_age_ms"
    ].between(0, _MAXIMUM_PRESSURE_AGE_MS)
    output["signal_imbalance_10"] = output["imbalance_10"].where(output["fresh"], 0.0)
    return output


def _observer_decisions(
    rows: list[Record], config: Hip3IndexSourceParityConfig
) -> list[Record]:
    selected: list[Record] = []
    seen: set[int] = set()
    for row in rows:
        decision = _mapping(row.get("decision"), "observer decision")
        _validate_observer_contract(row, decision, config)
        boundary = _integer(decision, "decision_time_ms")
        if not config.start_ms < boundary <= config.end_ms:
            continue
        if boundary in seen:
            raise ValueError("observer decisions contain a duplicate boundary")
        seen.add(boundary)
        selected.append(decision)
    if not selected:
        raise ValueError("observer decisions do not overlap comparison scope")
    return sorted(selected, key=lambda row: _integer(row, "decision_time_ms"))


def _validate_observer_contract(
    row: Record, decision: Record, config: Hip3IndexSourceParityConfig
) -> None:
    valid = (
        row.get("report_only") is True
        and row.get("execution_authority") == "none"
        and row.get("runtime_strategy_changed") is False
        and row.get("intents") == []
        and decision.get("execution_authority") == "none"
        and decision.get("prospective") is True
        and decision.get("symbol") == config.symbol
        and decision.get("provider_id") == config.provider_id
        and decision.get("profile_id") == config.profile_id
    )
    if not valid:
        raise ValueError("observer decision authority or identity is invalid")


def _archive_signals(
    candles: pd.DataFrame,
    pressure: pd.DataFrame,
    config: Hip3IndexSourceParityConfig,
) -> pd.DataFrame:
    inputs = candles.copy()
    inputs["decision_imbalance_10"] = pressure["signal_imbalance_10"]
    inputs["gap_before_bars"] = 0
    return build_breakout_pressure_signals(inputs, config.breakout, timeframe="15m")


def _candle_mismatches(trade: pd.DataFrame, venue: pd.DataFrame) -> list[Record]:
    output: list[Record] = []
    for timestamp in venue.index:
        fields = [
            field
            for field in ("open", "high", "low", "close")
            if not math.isclose(
                float(trade.at[timestamp, field]),
                float(venue.at[timestamp, field]),
                rel_tol=0.0,
                abs_tol=_PRICE_TOLERANCE,
            )
        ]
        if fields:
            bar_open_ms = int(timestamp.timestamp() * 1_000)
            output.append({"bar_open_ms": bar_open_ms, "fields": fields})
    return output


def _pressure_mismatches(
    pressure: pd.DataFrame,
    observers: list[Record],
    config: Hip3IndexSourceParityConfig,
) -> list[Record]:
    output: list[Record] = []
    threshold = config.breakout.minimum_abs_imbalance
    for decision in observers:
        boundary = _integer(decision, "decision_time_ms")
        timestamp = pd.to_datetime(boundary - _BAR_MS, unit="ms", utc=True)
        archive_fresh = bool(pressure.at[timestamp, "fresh"])
        archive_state = _pressure_state(
            float(pressure.at[timestamp, "signal_imbalance_10"]), threshold
        )
        rest_fresh = _boolean(decision, "pressure_fresh")
        rest_state = _pressure_state(
            _number(decision, "decision_imbalance_10") if rest_fresh else 0.0,
            threshold,
        )
        if (archive_fresh, archive_state) != (rest_fresh, rest_state):
            output.append(
                {
                    "decision_time_ms": boundary,
                    "archive_fresh": archive_fresh,
                    "archive_state": archive_state,
                    "rest_fresh": rest_fresh,
                    "rest_state": rest_state,
                }
            )
    return output


def _signal_mismatches(signals: pd.DataFrame, observers: list[Record]) -> list[Record]:
    output: list[Record] = []
    for decision in observers:
        boundary = _integer(decision, "decision_time_ms")
        timestamp = pd.to_datetime(boundary - _BAR_MS, unit="ms", utc=True)
        long_entry = bool(signals.at[timestamp, "long_entry"])
        short_entry = bool(signals.at[timestamp, "short_entry"])
        archive_side = "long" if long_entry else "short" if short_entry else None
        archive_eligible = archive_side is not None
        if archive_eligible != _boolean(decision, "eligible") or (
            archive_side != decision.get("side")
        ):
            output.append(
                {
                    "decision_time_ms": boundary,
                    "archive_eligible": archive_eligible,
                    "archive_side": archive_side,
                    "observer_eligible": _boolean(decision, "eligible"),
                    "observer_side": decision.get("side"),
                }
            )
    return output


def _coverage(
    candles: pd.DataFrame,
    trades: pd.DataFrame,
    pressure: pd.DataFrame,
    observers: list[Record],
    signals: pd.DataFrame,
) -> dict[str, object]:
    observer_eligible = sum(_boolean(row, "eligible") for row in observers)
    signal_rows = [
        signals.loc[
            pd.to_datetime(
                _integer(row, "decision_time_ms") - _BAR_MS, unit="ms", utc=True
            )
        ]
        for row in observers
    ]
    archive_eligible = sum(
        bool(row["long_entry"]) or bool(row["short_entry"]) for row in signal_rows
    )
    return {
        "completed_bars": len(candles),
        "trade_bars": len(trades),
        "archive_pressure_bars": len(pressure),
        "archive_fresh_pressure_bars": int(pressure["fresh"].sum()),
        "observer_decisions": len(observers),
        "observer_eligible_decisions": observer_eligible,
        "archive_eligible_decisions": archive_eligible,
    }


def _assessment(
    coverage: Record,
    candle: list[Record],
    pressure: list[Record],
    signal: list[Record],
) -> dict[str, bool]:
    non_vacuous = (
        int(coverage["observer_eligible_decisions"]) > 0
        or int(coverage["archive_eligible_decisions"]) > 0
    )
    return {
        "observer_rest_ledger_reconciled": True,
        "trade_candle_ohlc_parity_resolved": not candle,
        "pressure_threshold_parity_resolved": not pressure,
        "signal_decision_parity_resolved": not signal,
        "decision_parity_non_vacuous": non_vacuous,
        "source_transport_parity_resolved": not candle
        and not pressure
        and not signal
        and non_vacuous,
    }


def _validate_ohlc(frame: pd.DataFrame, label: str) -> None:
    finite = frame.map(lambda value: math.isfinite(float(value)) and float(value) > 0)
    if not finite.to_numpy().all():
        raise ValueError(f"{label} OHLC must be positive and finite")
    if frame["high"].lt(frame[["open", "low", "close"]].max(axis=1)).any():
        raise ValueError(f"{label} OHLC high is inconsistent")
    if frame["low"].gt(frame[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError(f"{label} OHLC low is inconsistent")


def _pressure_state(value: float, threshold: float) -> str:
    if value >= threshold:
        return "long"
    if value <= -threshold:
        return "short"
    return "neutral"


def _expected_index(config: Hip3IndexSourceParityConfig) -> pd.DatetimeIndex:
    start = pd.to_datetime(config.start_ms, unit="ms", utc=True)
    end = pd.to_datetime(config.end_ms - _BAR_MS, unit="ms", utc=True)
    return pd.date_range(start, end, freq="15min", inclusive="both")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(Record, value)


def _integer(value: Record, key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"{key} must be an integer")
    return selected


def _number(value: Record, key: str) -> float:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, (int, float)):
        raise ValueError(f"{key} must be numeric")
    number = float(selected)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number


def _boolean(value: Record, key: str) -> bool:
    selected = value.get(key)
    if not isinstance(selected, bool):
        raise ValueError(f"{key} must be boolean")
    return selected
