"""Phase 3 paper: costs, fills, session, live-feed daemon (no venue orders)."""

from hypervector.paper.costs import (
    CostProvider,
    CostSnapshot,
    funding_payment,
)
from hypervector.paper.fill_models import (
    DEFAULT_MAX_BOOK_AGE_MS,
    FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
    FILL_MODEL_L2_WALK_V1,
    FILL_MODEL_TOP_BPS_V1,
    BarCloseSlippageFillModel,
    FillResult,
    L2WalkFillModel,
    TopBpsFillModel,
    select_fill_model,
)
from hypervector.paper.fills import ExplicitFillEngine, PaperPosition
from hypervector.paper.ledger import PaperLedgerError, append_paper_decision
from hypervector.paper.order_intent import (
    NETWORK_MAINNET,
    ORDER_INTENT_SCHEMA,
    build_order_intent,
)
from hypervector.paper.report import (
    default_decisions_path,
    load_decision_rows,
    report_from_data_root,
    summarize_paper_decisions,
)
from hypervector.paper.runner import PaperDaemonResult, start_paper_daemon
from hypervector.paper.session import PaperSession, PaperSessionResult, run_paper_session_offline

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
