"""Narrow retry classification for mutable V58 research snapshots."""

from __future__ import annotations

from hypervector.live.transient_transport import transient_read_failure_reason

CONTINUOUS_TRANSIENT_RETRY_SECONDS = {"concurrent_source_refresh": 1.0}

_CONCURRENT_REFRESH_MESSAGES = frozenset(
    {
        "V58 ETH lifecycle status changed during path evaluation",
        "V58 ETH lifecycle status changed during lock evaluation",
        "V58 checkpoint changed during ETH exit-policy evaluation",
        "V58 live backend checkpoint changed while reading",
        "V58 live backend checkpoint changed during evaluation",
        "V58 venue preflight changed while reading",
        "V58 venue preflight changed during evaluation",
        "V58 runtime checkpoint evidence changed",
        "V58 return context is not synchronized across symbols",
        "V58 venue portfolio is temporarily unavailable",
        "route lifecycle status is stale",
    }
)


def continuous_transient_failure_reason(exc: Exception) -> str | None:
    """Classify only safe transport or atomic-snapshot refresh races."""
    if isinstance(exc, ValueError) and str(exc) in _CONCURRENT_REFRESH_MESSAGES:
        if str(exc) == "V58 venue portfolio is temporarily unavailable":
            return "venue_portfolio_unavailable"
        return "concurrent_source_refresh"
    return transient_read_failure_reason(exc)
