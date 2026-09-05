"""Durable source-candle evidence shared by report-only HIP-3 observers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import cast

import pandas as pd

_SOURCE_FIELDS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class ShadowCandleContract:
    """Freeze one exact source-candle identity and observation cadence."""

    symbol: str
    source: str
    event_type: str
    interval_ms: int
    maximum_observation_delay_ms: int
    revision_tolerant_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject incomplete identities or invalid timing bounds."""
        if not self.symbol or not self.source or not self.event_type:
            raise ValueError("shadow candle identity fields must be non-empty")
        if self.interval_ms <= 0 or self.maximum_observation_delay_ms < 0:
            raise ValueError("shadow candle timing bounds are invalid")
        if set(self.revision_tolerant_fields).difference(_SOURCE_FIELDS):
            raise ValueError("shadow candle revision fields are invalid")


@dataclass(frozen=True)
class ShadowCandleAppendResult:
    """Return frozen source rows and disclosed tolerated revisions."""

    frame: pd.DataFrame
    revision_rows: int
    revision_fields: tuple[str, ...]
    revision_bar_open_ms: tuple[int, ...]


def append_candles_once(
    path: Path,
    frame: pd.DataFrame,
    *,
    contract: ShadowCandleContract,
    observed_at_ms: int,
    prior_boundary_ms: int,
) -> ShadowCandleAppendResult:
    """Append each completed source candle once with causal provenance."""
    observed = _nonnegative_integer(observed_at_ms, "observed_at_ms")
    prior = _nonnegative_integer(prior_boundary_ms, "prior_boundary_ms")
    _validate_frame(frame)
    existing = _candle_rows_by_timestamp(path, contract)
    frozen = frame.copy()
    revision_bars: set[int] = set()
    revision_fields: set[str] = set()
    for timestamp, row in frame.iterrows():
        open_ms = int(pd.Timestamp(timestamp).timestamp() * 1_000)
        candidate = _candle_row(
            row,
            contract=contract,
            open_ms=open_ms,
            observed_at_ms=observed,
            prior_boundary_ms=prior,
        )
        validate_candle_row(candidate, contract)
        prior_row = existing.get(open_ms)
        if prior_row is not None:
            changed = _changed_source_fields(prior_row, candidate)
            if changed:
                _require_tolerated_revision(changed, contract)
                revision_bars.add(open_ms)
                revision_fields.update(changed)
                for field in changed:
                    frozen.at[timestamp, field] = prior_row[field]
            continue
        append_jsonl(path, candidate)
    return ShadowCandleAppendResult(
        frozen,
        len(revision_bars),
        tuple(sorted(revision_fields)),
        tuple(sorted(revision_bars)),
    )


def validate_candle_row(
    row: Mapping[str, object], contract: ShadowCandleContract
) -> None:
    """Validate one stored candle against its exact source/timing contract."""
    identity = (
        row.get("schema_version") == 1
        and row.get("event_type") == contract.event_type
        and row.get("symbol") == contract.symbol
        and row.get("source") == contract.source
        and row.get("execution_authority") == "none"
    )
    opened = _nonnegative_integer(row.get("bar_open_ms"), "bar_open_ms")
    closed = _nonnegative_integer(row.get("bar_close_ms"), "bar_close_ms")
    observed = _nonnegative_integer(row.get("observed_at_ms"), "observed_at_ms")
    historical = _boolean(row.get("historical_warmup"), "historical_warmup")
    prospective = _boolean(row.get("prospective"), "prospective")
    for key in ("open", "high", "low", "close", "volume"):
        _finite_number(row.get(key), key)
    delay_ms = observed - closed
    expected_prospective = (
        not historical and 0 <= delay_ms <= contract.maximum_observation_delay_ms
    )
    if (
        not identity
        or closed - opened != contract.interval_ms
        or delay_ms < 0
        or prospective is not expected_prospective
    ):
        raise ValueError("shadow candle row violates its source contract")


def candle_summary(path: Path) -> dict[str, object]:
    """Return cumulative historical and prospective candle counts."""
    if not path.exists():
        return {
            "candle_rows_total": 0,
            "prospective_candle_rows_total": 0,
            "late_non_warmup_candle_rows_total": 0,
        }
    rows = jsonl_rows(path, "candle")
    return {
        "candle_rows_total": len(rows),
        "prospective_candle_rows_total": sum(
            row.get("prospective") is True for row in rows
        ),
        "late_non_warmup_candle_rows_total": sum(
            row.get("historical_warmup") is False and row.get("prospective") is False
            for row in rows
        ),
    }


