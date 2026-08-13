"""Identity contract for the staged SOL aligned-range live experiment."""

SOL_ALIGNED_RANGE_FIXED60_STRATEGY = (
    "sol_aligned_range_relaxed_fixed60_bidirectional_v1"
)


def require_sol_aligned_range_strategy(value: str) -> str:
    """Return the exact supported strategy identity or reject another family."""
    if value != SOL_ALIGNED_RANGE_FIXED60_STRATEGY:
        raise ValueError(f"unsupported SOL aligned-range strategy identity: {value}")
    return value
