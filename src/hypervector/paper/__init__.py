"""Phase 3 paper: costs, fills, session, live-feed daemon (no venue orders)."""

from hypervector.paper.costs import (
    FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
    CostProvider,
    CostSnapshot,
    funding_payment,
)
from hypervector.paper.fills import ExplicitFillEngine, PaperPosition
from hypervector.paper.ledger import PaperLedgerError, append_paper_decision
from hypervector.paper.runner import PaperDaemonResult, start_paper_daemon
from hypervector.paper.session import PaperSession, PaperSessionResult, run_paper_session_offline

__all__ = [
    "FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1",
    "CostProvider",
    "CostSnapshot",
    "ExplicitFillEngine",
    "PaperDaemonResult",
    "PaperLedgerError",
    "PaperPosition",
    "PaperSession",
    "PaperSessionResult",
    "append_paper_decision",
    "funding_payment",
    "run_paper_session_offline",
    "start_paper_daemon",
]
