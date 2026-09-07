"""Frozen exploratory activity evidence for the three non-crypto additions."""

from hypervector.live.hourly_price_provider import (
    BAND_REENTRY_STRATEGY,
    DONCHIAN20_STRATEGY,
    DONCHIAN8_STRATEGY,
)

_REVIEW = "docs/reviews/2026-09-07-frequency-and-noncrypto-expansion.md"
_COMMON = " $500 conditional notional; native OHLC proxies. Exploratory, not untouched OOS or live fills."


def hourly_price_evidence_rows() -> tuple[
    tuple[str, str, str, str, str, str, str], ...
]:
    """Expose measured cadence and limitations without changing route authority."""
    return (
        (
            BAND_REENTRY_STRATEGY,
            "xyz:SPCX",
            "exploratory_candidate_concentrated",
            "low",
            "52 modeled trades / 48 days (1.08/day); 61.5% net wins",
            "Adverse-cost net +$43.79; development +$25.10, extension +$13.45; "
            "excluding top three winners -$7.05." + _COMMON,
            _REVIEW,
        ),
        (
            DONCHIAN20_STRATEGY,
            "xyz:SNDK",
            "exploratory_later_partition_negative",
            "low",
            "47 modeled trades / 48 days (0.98/day); 31.9% net wins",
            "Adverse-cost net +$120.85; development +$147.08, extension -$24.93; "
            "excluding top three winners -$107.38." + _COMMON,
            _REVIEW,
        ),
        (
            DONCHIAN8_STRATEGY,
            "xyz:BRENTOIL",
            "exploratory_candidate_concentrated",
            "low",
            "61 modeled trades / 48 days (1.27/day); 32.8% net wins",
            "Adverse-cost net +$32.86; development +$25.76, extension +$6.25; "
            "excluding top three winners -$42.41." + _COMMON,
            _REVIEW,
        ),
    )
