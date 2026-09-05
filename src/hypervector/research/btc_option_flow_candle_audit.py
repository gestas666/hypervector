"""Outcome-blind cadence audits for BTC option-flow candle sources."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CandleGap:
    """Describe one consecutive run of absent one-minute candles."""

    start_utc: pd.Timestamp
    end_utc_exclusive: pd.Timestamp
    minutes: int
    repairable: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation of the gap."""
        return {
            "start_utc": self.start_utc.isoformat(),
            "end_utc_exclusive": self.end_utc_exclusive.isoformat(),
            "minutes": self.minutes,
            "repairable": self.repairable,
        }


@dataclass(frozen=True)
class CandleCadenceAudit:
    """Summarize whether a candle source satisfies its cadence contract."""

    start_utc: pd.Timestamp
    end_utc_exclusive: pd.Timestamp
    expected_rows: int
    observed_rows: int
    missing_rows: int
    gap_run_count: int
    maximum_gap_minutes: int
    repairable_missing_rows: int
    rejected_missing_rows: int
    leading_gap: bool
    trailing_gap: bool
    contract_pass: bool
    gaps: tuple[CandleGap, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation of the audit."""
        return {
            "start_utc": self.start_utc.isoformat(),
            "end_utc_exclusive": self.end_utc_exclusive.isoformat(),
            "expected_rows": self.expected_rows,
            "observed_rows": self.observed_rows,
            "missing_rows": self.missing_rows,
            "gap_run_count": self.gap_run_count,
            "maximum_gap_minutes": self.maximum_gap_minutes,
            "repairable_missing_rows": self.repairable_missing_rows,
            "rejected_missing_rows": self.rejected_missing_rows,
            "leading_gap": self.leading_gap,
            "trailing_gap": self.trailing_gap,
            "contract_pass": self.contract_pass,
            "gaps": [gap.to_dict() for gap in self.gaps],
        }


def _validated_bound(value: pd.Timestamp, *, name: str) -> pd.Timestamp:
    bound = pd.Timestamp(value)
    if bound.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    bound = bound.tz_convert("UTC")
    if bound != bound.floor("min"):
        raise ValueError(f"{name} must align to a whole minute")
    return bound


def _validated_timestamps(
    frame: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DatetimeIndex:
    if "timestamp" not in frame.columns:
        raise ValueError("candle frame must contain a timestamp column")
    timestamps = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], errors="raise"))
    if timestamps.tz is None:
        raise ValueError("candle timestamps must be timezone-aware")
    timestamps = timestamps.tz_convert("UTC")
    if not timestamps.is_monotonic_increasing or timestamps.has_duplicates:
        raise ValueError("candle timestamps must be ordered and unique")
    if not timestamps.empty and (timestamps[0] < start or timestamps[-1] >= end):
        raise ValueError(
            "candle timestamps must lie inside the half-open audit interval"
        )
    if any(timestamp != timestamp.floor("min") for timestamp in timestamps):
        raise ValueError("candle timestamps must align to whole minutes")
    return timestamps


def _gap_from_run(run: list[pd.Timestamp], maximum: int) -> CandleGap:
    minutes = len(run)
    return CandleGap(
        start_utc=run[0],
        end_utc_exclusive=run[-1] + pd.Timedelta(minutes=1),
        minutes=minutes,
        repairable=minutes <= maximum,
    )


def _group_missing_minutes(
    missing: pd.DatetimeIndex,
    *,
    maximum: int,
) -> tuple[CandleGap, ...]:
    if missing.empty:
        return ()
    gaps: list[CandleGap] = []
    run = [missing[0]]
    for timestamp in missing[1:]:
        if timestamp == run[-1] + pd.Timedelta(minutes=1):
            run.append(timestamp)
            continue
        gaps.append(_gap_from_run(run, maximum))
        run = [timestamp]
    gaps.append(_gap_from_run(run, maximum))
    return tuple(gaps)


def audit_candle_cadence(
    frame: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    maximum_repair_minutes: int,
) -> CandleCadenceAudit:
    """Audit a one-minute candle frame without using market outcomes."""
    start_utc = _validated_bound(start, name="start")
    end_utc = _validated_bound(end, name="end")
    if end_utc <= start_utc:
        raise ValueError("end must be later than start")
    if maximum_repair_minutes < 1:
        raise ValueError("maximum_repair_minutes must be positive")
    observed = _validated_timestamps(frame, start=start_utc, end=end_utc)
    expected = pd.date_range(start_utc, end_utc, inclusive="left", freq="1min")
    missing = expected.difference(observed)
    gaps = _group_missing_minutes(missing, maximum=maximum_repair_minutes)
    leading_gap = bool(gaps and gaps[0].start_utc == start_utc)
    trailing_gap = bool(gaps and gaps[-1].end_utc_exclusive == end_utc)
    rejected = sum(gap.minutes for gap in gaps if not gap.repairable)
    repairable = sum(gap.minutes for gap in gaps if gap.repairable)
    return CandleCadenceAudit(
        start_utc=start_utc,
        end_utc_exclusive=end_utc,
        expected_rows=len(expected),
        observed_rows=len(observed),
        missing_rows=len(missing),
        gap_run_count=len(gaps),
        maximum_gap_minutes=max((gap.minutes for gap in gaps), default=0),
        repairable_missing_rows=repairable,
        rejected_missing_rows=rejected,
        leading_gap=leading_gap,
        trailing_gap=trailing_gap,
        contract_pass=not leading_gap and not trailing_gap and rejected == 0,
        gaps=gaps,
    )


def build_candle_source_record(
    frame: pd.DataFrame,
    *,
    source_revision: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    maximum_repair_minutes: int,
    expected_contract_pass: bool,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    """Bind one cadence audit to its immutable source evidence and expectation."""
    if not source_revision.strip():
        raise ValueError("source_revision must be nonempty")
    audit = audit_candle_cadence(
        frame,
        start=start,
        end=end,
        maximum_repair_minutes=maximum_repair_minutes,
    )
    if audit.contract_pass is not expected_contract_pass:
        raise ValueError("observed candle contract result differs from expectation")
    return {
        "source_revision": source_revision,
        "expected_contract_pass": expected_contract_pass,
        "maximum_repair_minutes": maximum_repair_minutes,
        "evidence": dict(evidence),
        "audit": audit.to_dict(),
    }
