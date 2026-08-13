"""Internal replay state for one-blocker execution feasibility."""

from __future__ import annotations

from dataclasses import dataclass

from hypervector.research.market_depth_fill import DepthLevel


@dataclass(frozen=True)
class Book:
    """Validated top-of-book observation used by the causal replay."""

    recv_ts_ms: int
    opi: float
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]


@dataclass
class Coverage:
    """Selection and execution attrition counters for one replay."""

    evaluations: int = 0
    pre_cutoff_excluded: int = 0
    exact_candidates: int = 0
    context_missing: int = 0
    context_stale: int = 0
    context_cohort_excluded: int = 0
    selected_non_overlapping: int = 0
    entry_missing: int = 0
    entry_capacity_failures: int = 0
    exit_pending: int = 0
    exit_missing: int = 0
    exit_capacity_failures: int = 0
    resolved_executions: int = 0

    def as_payload(self) -> dict[str, int]:
        """Return complete selection and execution attrition."""
        return dict(vars(self))
