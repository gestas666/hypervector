"""Shared identities for the independently journaled HYPE exit experiments."""

HYPE_RELAXED_FIXED_STRATEGY = "hype_breakout_relaxed_60m_bidirectional_v2"
HYPE_RELAXED_TARGET20_STRATEGY = "hype_breakout_relaxed_target20_60m_bidirectional_v3"
HYPE_RELAXED_MATCHED_FIXED_STRATEGY = (
    "hype_breakout_relaxed_fixed60_matched_bidirectional_v4"
)
HYPE_RELAXED_STRATEGIES = frozenset(
    {
        HYPE_RELAXED_FIXED_STRATEGY,
        HYPE_RELAXED_TARGET20_STRATEGY,
        HYPE_RELAXED_MATCHED_FIXED_STRATEGY,
    }
)


def require_hype_relaxed_strategy(value: str) -> str:
    """Return a supported experiment identity or reject cross-experiment state."""
    if value not in HYPE_RELAXED_STRATEGIES:
        raise ValueError(f"unsupported HYPE relaxed strategy identity: {value}")
    return value
