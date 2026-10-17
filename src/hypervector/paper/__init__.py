"""Lazy public exports for Hypervector paper services."""

from importlib import import_module

_EXPORTS = {
    "CostProvider": ("hypervector.paper.costs", "CostProvider"),
    "CostSnapshot": ("hypervector.paper.costs", "CostSnapshot"),
    "funding_payment": ("hypervector.paper.costs", "funding_payment"),
    "DEFAULT_MAX_BOOK_AGE_MS": (
        "hypervector.paper.fill_models",
        "DEFAULT_MAX_BOOK_AGE_MS",
    ),
    "FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1": (
        "hypervector.paper.fill_models",
        "FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1",
    ),
    "FILL_MODEL_L2_WALK_V1": ("hypervector.paper.fill_models", "FILL_MODEL_L2_WALK_V1"),
    "FILL_MODEL_TOP_BPS_V1": ("hypervector.paper.fill_models", "FILL_MODEL_TOP_BPS_V1"),
    "BarCloseSlippageFillModel": (
        "hypervector.paper.fill_models",
        "BarCloseSlippageFillModel",
    ),
    "FillResult": ("hypervector.paper.fill_models", "FillResult"),
    "L2WalkFillModel": ("hypervector.paper.fill_models", "L2WalkFillModel"),
    "TopBpsFillModel": ("hypervector.paper.fill_models", "TopBpsFillModel"),
    "select_fill_model": ("hypervector.paper.fill_models", "select_fill_model"),
    "ExplicitFillEngine": ("hypervector.paper.fills", "ExplicitFillEngine"),
    "PaperPosition": ("hypervector.paper.fills", "PaperPosition"),
    "PaperLedgerError": ("hypervector.paper.ledger", "PaperLedgerError"),
    "append_paper_decision": ("hypervector.paper.ledger", "append_paper_decision"),
    "NETWORK_MAINNET": ("hypervector.paper.order_intent", "NETWORK_MAINNET"),
    "ORDER_INTENT_SCHEMA": ("hypervector.paper.order_intent", "ORDER_INTENT_SCHEMA"),
    "build_order_intent": ("hypervector.paper.order_intent", "build_order_intent"),
    "default_decisions_path": ("hypervector.paper.report", "default_decisions_path"),
    "load_decision_rows": ("hypervector.paper.report", "load_decision_rows"),
    "report_from_data_root": ("hypervector.paper.report", "report_from_data_root"),
    "summarize_paper_decisions": (
        "hypervector.paper.report",
        "summarize_paper_decisions",
    ),
    "PaperDaemonResult": ("hypervector.paper.runner", "PaperDaemonResult"),
    "start_paper_daemon": ("hypervector.paper.runner", "start_paper_daemon"),
    "PaperSession": ("hypervector.paper.session", "PaperSession"),
    "PaperSessionResult": ("hypervector.paper.session", "PaperSessionResult"),
    "run_paper_session_offline": (
        "hypervector.paper.session",
        "run_paper_session_offline",
    ),
}

__all__ = [
    "DEFAULT_MAX_BOOK_AGE_MS",
    "FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1",
    "FILL_MODEL_L2_WALK_V1",
    "FILL_MODEL_TOP_BPS_V1",
    "NETWORK_MAINNET",
    "ORDER_INTENT_SCHEMA",
    "BarCloseSlippageFillModel",
    "CostProvider",
    "CostSnapshot",
    "ExplicitFillEngine",
    "FillResult",
    "L2WalkFillModel",
    "TopBpsFillModel",
    "PaperDaemonResult",
    "PaperLedgerError",
    "PaperPosition",
    "PaperSession",
    "PaperSessionResult",
    "append_paper_decision",
    "build_order_intent",
    "default_decisions_path",
    "funding_payment",
    "load_decision_rows",
    "report_from_data_root",
    "run_paper_session_offline",
    "select_fill_model",
    "start_paper_daemon",
    "summarize_paper_decisions",
]


def __getattr__(name: str) -> object:
    """Resolve public services without importing unrelated execution engines."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value
