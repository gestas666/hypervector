"""Dispatch validated Hypervelocity runtime profile families."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

from hypervector.strategies.hypervelocity_profile import (
    HypervelocityProfile,
    load_hypervelocity_profile,
)
from hypervector.strategies.source_follow_profile import (
    load_source_follow_profile,
)

_SOURCE_PROFILES = frozenset(
    {
        "hypervelocity_source_follow_shadow_v1",
        "hypervelocity_source_follow_minrange12_shadow_v1",
        "hypervelocity_source_follow_minrange12_alloc35_shadow_v1",
        "hypervelocity_source_follow_session_06_15_minrange12_alloc35_shadow_v1",
        "hypervelocity_source_follow_bidirectional_minrange12_alloc35_shadow_v1",
        "hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow_v1",
    }
)


def load_hypervelocity_runtime_profile(path: Path | str) -> HypervelocityProfile:
    """Load the faithful or source-follow runtime profile without fallback."""
    profile_path = Path(path)
    if not profile_path.is_file():
        raise FileNotFoundError(f"Hypervelocity config not found: {profile_path}")
    with profile_path.open("rb") as handle:
        raw = cast(dict[str, object], tomllib.load(handle))
    profile_id = raw.get("profile")
    if profile_id in _SOURCE_PROFILES:
        return load_source_follow_profile(profile_path)
    return load_hypervelocity_profile(profile_path)
