"""Frozen candidate identities for Hypervelocity re-entry research."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal

ReentryPolicy = Literal[
    "regime_reset",
    "cooldown_only",
    "target_continuation",
    "target_rsi_reconfirmation",
]


@dataclass(frozen=True)
class ReentryCandidate:
    """One predeclared completed-trade re-entry challenger."""

    candidate_id: str
    policy: ReentryPolicy
    cooldown_seconds: float
    cooldown_bars: int
    clearance_bps: float = 0.0
    target_limit_per_episode: int | None = None
    minimum_episode_seconds: float = 0.0
    minimum_episode_bars: int = 0

    def __post_init__(self) -> None:
        """Reject invalid or incompatible candidate assumptions."""
        if self.cooldown_seconds < 0.0 or self.cooldown_bars < 0:
            raise ValueError("re-entry cooldowns must be non-negative")
        if not math.isfinite(self.clearance_bps) or self.clearance_bps < 0.0:
            raise ValueError("re-entry clearance must be finite and non-negative")
        self._validate_limit()
        self._validate_maturity()

    def _validate_limit(self) -> None:
        limit = self.target_limit_per_episode
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ValueError("target limit per episode must be a positive integer")
        if limit is not None and self.policy != "target_continuation":
            raise ValueError("target limit per episode requires target_continuation")

    def _validate_maturity(self) -> None:
        if (
            not math.isfinite(self.minimum_episode_seconds)
            or self.minimum_episode_seconds < 0.0
        ):
            raise ValueError("minimum episode seconds must be finite and non-negative")
        if (
            isinstance(self.minimum_episode_bars, bool)
            or not isinstance(self.minimum_episode_bars, int)
            or self.minimum_episode_bars < 0
        ):
            raise ValueError("minimum episode bars must be a non-negative integer")
        has_maturity = (
            self.minimum_episode_seconds > 0.0 or self.minimum_episode_bars > 0
        )
        if has_maturity and self.policy != "target_continuation":
            raise ValueError("minimum episode maturity requires target_continuation")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe candidate identity."""
        return asdict(self)


def reentry_candidate_matrix() -> tuple[ReentryCandidate, ...]:
    """Return the fixed control and three source-grounded cooldowns."""
    return (
        ReentryCandidate("regime_reset_60s", "regime_reset", 60.0, 1),
        ReentryCandidate("cooldown_only_60s", "cooldown_only", 60.0, 1),
        ReentryCandidate("cooldown_only_120s", "cooldown_only", 120.0, 2),
        ReentryCandidate("cooldown_only_300s", "cooldown_only", 300.0, 5),
    )


def target_continuation_candidate_matrix() -> tuple[ReentryCandidate, ...]:
    """Return the fixed control and three outcome-aware challengers."""
    return (
        ReentryCandidate("regime_reset_60s", "regime_reset", 60.0, 1),
        ReentryCandidate(
            "target_continuation_0bps", "target_continuation", 60.0, 1, 0.0
        ),
        ReentryCandidate(
            "target_continuation_1bps", "target_continuation", 60.0, 1, 1.0
        ),
        ReentryCandidate(
            "target_continuation_3bps", "target_continuation", 60.0, 1, 3.0
        ),
    )


def bounded_target_ladder_candidate_matrix() -> tuple[ReentryCandidate, ...]:
    """Return the frozen source-bounded target ladder candidates."""
    return (
        ReentryCandidate("regime_reset_60s", "regime_reset", 60.0, 1),
        ReentryCandidate("target_ladder_cap2", "target_continuation", 60.0, 1, 0.0, 2),
        ReentryCandidate("target_ladder_cap3", "target_continuation", 60.0, 1, 0.0, 3),
        ReentryCandidate("target_ladder_cap6", "target_continuation", 60.0, 1, 0.0, 6),
    )


def mature_target_continuation_candidate_matrix() -> tuple[ReentryCandidate, ...]:
    """Return the control, cap-2 reference, and mature cap-2 challenger."""
    return (
        ReentryCandidate("regime_reset_60s", "regime_reset", 60.0, 1),
        ReentryCandidate(
            "target_ladder_cap2",
            "target_continuation",
            60.0,
            1,
            target_limit_per_episode=2,
        ),
        ReentryCandidate(
            "mature_target_ladder_cap2",
            "target_continuation",
            60.0,
            1,
            target_limit_per_episode=2,
            minimum_episode_seconds=1_800.0,
            minimum_episode_bars=30,
        ),
    )


def target_rsi_candidate_matrix() -> tuple[ReentryCandidate, ...]:
    """Return the control and one fixed RSI reconfirmation challenger."""
    return (
        ReentryCandidate("regime_reset_60s", "regime_reset", 60.0, 1),
        ReentryCandidate(
            "target_rsi_reconfirmation_60s",
            "target_rsi_reconfirmation",
            60.0,
            1,
        ),
    )
