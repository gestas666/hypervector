"""Read-only session identity payload sections for backend-authored telemetry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypervector.paper.order_intent import NETWORK_MAINNET
from hypervector.paper.session_configuration import (
    _effective_execution,
    _effective_exits,
    _effective_risk,
    _effective_strategy_params,
)
from hypervector.strategies.registry import execution_profile

if TYPE_CHECKING:
    from hypervector.paper.session import PaperSession

#: Bar-driven paper execution: one intent per completed bar, filled by the
#: session's fill model (or resting post-only entries when declared).
PAPER_EXECUTION_MODEL = "paper_bar_v1"


def session_identity_payload(session: PaperSession) -> dict[str, object]:
    """Build the public session_start identity from its meaning-named sections.

    Section order is the payload key order; keep it stable for consumers.
    """
    return {
        **_section_identity(session),
        **_section_model(session),
        **_section_strategy_policy(session),
        **_section_risk_costs(session),
        **_section_runtime(session),
        **_section_portfolio_state(session),
    }


def _section_identity(session: PaperSession) -> dict[str, object]:
    return {
        "feed_ts": "session_start",
        "run_id": session.run_id,
        "export_id": str(session.export_id),
        "strategy_name": session.strategy_name,
        "symbol": session.loadout.symbol,
        "timeframe": session.loadout.timeframe,
        "data_root": str(session.root.resolve()),
        "action": "session_start",
        "execution_model": PAPER_EXECUTION_MODEL,
    }


def _section_model(session: PaperSession) -> dict[str, object]:
    return {
        "conviction": session.conviction,
        "metalabel_mode": session.metalabel_mode,
        "metalabel_bundle_id": session.conviction_provider.bundle_id,
    }


def _section_strategy_policy(session: PaperSession) -> dict[str, object]:
    return {
        "strategy_params": {
            "strategy": session.loadout.strategy_name,
            **_effective_strategy_params(session.loadout),
        },
        "execution_profile": execution_profile(
            session.loadout.strategy_name
        ).to_dict(),
        "portfolio_spec": session._portfolio_spec,
        "portfolio_fingerprint": session._portfolio_fingerprint,
    }


def _section_risk_costs(session: PaperSession) -> dict[str, object]:
    return {
        "exits": _effective_exits(session.loadout),
        "risk": _effective_risk(session.loadout),
        "execution": _effective_execution(session.loadout),
        "costs": dict(session.loadout.costs or {}),
    }


def _section_runtime(session: PaperSession) -> dict[str, object]:
    return {
        "runtime": {
            "lookback_days": session.lookback_days,
            "live_activated_at": session._live_activated_at.isoformat()
            if session._live_activated_at is not None
            else None,
        }
    }


def _section_portfolio_state(session: PaperSession) -> dict[str, object]:
    position = session.engine.position
    return {
        "bars_processed": session.bars_processed,
        "execution_mode": session.execution_mode,
        "submitted": False,
        "network": NETWORK_MAINNET,
        "position_qty": float(position.qty),
        "position_avg_px": float(position.avg_px),
        "realized_pnl": float(position.realized_pnl),
        "unrealized_pnl": 0.0,
        "equity": float(session.equity),
        "init_cash": float(session.engine.initial_cash),
        "no_submit": True,
    }
