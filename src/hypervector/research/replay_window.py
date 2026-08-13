"""Validated causal windows for report-only replay commands."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd


@dataclass(frozen=True)
class ReplayWindow:
    """UTC bounds separating development evidence from fresh evidence."""

    data_start: datetime
    fresh_start: datetime
    data_end: datetime

    def __post_init__(self) -> None:
        if not self.data_start <= self.fresh_start < self.data_end:
            raise ValueError(
                "replay window requires data_start <= fresh_start < data_end"
            )

    def to_dict(self) -> dict[str, str]:
        """Serialize the immutable UTC replay bounds."""
        return {
            "data_start": self.data_start.isoformat(),
            "fresh_start": self.fresh_start.isoformat(),
            "data_end": self.data_end.isoformat(),
        }


_DEFAULT_WINDOW = ReplayWindow(
    data_start=datetime(2026, 4, 28, tzinfo=UTC),
    fresh_start=datetime(2026, 7, 27, tzinfo=UTC),
    data_end=datetime(2026, 7, 28, tzinfo=UTC),
)


def add_replay_window_arguments(parser: argparse.ArgumentParser) -> None:
    """Add backward-compatible explicit UTC replay bounds to one parser."""
    parser.add_argument(
        "--data-start", type=_utc_datetime, default=_DEFAULT_WINDOW.data_start
    )
    parser.add_argument(
        "--fresh-start", type=_utc_datetime, default=_DEFAULT_WINDOW.fresh_start
    )
    parser.add_argument(
        "--data-end", type=_utc_datetime, default=_DEFAULT_WINDOW.data_end
    )


def validate_replay_window(args: argparse.Namespace) -> ReplayWindow:
    """Construct and validate replay bounds parsed from the command line."""
    return ReplayWindow(args.data_start, args.fresh_start, args.data_end)


def partition_replay_events(
    events: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep causal decisions in bounds and split development from fresh."""
    window = validate_replay_window(args)
    decision_time = pd.to_datetime(events["decision_time_utc"], utc=True)
    bounded = decision_time.ge(window.data_start) & decision_time.lt(window.data_end)
    development = bounded & decision_time.lt(window.fresh_start)
    fresh = bounded & decision_time.ge(window.fresh_start)
    return (
        events.loc[development].reset_index(drop=True),
        events.loc[fresh].reset_index(drop=True),
    )


def _utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid UTC timestamp: {value}") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset or Z")
    return parsed.astimezone(UTC)
