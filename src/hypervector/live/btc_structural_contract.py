"""Identity and immutable timing contract for the BTC structural candidate."""

BTC_STRUCTURAL_FIXED60_STRATEGY = "btc_structural_continuation_fixed60_bidirectional_v1"


def require_btc_structural_strategy(value: str) -> str:
    """Return the supported identity or reject cross-strategy cadence state."""
    if value != BTC_STRUCTURAL_FIXED60_STRATEGY:
        raise ValueError(f"unsupported BTC structural strategy identity: {value}")
    return value
