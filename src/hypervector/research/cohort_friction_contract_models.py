"""Typed modeled execution contract used by friction comparison."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModeledExecutionContract:
    """Research mechanics cited for one live provider identity."""

    entry_liquidity: str
    entry_fee_bps: float
    entry_slippage_bps: float | None
    stop_policy: str
    stop_bps: float | None
    minimum_stop_bps: float | None
    maximum_stop_bps: float | None
    maximum_hold_seconds: int | None
    maximum_hold_policy: str
    hard_maximum_hold_seconds: int | None
    target_policy: str
    target_liquidity: str | None
    target_bps: float | None
    target_r_multiple: float | None
    evidence_source: str

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-safe modeled contract projection."""
        return asdict(self)
