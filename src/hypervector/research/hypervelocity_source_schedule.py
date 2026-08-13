"""Point-in-time decisions derived from reconciled source entry timestamps."""

from __future__ import annotations

import math

import pandas as pd

_REQUIRED_COLUMNS = {"open_ts", "side", "timestamp_provenance"}
_SUPPLEMENTAL_COLUMNS = {"open_time_utc", "side", "entry_price"}
_SUPPLEMENTAL_OPTIONAL_COLUMNS = {"exit_price", "outcome_time_utc"}


def merge_supplemental_positions(
    logical: pd.DataFrame,
    supplemental: pd.DataFrame,
) -> pd.DataFrame:
    """Merge outcome-backed screenshot entries, replacing matching trackers."""
    if "entry_price" not in logical:
        raise ValueError("logical source positions require entry_price for merge")
    missing = _SUPPLEMENTAL_COLUMNS.difference(supplemental.columns)
    if missing:
        raise ValueError(f"supplemental source positions missing: {sorted(missing)}")
    base = logical.copy()
    selected = _SUPPLEMENTAL_COLUMNS | (
        _SUPPLEMENTAL_OPTIONAL_COLUMNS & set(supplemental.columns)
    )
    extra = supplemental.loc[:, sorted(selected)].copy()
    extra["open_ts"] = pd.to_datetime(
        extra.pop("open_time_utc"), utc=True, format="ISO8601"
    )
    extra["side"] = extra["side"].astype(str).str.lower()
    extra["entry_price"] = pd.to_numeric(extra["entry_price"], errors="coerce")
    if extra[["open_ts", "entry_price"]].isna().any().any():
        raise ValueError("supplemental source positions contain invalid values")
    if not extra["side"].isin(("long", "short")).all():
        raise ValueError("supplemental source position side must be long or short")
    if "exit_price" in extra:
        extra["exit_price"] = pd.to_numeric(extra["exit_price"], errors="coerce")
    if "outcome_time_utc" in extra:
        extra["close_ts"] = pd.to_datetime(
            extra.pop("outcome_time_utc"),
            utc=True,
            errors="coerce",
            format="ISO8601",
        )
    extra["timestamp_provenance"] = "screenshot_outcome_backed"
    combined = pd.concat([base, extra], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(["open_ts", "side", "entry_price"], keep="last")
    return combined.sort_values("open_ts", kind="stable").reset_index(drop=True)


def _validated_positions(logical: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED_COLUMNS.difference(logical.columns)
    if missing:
        raise ValueError(f"logical source positions missing: {sorted(missing)}")
    frame = logical.copy()
    frame["open_ts"] = pd.to_datetime(frame["open_ts"], utc=True)
    if frame.empty or frame["open_ts"].isna().any():
        raise ValueError("logical source positions require valid open timestamps")
    if not frame["side"].isin(("long", "short")).all():
        raise ValueError("logical source position side must be long or short")
    frame = frame.sort_values("open_ts", kind="stable").reset_index(drop=True)
    if frame["open_ts"].duplicated().any():
        raise ValueError("logical source positions have duplicate open timestamps")
    return frame


def source_schedule_decisions(
    logical: pd.DataFrame,
    *,
    reset_lead_seconds: float = 5.0,
) -> pd.DataFrame:
    """Create one causal entry event per reconciled source position.

    A short non-directional interval before each event clears replay-only
    completed or expired intent. It does not close an existing position.
    """
    if not math.isfinite(reset_lead_seconds) or reset_lead_seconds <= 0.0:
        raise ValueError("source schedule reset lead must be positive and finite")
    frame = _validated_positions(logical)
    lead = pd.Timedelta(seconds=reset_lead_seconds)
    availability_shift = pd.Timedelta(minutes=1)
    rows: list[dict[str, object]] = []
    indexes: list[pd.Timestamp] = []
    for event_id, row in frame.iterrows():
        open_time = pd.Timestamp(row["open_ts"])
        shared = {
            "source_event_id": int(event_id),
            "source_open_time_utc": open_time.isoformat(),
            "timestamp_provenance": str(row["timestamp_provenance"]),
        }
        indexes.append(open_time - lead - availability_shift)
        rows.append(
            {
                **shared,
                "entry_direction": None,
                "structural_direction": None,
                "decision_kind": "source_rearm",
            }
        )
        indexes.append(open_time - availability_shift)
        rows.append(
            {
                **shared,
                "entry_direction": str(row["side"]),
                "structural_direction": str(row["side"]),
                "decision_kind": "source_entry",
            }
        )
    output = pd.DataFrame(rows, index=pd.DatetimeIndex(indexes))
    output = output.sort_index(kind="stable")
    if output.index.has_duplicates:
        raise ValueError("source schedule decisions collide at the same timestamp")
    for name in ("entry_direction", "structural_direction"):
        output[name] = output[name].astype(object)
    return output
