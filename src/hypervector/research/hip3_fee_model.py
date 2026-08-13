"""Pure sensitivity model for the documented Hyperliquid HIP-3 fee formula."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

FORMULA_SOURCE = "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees"


@dataclass(frozen=True)
class Hip3FeeInputs:
    """Point-in-time inputs required by the official HIP-3 fee formula."""

    account_maker_rate: float
    account_taker_rate: float
    active_referral_discount: float
    deployer_fee_scale: float
    growth_mode: bool
    aligned_quote: bool
    aligned_quote_status: str
    evidence_label: str

    def __post_init__(self) -> None:
        """Reject incomplete or out-of-domain fee evidence."""
        _bounded_rate(
            self.account_maker_rate, "account_maker_rate", allow_negative=True
        )
        _bounded_rate(self.account_taker_rate, "account_taker_rate")
        _bounded_fraction(
            self.active_referral_discount,
            "active_referral_discount",
            upper_inclusive=False,
        )
        if (
            not isfinite(self.deployer_fee_scale)
            or not 0.0 <= self.deployer_fee_scale <= 3.0
        ):
            raise ValueError("deployer_fee_scale must be finite and between 0 and 3")
        if not isinstance(self.growth_mode, bool):
            raise ValueError("growth_mode must be boolean")
        if not isinstance(self.aligned_quote, bool):
            raise ValueError("aligned_quote must be boolean")
        if not self.aligned_quote_status.strip():
            raise ValueError("aligned_quote_status must be non-empty")
        if not self.evidence_label.strip():
            raise ValueError("evidence_label must be non-empty")


@dataclass(frozen=True)
class EffectiveHip3Fees:
    """Effective rates and bps costs under one explicit fee assumption set."""

    inputs: Hip3FeeInputs
    formula_source: str
    effective_maker_rate: float
    effective_taker_rate: float
    one_way_maker_fee_bps: float
    one_way_taker_fee_bps: float
    round_trip_maker_fee_bps: float
    round_trip_taker_fee_bps: float


def effective_hip3_fees(inputs: Hip3FeeInputs) -> EffectiveHip3Fees:
    """Apply Hyperliquid's published HIP-3 rate scaling formula."""
    hip3_scale = _hip3_scale(inputs.deployer_fee_scale)
    deployer_share = _deployer_share(inputs.deployer_fee_scale)
    growth_scale = 0.1 if inputs.growth_mode else 1.0
    referral_scale = 1.0 - inputs.active_referral_discount
    maker = inputs.account_maker_rate * growth_scale
    if maker > 0.0:
        maker *= hip3_scale * referral_scale
    elif inputs.aligned_quote:
        maker *= (1.0 - deployer_share) * 1.5 + deployer_share
    taker = inputs.account_taker_rate * hip3_scale * growth_scale * referral_scale
    if inputs.aligned_quote:
        taker *= (1.0 - deployer_share) * 0.8 + deployer_share
    maker_bps = maker * 10_000.0
    taker_bps = taker * 10_000.0
    return EffectiveHip3Fees(
        inputs,
        FORMULA_SOURCE,
        maker,
        taker,
        maker_bps,
        taker_bps,
        maker_bps * 2.0,
        taker_bps * 2.0,
    )


def _hip3_scale(deployer_fee_scale: float) -> float:
    return (
        deployer_fee_scale + 1.0
        if deployer_fee_scale < 1.0
        else deployer_fee_scale * 2.0
    )


def _deployer_share(deployer_fee_scale: float) -> float:
    if deployer_fee_scale < 1.0:
        return deployer_fee_scale / (1.0 + deployer_fee_scale)
    return 0.5


def _bounded_rate(value: float, label: str, *, allow_negative: bool = False) -> None:
    lower = -0.01 if allow_negative else 0.0
    if not isfinite(value) or not lower <= value < 0.01:
        qualifier = "between -0.01 and 0.01" if allow_negative else "between 0 and 0.01"
        raise ValueError(f"{label} must be finite and {qualifier}")


def _bounded_fraction(
    value: float,
    label: str,
    *,
    upper_inclusive: bool,
) -> None:
    within_upper = value <= 1.0 if upper_inclusive else value < 1.0
    if not isfinite(value) or value < 0.0 or not within_upper:
        boundary = "inclusive" if upper_inclusive else "exclusive"
        raise ValueError(f"{label} must be in [0, 1] with upper bound {boundary}")
