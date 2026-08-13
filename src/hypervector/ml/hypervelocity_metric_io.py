"""JSON-safe serialization helpers for Hypervelocity model diagnostics."""

from __future__ import annotations

import math
from collections.abc import Mapping


def json_safe_metrics(
    metrics: Mapping[str, Mapping[str, float | int | None]],
) -> dict[str, dict[str, float | int | None]]:
    """Replace undefined non-finite diagnostics with explicit JSON nulls."""
    return {
        name: {
            key: None
            if isinstance(value, float) and not math.isfinite(value)
            else value
            for key, value in values.items()
        }
        for name, values in metrics.items()
    }
