"""Frozen exploratory evidence for the hourly price routes, by review.

Rows are keyed by (strategy, symbol). A later row with the same key supersedes an
earlier one when the evidence table is built, which is how a newer review replaces
an older statement about the same route. Nothing here changes route authority.
"""

from hypervector.live.hourly_price_provider import (
    BAND_REENTRY_STRATEGY,
    DONCHIAN20_STRATEGY,
    DONCHIAN8_STRATEGY,
    PROTECTED_DONCHIAN20_SYMBOLS,
    PROTECTED_DONCHIAN20_STRATEGY,
    STRONG_SHORT_DONCHIAN20_STRATEGY,
)

EvidenceRow = tuple[str, str, str, str, str, str, str]

_V89_REVIEW = "docs/reviews/2026-09-07-frequency-and-noncrypto-expansion.md"
_V89_COMMON = (
    " $500 conditional notional; native OHLC proxies. Exploratory, not untouched "
    "OOS or live fills."
)
_V90_PLAN = "docs/plans/2026-09-20-v90-aggressive-bankroll-builder.md"
_V90_EXIT_REVIEW = "docs/reviews/2026-09-21-v90-profit-lock-exit-review.md"
_V90_COMMON = (
    " $500 conditional notional; native 15m OHLC proxies. Nets are quoted at the "
    "measured live costs (0.864 / 4.32 bps fees) with the adverse arm (5.5 bps "
    "slippage) beside them. The modeled friction contract is bound to that adverse "
    "arm on the routes V90 adds or moves (SOL, xyz:BRENTOIL, xyz:TSLA); xyz:SNDK "
    "keeps the frozen V89 nominal contract at 2.5 bps slippage. Every window is a broadly rising tape on which buy-and-hold beat the "
    "mechanism on most symbols. Not untouched OOS or live fills."
)
_PROTECTED_REVIEW = "docs/reviews/2026-09-21-v90-profit-protection-readiness.md"
_V94_RESCORE = "docs/research-journal/v94-weak-short-rescore-20260924-v1.json"
_V94_COMMON = (
    " Mechanism level, pre-registered bar passed 4 of 4 (V93 sizing, v2 exits): "
    "recent 8-asset +$431.39 measured / +$547.75 adverse, one-year crypto "
    "+$798.30 / +$1,065.87, live-4 recent +$210.09 / +$289.65. Not out of sample: "
    "the 1 ATR split was found on these same windows after 5 split families were "
    "examined. The live-4 gain is SNDK-concentrated (without SNDK -$2.65 measured "
    "/ +$25.35 adverse), and the rule also skips winners (largest $66.58 recent). "
    "The modeled contract is the re-score's adverse arm. Not live fills."
)


def hourly_price_evidence_rows() -> tuple[EvidenceRow, ...]:
    """Expose measured cadence and limitations without changing route authority."""
    return _v89_rows() + _v90_rows() + _protected_rows() + _v94_strong_short_rows()


def _v89_rows() -> tuple[EvidenceRow, ...]:
    """The 2026-09-07 selection screen: 48 days, 10x, adverse cost."""
    return (
        (
            BAND_REENTRY_STRATEGY,
            "xyz:SPCX",
            "exploratory_candidate_concentrated",
            "low",
            "52 modeled trades / 48 days (1.08/day); 61.5% net wins",
            "Adverse-cost net +$43.79; development +$25.10, extension +$13.45; "
            "excluding top three winners -$7.05." + _V89_COMMON,
            _V89_REVIEW,
        ),
        (
            DONCHIAN20_STRATEGY,
            "xyz:SNDK",
            "exploratory_later_partition_negative",
            "low",
            "47 modeled trades / 48 days (0.98/day); 31.9% net wins",
            "Adverse-cost net +$120.85; development +$147.08, extension -$24.93; "
            "excluding top three winners -$107.38." + _V89_COMMON,
            _V89_REVIEW,
        ),
        (
            DONCHIAN8_STRATEGY,
            "xyz:BRENTOIL",
            "exploratory_candidate_concentrated",
            "low",
            "61 modeled trades / 48 days (1.27/day); 32.8% net wins",
            "Adverse-cost net +$32.86; development +$25.76, extension +$6.25; "
            "excluding top three winners -$42.41." + _V89_COMMON,
            _V89_REVIEW,
        ),
    )


