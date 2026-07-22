"""Phase 3 paper identity — decision/fill scaffolding (no live feed loop yet)."""

from hypervector.paper.costs import (
    FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1,
    CostProvider,
    CostSnapshot,
    funding_payment,
)
from hypervector.paper.fills import ExplicitFillEngine, PaperPosition
from hypervector.paper.ledger import PaperLedgerError, append_paper_decision

__all__ = [
    "FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1",
    "CostProvider",
    "CostSnapshot",
    "ExplicitFillEngine",
    "PaperLedgerError",
    "PaperPosition",
    "append_paper_decision",
    "funding_payment",
]
