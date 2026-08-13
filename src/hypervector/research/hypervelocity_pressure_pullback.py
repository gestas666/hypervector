"""Causal, report-only opposing-book-pressure entry timing."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from hypervector.data.oxa_archive_audit import OxaArchiveBundle
from hypervector.research.hypervelocity_attribution import align_book_pressure
from hypervector.research.hypervelocity_attribution_io import (
    load_native_book_pressure,
)

_PRESSURE_COLUMNS = (
    "ts_ms",
    "obi_5",
    "obi_20",
    "spread_bps",
    "micro_price_delta_bps",
    "best_bid",
    "best_ask",
    "best_bid_size",
    "best_ask_size",
)


def _validate_decisions(decisions: pd.DataFrame) -> None:
    required = {"entry_direction", "structural_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"pressure pullback decisions missing: {sorted(missing)}")
    if not isinstance(decisions.index, pd.DatetimeIndex):
        raise ValueError("pressure pullback decisions require a DatetimeIndex")
    if not decisions.index.is_monotonic_increasing or decisions.index.has_duplicates:
        raise ValueError(
            "pressure pullback decision index must be unique and increasing"
        )
    valid = decisions["entry_direction"].dropna().isin(("long", "short"))
    if not valid.all():
        raise ValueError("pressure pullback entry directions must be long|short|null")


def _empty_pressure() -> pd.DataFrame:
    return pd.DataFrame(columns=_PRESSURE_COLUMNS)


def _load_bundle(bundle: OxaArchiveBundle) -> pd.DataFrame:
    if bundle.book_path is None:
        return _empty_pressure()
    return load_native_book_pressure(bundle.book_path)


def _combined_pressure(
    previous: pd.DataFrame,
    current: pd.DataFrame,
) -> pd.DataFrame:
    frames = [frame for frame in (previous, current) if not frame.empty]
    if not frames:
        return _empty_pressure()
    combined = pd.concat(frames, ignore_index=True)
    return (
        combined.sort_values("ts_ms", kind="stable")
        .drop_duplicates("ts_ms", keep="last")
        .reset_index(drop=True)
    )


def _trailing_pressure(current: pd.DataFrame) -> pd.DataFrame:
    if current.empty:
        return current
    cutoff = int(current["ts_ms"].iloc[-1]) - 10_000
    return current.loc[current["ts_ms"].ge(cutoff)].reset_index(drop=True)


def decision_book_pressure(
    decisions: pd.DataFrame,
    bundles: Iterable[OxaArchiveBundle],
    *,
    max_age_ms: int = 2_000,
) -> pd.Series:
    """Return latest causal top-five OBI when each decision bar is available."""
    _validate_decisions(decisions)
    if max_age_ms < 0:
        raise ValueError("pressure pullback maximum age must be non-negative")
    availability = decisions.index + pd.Timedelta(minutes=1)
    result = pd.Series(float("nan"), index=decisions.index, dtype="float64")
    previous = _empty_pressure()
    for bundle in bundles:
        start, end = pd.Timestamp(bundle.start), pd.Timestamp(bundle.end)
        selected = availability[(availability >= start) & (availability < end)]
        current = _load_bundle(bundle)
        if len(selected):
            evidence = _combined_pressure(previous, current)
            aligned = align_book_pressure(
                selected,
                evidence,
                max_age_ms=max_age_ms,
                trailing_window_ms=5_000,
            )
            result.loc[selected - pd.Timedelta(minutes=1)] = aligned["obi_5"].to_numpy()
        if not current.empty:
            previous = _trailing_pressure(current)
    return result


def _alignment(direction: pd.Series, pressure: pd.Series) -> pd.Series:
    sign = direction.map({"long": 1.0, "short": -1.0})
    directional = sign * pressure
    alignment = pd.Series("missing", index=direction.index, dtype=object)
    observed = sign.notna() & pressure.notna()
    alignment = alignment.mask(observed & directional.lt(0.0), "opposed")
    alignment = alignment.mask(observed & directional.gt(0.0), "aligned")
    return alignment.mask(observed & directional.eq(0.0), "neutral")


def apply_opposed_pressure_gate(
    decisions: pd.DataFrame,
    pressure: pd.Series,
) -> pd.DataFrame:
    """Permit entries only during opposing top-five displayed-book pressure."""
    _validate_decisions(decisions)
    if not pressure.index.equals(decisions.index):
        raise ValueError("pressure pullback evidence must share the decision index")
    numeric = pd.to_numeric(pressure, errors="coerce").astype(float)
    output = decisions.copy()
    alignment = _alignment(output["entry_direction"], numeric)
    passed = alignment.eq("opposed")
    output["entry_pressure_obi5"] = numeric
    output["entry_pressure_alignment"] = alignment
    output["entry_pressure_gate_passed"] = passed
    gated = [
        value if allowed else None
        for value, allowed in zip(output["entry_direction"], passed, strict=True)
    ]
    output["entry_direction"] = pd.Series(gated, index=output.index, dtype=object)
    return output


def _event_row(
    timestamps: np.ndarray,
    obi_5: np.ndarray,
    start_ms: int,
    end_ms: int,
    direction: str,
    source_time: pd.Timestamp,
) -> dict[str, object] | None:
    first = int(np.searchsorted(timestamps, start_ms, side="left"))
    last = int(np.searchsorted(timestamps, end_ms, side="left"))
    if first >= last:
        return None
    sign = 1.0 if direction == "long" else -1.0
    opposed = np.flatnonzero(sign * obi_5[first:last] < 0.0)
    if not len(opposed):
        return None
    position = first + int(opposed[0])
    snapshot_ms = int(timestamps[position])
    event_time = pd.to_datetime(snapshot_ms, unit="ms", utc=True)
    return {
        "source_decision_time": source_time,
        "event_time": event_time,
        "direction": direction,
        "obi_5": float(obi_5[position]),
        "snapshot_ts_ms": snapshot_ms,
    }


def _bundle_event_rows(
    decisions: pd.DataFrame,
    availability: pd.DatetimeIndex,
    bundle: OxaArchiveBundle,
) -> list[dict[str, object]]:
    if bundle.book_path is None:
        return []
    start, end = pd.Timestamp(bundle.start), pd.Timestamp(bundle.end)
    selected = np.flatnonzero((availability >= start) & (availability < end))
    if not len(selected):
        return []
    pressure = _load_bundle(bundle)
    timestamps = pressure["ts_ms"].to_numpy(dtype=np.int64)
    obi_5 = pressure["obi_5"].to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    for position in selected:
        direction = decisions["entry_direction"].iloc[position]
        if direction not in ("long", "short"):
            continue
        available = availability[position]
        row = _event_row(
            timestamps,
            obi_5,
            available.value // 1_000_000,
            min(available + pd.Timedelta(minutes=1), end).value // 1_000_000,
            str(direction),
            pd.Timestamp(decisions.index[position]),
        )
        if row is not None:
            rows.append(row)
    return rows


def _event_frame(
    decisions: pd.DataFrame,
    evidence: pd.DataFrame,
) -> pd.DataFrame:
    states = decisions.loc[:, ["structural_direction"]].copy()
    states["entry_direction"] = pd.Series(None, index=states.index, dtype=object)
    states["decision_kind"] = "bar_state"
    if evidence.empty:
        return states
    event_index = pd.DatetimeIndex(evidence["event_time"]) - pd.Timedelta(minutes=1)
    events = pd.DataFrame(
        {
            "structural_direction": evidence["direction"].to_numpy(),
            "entry_direction": evidence["direction"].to_numpy(),
            "decision_kind": "opposed_obi5_event",
        },
        index=event_index,
    )
    combined = pd.concat([states, events]).sort_index(kind="stable")
    if combined.index.has_duplicates:
        combined = combined.groupby(level=0, sort=True).tail(1)
    return combined


def opposed_pressure_event_decisions(
    decisions: pd.DataFrame,
    bundles: Iterable[OxaArchiveBundle],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Emit the first opposing OBI5 snapshot within each eligible minute."""
    _validate_decisions(decisions)
    availability = decisions.index + pd.Timedelta(minutes=1)
    rows: list[dict[str, object]] = []
    for bundle in bundles:
        rows.extend(_bundle_event_rows(decisions, availability, bundle))
    evidence = pd.DataFrame(
        rows,
        columns=(
            "source_decision_time",
            "event_time",
            "direction",
            "obi_5",
            "snapshot_ts_ms",
        ),
    )
    return _event_frame(decisions, evidence), evidence
