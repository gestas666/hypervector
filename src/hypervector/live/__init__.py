"""Lazy public exports for Hypervector live services."""

from importlib import import_module

_EXPORTS = {
    "HyperliquidLiveExecClient": (
        "hypervector.live.exec_client",
        "HyperliquidLiveExecClient",
    ),
    "LiveExecClient": ("hypervector.live.exec_client", "LiveExecClient"),
    "PlaceResult": ("hypervector.live.exec_client", "PlaceResult"),
    "create_live_exec_client": (
        "hypervector.live.exec_client",
        "create_live_exec_client",
    ),
    "create_live_exec_client_from_env": (
        "hypervector.live.exec_client",
        "create_live_exec_client_from_env",
    ),
    "is_submit_wired": ("hypervector.live.exec_client", "is_submit_wired"),
    "LiveLedgerError": ("hypervector.live.ledger", "LiveLedgerError"),
    "append_live_decision": ("hypervector.live.ledger", "append_live_decision"),
    "LivePolicy": ("hypervector.live.policy", "LivePolicy"),
    "LivePolicyError": ("hypervector.live.policy", "LivePolicyError"),
    "live_policy_from_env": ("hypervector.live.policy", "live_policy_from_env"),
    "live_report_from_data_root": ("hypervector.live.report", "report_from_data_root"),
    "summarize_live_decisions": ("hypervector.live.report", "summarize_live_decisions"),
    "LiveDaemonResult": ("hypervector.live.runner", "LiveDaemonResult"),
    "start_live_daemon": ("hypervector.live.runner", "start_live_daemon"),
}

__all__ = [
    "HyperliquidLiveExecClient",
    "LiveDaemonResult",
    "LiveExecClient",
    "LiveLedgerError",
    "LivePolicy",
    "LivePolicyError",
    "PlaceResult",
    "append_live_decision",
    "create_live_exec_client",
    "create_live_exec_client_from_env",
    "is_submit_wired",
    "live_policy_from_env",
    "live_report_from_data_root",
    "start_live_daemon",
    "summarize_live_decisions",
]


def __getattr__(name: str) -> object:
    """Resolve public services without importing unrelated execution engines."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value
