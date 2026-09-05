"""Source-backed route scope for continuous cohort research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

Record = Mapping[str, object]
_SIDES = frozenset({"long", "short"})


def configured_research_directions(checkpoint: Record) -> dict[str, list[str]]:
    """Prefer explicit observation sides while supporting legacy checkpoints."""
    generation = _mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    if generation.get("matches_runtime") is not True:
        raise ValueError(
            "continuous research requires the current runtime configuration"
        )
    raw = generation.get("current_provider_observation_directions")
    if raw is None:
        raw = generation.get("current_provider_execution_directions")
    routes = _mapping(raw, "route directions")
    return {route: _directions(value, route) for route, value in sorted(routes.items())}


def configured_execution_directions(checkpoint: Record) -> dict[str, list[str]]:
    """Return only routes with explicit execution authority in the live config."""
    generation = _mapping(
        checkpoint.get("configuration_generation"), "configuration generation"
    )
    if generation.get("matches_runtime") is not True:
        raise ValueError(
            "continuous research requires the current runtime configuration"
        )
    routes = _mapping(
        generation.get("current_provider_execution_directions"),
        "execution route directions",
    )
    return {route: _directions(value, route) for route, value in sorted(routes.items())}


def _directions(value: object, route: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"configured directions must be a non-empty array: {route}")
    directions = sorted({_text(side, "configured side") for side in value})
    if not directions or set(directions) - _SIDES or len(directions) != len(value):
        raise ValueError(f"configured directions are invalid: {route}")
    return directions


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
