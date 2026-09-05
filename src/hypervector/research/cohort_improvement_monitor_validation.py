"""Input validation for the report-only cohort improvement monitor."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import math

Record = Mapping[str, object]


def validate_checkpoint_freshness(
    checkpoint: Record,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> None:
    """Reject future, stale, or malformed checkpoint timestamps."""
    if not math.isfinite(maximum_age_seconds) or maximum_age_seconds <= 0.0:
        raise ValueError("maximum checkpoint age must be positive and finite")
    generated_at = _timestamp(checkpoint.get("generated_at_utc"))
    age = (observed_at - generated_at).total_seconds()
    if age < 0.0:
        raise ValueError("checkpoint generation time is in the future")
    if age > maximum_age_seconds:
        raise ValueError(
            f"checkpoint is stale: age={age:.3f}s limit={maximum_age_seconds:.3f}s"
        )


def validate_loop_args(args: argparse.Namespace) -> None:
    """Reject invalid monitor loop and evidence-freshness bounds."""
    fields = (
        ("interval_seconds", "improvement monitor interval"),
        ("maximum_checkpoint_age_seconds", "maximum checkpoint age"),
        ("maximum_sol_observer_age_seconds", "maximum SOL observer age"),
        ("maximum_index_mark_recorder_age_seconds", "maximum mark recorder age"),
        ("maximum_external_observer_age_seconds", "maximum external observer age"),
        (
            "maximum_hype_native_lifecycle_age_seconds",
            "maximum HYPE lifecycle age",
        ),
    )
    for field, label in fields:
        value = getattr(args, field)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{label} must be positive and finite")
    if args.max_cycles < 0:
        raise ValueError("improvement monitor max cycles cannot be negative")


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("checkpoint generation time must be non-empty text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("checkpoint generation time must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("checkpoint generation time must include a timezone")
    return parsed.astimezone(UTC)
