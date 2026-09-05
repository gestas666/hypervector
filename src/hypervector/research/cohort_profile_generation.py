"""Exact profile-generation labels for cohort research telemetry."""

from __future__ import annotations

import re

_GENERATION = re.compile(r"(?:^|[_-])v(\d+)(?:$|[_-])", re.IGNORECASE)
_LEGACY_TRAILING_GENERATION = re.compile(r"(?:^|[_-])(\d+)$")


def cohort_profile_generation(profile_id: str) -> str:
    """Return the final explicit generation token from a cohort profile ID."""
    normalized = profile_id.strip()
    if not normalized:
        raise ValueError("cohort profile identity must be non-empty text")
    matches = _GENERATION.findall(normalized)
    if matches:
        return f"v{matches[-1]}"
    legacy = _LEGACY_TRAILING_GENERATION.search(normalized)
    if legacy is not None:
        return f"v{legacy.group(1)}"
    raise ValueError("cohort profile identity lacks a version generation")


def cohort_hypothesis_text(experiment: str, generation: str) -> str:
    """Describe a generation-bound live-translation research hypothesis."""
    if experiment == "collect_route_specific_regime_context_evidence":
        return (
            "route-specific clear multi-timeframe context improves the exact "
            f"{generation} route after costs"
        )
    return f"the exact {generation} route retains after-cost edge in its intended conditions"