def _v90_rows() -> tuple[EvidenceRow, ...]:
    """The 2026-09-20/21 screens for every route V90 sizes, moves or adds.

    The SNDK row supersedes the V89 row above for the same key: the mechanism is
    unchanged, but V90 raises its notional about 3.9x, and the evidence must say
    that this is a risk preference the screens do not validate.
    """
    return (
        (
            DONCHIAN20_STRATEGY,
            "xyz:SNDK",
            "exploratory_positive_all_windows_size_raised_3_9x_unvalidated",
            "low",
            "61 modeled trades / 63 days (0.97/day) at 8x; 34.4% net wins",
            "Measured-cost net +$177.96 (adverse +$134.47), payoff ratio 2.82, "
            "PF 1.48, largest trade $91.48; one liquidation at 10x that 8x removes. "
            "The separate 10x screen (screen_63d_known8_H1_M15.json) records three "
            "positive calendar blocks measured and two of three adverse; the 8x "
            "roster screen quoted here does not partition by block. The frozen 48-day selection screen remains the prior "
            "record: adverse +$120.85, extension partition -$24.93, -$107.38 "
            "excluding its top three winners. V90 raises the route from ~$500 to "
            "~$1,948 notional. "
            "Every screen cell is $500; nothing measures behaviour at that size, so "
            "the increase is an operator risk preference, not a validated "
            "improvement. Every tested profit lock reduced this route, the proposed "
            "100/25/50 to +$1.48." + _V90_COMMON,
            _V90_EXIT_REVIEW,
        ),
        (
            DONCHIAN20_STRATEGY,
            "SOL",
            "exploratory_candidate_two_windows_positive",
            "low",
            "47 modeled trades / 63 days (0.75/day) at 8x; 44.7% net wins",
            "Measured-cost net +$197.56 (adverse +$176.23), PF 2.52; 52-day breadth "
            "screen at 10x +$188.44 with 2 of 3 blocks positive and +$68.63 over "
            "time-in-market-scaled buy-and-hold. Development partition of the "
            "frozen 48-day screen was -$31.48; rank 1 of 8 Donchian cells, so "
            "budget zero." + _V90_COMMON,
            _V90_PLAN,
        ),
        (
            DONCHIAN20_STRATEGY,
            "xyz:BRENTOIL",
            "mechanism_standardisation_untested",
            "low",
            "52 modeled trades / 63 days (0.83/day) at 8x; 36.5% net wins",
            "Measured-cost net +$41.79 (adverse +$18.96), PF 1.23; 52-day breadth "
            "screen at 10x +$32.10 with 2 of 3 blocks positive but below scaled "
            "buy-and-hold by $25.68. Moved from Donchian 8/4 as a consequence of "
            "standardising on one mechanism; the 20/10 vs 8/4 contrast is p=0.52 "
            "and about 60% of the 20/10 cell is funding carry." + _V90_COMMON,
            _V90_PLAN,
        ),
        (
            DONCHIAN20_STRATEGY,
            "xyz:TSLA",
            "exploratory_addition_failed_predeclared_bar",
            "low",
            "51 modeled trades / 52 days (0.98/day) at 10x; 35.3% net wins",
            "Measured-cost net +$25.29 (adverse +$2.87); the only new market of 18 "
            "positive in all 3 blocks, but below time-in-market-scaled buy-and-hold "
            "by $20.65, t=0.54, and the pick of 18. Screened at 10x with no "
            "liquidation, so the 8x the profile runs changes only the liquidation "
            "buffer. Admitted as an operator scope choice at the screened $500 "
            "contract; 0 of 18 new markets passed the bar written before results "
            "(section 10.6)." + _V90_COMMON,
            _V90_PLAN,
        ),
    )


def _protected_rows() -> tuple[EvidenceRow, ...]:
    """The identity-bound lock, evidenced only on the three symbols it may run on."""
    return tuple(
        (
            PROTECTED_DONCHIAN20_STRATEGY,
            symbol,
            "profit_protection_candidate_unconfirmed",
            "low",
            "Completed hourly entries; 1-minute profit-lock decisions",
            "100-bps activation, 25-bps gross floor, 50-bps trail. "
            "Exploratory delayed-exit proxies; no confirmed forward return or floor. "
            "Preserves recipe exits and initial venue protection. Not configured in "
            "V90: on the routes it funds the lock cut net from +$417 to +$137 "
            "(" + _V90_EXIT_REVIEW + ").",
            _PROTECTED_REVIEW,
        )
        for symbol in sorted(PROTECTED_DONCHIAN20_SYMBOLS)
    )


def _v94_strong_short_rows() -> tuple[EvidenceRow, ...]:
    """The 2026-09-24 weak-short re-score, quoted per route from its recent cell.

    The rule ships on every Donchian route because it passed at mechanism level;
    the per-route deltas below are small samples and two of them are negative.
    """
    routes = (
        (
            "SOL",
            "18 weak shorts skipped / recent window",
            "Recent-window delta -$19.11 measured / -$7.24 adverse; one-year "
            "+$190.29 / +$240.19 over 122-123 skipped shorts.",
        ),
        (
            "xyz:SNDK",
            "20 weak shorts skipped / recent window",
            "Recent-window delta +$212.74 measured / +$264.30 adverse; this route "
            "carries most of the live-4 gain.",
        ),
        (
            "xyz:BRENTOIL",
            "18 weak shorts skipped / recent window",
            "Recent-window delta +$20.98 measured / +$28.21 adverse.",
        ),
        (
            "xyz:TSLA",
            "17 weak shorts skipped / recent window",
            "Recent-window delta -$4.52 measured / +$4.39 adverse.",
        ),
    )
    return tuple(
        (
            STRONG_SHORT_DONCHIAN20_STRATEGY,
            symbol,
            "preregistered_rescore_passed_in_sample",
            "low",
            cadence,
            route + _V94_COMMON,
            _V94_RESCORE,
        )
        for symbol, cadence, route in routes
    )