def source_revision_status(
    path: Path,
    *,
    current_bars: tuple[int, ...],
    current_fields: tuple[str, ...],
    allowed_fields: tuple[str, ...],
) -> dict[str, object]:
    """Carry forward disclosure of every tolerated source revision."""
    prior: dict[str, object] = {}
    if path.exists():
        prior = _object(json.loads(path.read_text(encoding="utf-8")), "status")
    prior_bars = _revision_bars(prior.get("source_revision_bar_open_ms_total", []))
    prior_fields = _revision_fields(
        prior.get("source_revision_fields_total", []), allowed_fields
    )
    bars = prior_bars.union(_revision_bars(list(current_bars)))
    fields = prior_fields.union(_revision_fields(list(current_fields), allowed_fields))
    return {
        "source_revision_rows_current_snapshot": len(current_bars),
        "source_revision_fields_current_snapshot": list(current_fields),
        "source_revision_rows_total": len(bars),
        "source_revision_bar_open_ms_total": sorted(bars),
        "source_revision_fields_total": sorted(fields),
    }


def append_jsonl(path: Path, payload: Mapping[str, object]) -> None:
    """Append and fsync one canonical JSON object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def jsonl_rows(path: Path, label: str) -> tuple[dict[str, object], ...]:
    """Load validated JSON objects from one JSONL file."""
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            rows.append(_object(json.loads(line), f"{label} line {line_number}"))
    return tuple(rows)


def _candle_row(
    row: pd.Series,
    *,
    contract: ShadowCandleContract,
    open_ms: int,
    observed_at_ms: int,
    prior_boundary_ms: int,
) -> dict[str, object]:
    close_ms = open_ms + contract.interval_ms
    historical_warmup = close_ms <= prior_boundary_ms
    delay_ms = observed_at_ms - close_ms
    prospective = (
        not historical_warmup and 0 <= delay_ms <= contract.maximum_observation_delay_ms
    )
    return {
        "schema_version": 1,
        "event_type": contract.event_type,
        "symbol": contract.symbol,
        "source": contract.source,
        "bar_open_ms": open_ms,
        "bar_close_ms": close_ms,
        "observed_at_ms": observed_at_ms,
        "open": _finite_number(row["open"], "open"),
        "high": _finite_number(row["high"], "high"),
        "low": _finite_number(row["low"], "low"),
        "close": _finite_number(row["close"], "close"),
        "volume": _finite_number(row["volume"], "volume"),
        "historical_warmup": historical_warmup,
        "prospective": prospective,
        "execution_authority": "none",
    }


def _validate_frame(frame: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"shadow candle frame missing columns: {missing}")
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None or not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("shadow candle index must be ordered, unique, and UTC-aware")


def _candle_rows_by_timestamp(
    path: Path, contract: ShadowCandleContract
) -> dict[int, dict[str, object]]:
    if not path.exists():
        return {}
    rows: dict[int, dict[str, object]] = {}
    for row in jsonl_rows(path, "candle"):
        validate_candle_row(row, contract)
        value = _nonnegative_integer(row.get("bar_open_ms"), "bar_open_ms")
        if value in rows:
            raise ValueError("shadow candle ledger contains a duplicate bar")
        rows[value] = row
    return rows


def _changed_source_fields(
    prior: Mapping[str, object], candidate: Mapping[str, object]
) -> tuple[str, ...]:
    return tuple(
        field for field in _SOURCE_FIELDS if prior.get(field) != candidate.get(field)
    )


def _require_tolerated_revision(
    changed: tuple[str, ...], contract: ShadowCandleContract
) -> None:
    if set(changed).difference(contract.revision_tolerant_fields):
        raise ValueError("shadow ledger contains a changed source candle")


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"shadow candle {label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"shadow candle {label} must be finite")
    return numeric


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"shadow candle {label} must be boolean")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"shadow candle {label} must be a nonnegative integer")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"shadow candle {label} must be an object")
    return cast(dict[str, object], value)


def _revision_bars(value: object) -> set[int]:
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 0
        for item in value
    ):
        raise ValueError("shadow candle revision bars are invalid")
    return set(cast(list[int], value))


def _revision_fields(value: object, allowed_fields: tuple[str, ...]) -> set[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or item not in allowed_fields for item in value
    ):
        raise ValueError("shadow candle revision fields are invalid")
    return set(cast(list[str], value))
