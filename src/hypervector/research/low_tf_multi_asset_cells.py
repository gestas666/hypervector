"""Declared low-timeframe strategy-cell identities."""

from __future__ import annotations

LowTfCell = tuple[str, str, str]


def declared_low_tf_cells() -> tuple[LowTfCell, ...]:
    """Return every family/side/exit identity, including zero-signal cells."""
    symmetric: tuple[tuple[str, tuple[str, str]], ...] = (
        (
            "range_reclaim_v1",
            ("range_close_invalidation", "range_wick_atr_stop"),
        ),
        (
            "trend_expansion_v1",
            ("rsi_reversal_exit", "ema_alignment_exit"),
        ),
        (
            "pmarp_exhaustion_v1",
            ("ema_mean_exit", "pmarp_opposite_extreme_exit"),
        ),
        (
            "krown_ema55_touch_v1",
            (
                "krown_touch_close_stop_rsi_div",
                "krown_touch_hard_stop_rsi_div",
            ),
        ),
    )
    bidirectional = tuple(
        (family, side, variant)
        for family, variants in symmetric
        for side in ("long", "short")
        for variant in variants
    )
    controls = (
        (
            "krown_pullback_long_v1",
            "long",
            "krown_close_stop_pmarp80",
        ),
        (
            "krown_pullback_long_v1",
            "long",
            "krown_hard_stop_pmarp80",
        ),
    )
    return (*bidirectional, *controls)
