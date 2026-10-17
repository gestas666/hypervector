"""Read-only session identity payload sections for backend-authored telemetry."""

from __future__ import annotations
from typing import TYPE_CHECKING
from hypervector.paper.order_intent import NETWORK_MAINNET
from hypervector.paper.liquidation_execution import (
    LIQUIDATION_EXECUTION_MODEL,
    PARTIAL_LIQUIDATION_SUPPORTED,
)
from hypervector.strategies.source_follow_profile import (
    SourceFollowHypervelocityProfile,
)
from hypervector.paper.session_configuration import (
    _source_follow_metalabel_policy,
    _effective_strategy_params,
    _effective_exits,
    _effective_risk,
    _effective_execution,
)

if TYPE_CHECKING:
    from hypervector.paper.session import PaperSession


def session_identity_payload(session: PaperSession) -> dict[str, object]:
    """Build the public session_start identity from its meaning-named sections.

    Section order is the payload key order; keep it stable for consumers.
    """
    return {
        **_section_identity(session),
        **_section_execution_model(session),
        **_section_strategy_policy(session),
        **_section_risk_costs(session),
        **_section_runtime(session),
        **_section_portfolio_state(session),
        **_section_event_hold_state(session),
    }


def _section_identity(session: PaperSession) -> dict[str, object]:
    return {
        "feed_ts": "session_start",
        "run_id": session.run_id,
        "export_id": str(session.export_id),
        "strategy_name": session.strategy_name,
        "profile_id": session.hypervelocity_profile.profile_id
        if session.hypervelocity_profile is not None
        else None,
        "symbol": session.loadout.symbol,
        "timeframe": session.loadout.timeframe,
        "data_root": str(session.root.resolve()),
        "action": "session_start",
        "execution_model": session.hypervelocity_profile.shadow_execution_model
        if session.hypervelocity_profile is not None
        else "legacy_bar_through_v1",
        "execution_data_source": "hyperliquid_public_ws_l2_trades_active_asset_ctx"
        if session.hypervelocity_profile is not None
        else None,
        "execution_evidence_fresh": False,
        "execution_submit_latency_ms": session.hypervelocity_profile.execution_submit_latency_ms
        if session.hypervelocity_profile is not None
        else None,
        "execution_cancel_latency_ms": session.hypervelocity_profile.execution_cancel_latency_ms
        if session.hypervelocity_profile is not None
        else None,
    }


def _section_execution_model(session: PaperSession) -> dict[str, object]:
    return {
        "execution_update_latency_ms": session.hypervelocity_profile.execution_update_latency_ms
        if session.hypervelocity_profile is not None
        else None,
        "execution_queue_ahead_qty": None,
        "execution_requested_qty": None,
        "cumulative_filled_qty": None,
        "remaining_qty": None,
        "liquidity_side": None,
        "margin_model": "hyperliquid_isolated_v1"
        if session.hypervelocity_profile is not None
        else None,
        "liquidation_execution_model": LIQUIDATION_EXECUTION_MODEL
        if session.hypervelocity_profile is not None
        else None,
        "partial_liquidation_supported": PARTIAL_LIQUIDATION_SUPPORTED
        if session.hypervelocity_profile is not None
        else None,
        "backstop_liquidation_supported": session.hypervelocity_profile.backstop_liquidation_supported
        if session.hypervelocity_profile is not None
        else None,
        "conviction": session.conviction,
        "metalabel_mode": session.metalabel_mode,
        "metalabel_policy": _source_follow_metalabel_policy(
            session.hypervelocity_profile
        ),
        "metalabel_bundle_id": session.conviction_provider.bundle_id,
    }


def _section_strategy_policy(session: PaperSession) -> dict[str, object]:
    resume = session._shadow_resume
    return {
        "strategy_params": {
            "strategy": session.hypervelocity_profile.strategy_id
            if session.hypervelocity_profile
            else session.loadout.strategy_name,
            **_effective_strategy_params(
                session.loadout, profile=session.hypervelocity_profile
            ),
        },
        "position_policy": session.hypervelocity_profile.position_policy()
        if session.hypervelocity_profile
        else None,
        "regime_policy": session.hypervelocity_profile.regime_policy()
        if session.hypervelocity_profile
        else None,
        "peak_observer": session.hypervelocity_profile.peak_observer.telemetry()
        if session.hypervelocity_profile
        else None,
        "portfolio_spec": session._portfolio_spec,
        "portfolio_fingerprint": session._portfolio_fingerprint,
        "portfolio_profile_changed_from": resume.portfolio_profile_changed_from
        if resume is not None
        else None,
    }


def _section_risk_costs(session: PaperSession) -> dict[str, object]:
    return {
        "exits": _effective_exits(
            session.loadout, profile=session.hypervelocity_profile
        ),
        "risk": _effective_risk(session.loadout, profile=session.hypervelocity_profile),
        "execution": _effective_execution(
            session.loadout, profile=session.hypervelocity_profile
        ),
        "costs": session._effective_costs(),
    }


def _section_runtime(session: PaperSession) -> dict[str, object]:
    return {
        "runtime": {
            "lookback_days": session.lookback_days,
            "live_activated_at": session._live_activated_at.isoformat()
            if session._live_activated_at is not None
            else None,
            **(
                session.hypervelocity_profile.research_evidence()
                if isinstance(
                    session.hypervelocity_profile, SourceFollowHypervelocityProfile
                )
                else {}
            ),
        }
    }


def _section_portfolio_state(session: PaperSession) -> dict[str, object]:
    position = session.engine.position
    resume = session._shadow_resume
    return {
        "orderbook_archive": {
            "enabled": session.hypervelocity_profile.orderbook_archive_enabled,
            "depth_levels": session.hypervelocity_profile.orderbook_archive_depth_levels,
            "path_pattern": "cache/events/hyperliquid/<SYMBOL>/<UTC_DAY>/{l2.parquet,trades.parquet,asset_context.parquet,gaps.jsonl}",
        }
        if session.hypervelocity_profile is not None
        else {"enabled": False},
        "bars_processed": session.bars_processed,
        "execution_mode": session.execution_mode,
        "submitted": False,
        "network": NETWORK_MAINNET,
        "position_qty": float(position.qty),
        "position_avg_px": float(position.avg_px),
        "liquidation_price": session._current_liquidation_price(),
        "realized_pnl": float(position.realized_pnl),
        "unrealized_pnl": float(resume.unrealized_pnl) if resume is not None else 0.0,
        "equity": float(resume.equity) if resume is not None else float(session.equity),
        "init_cash": float(session.engine.initial_cash),
        "resumed_shadow_portfolio": resume is not None,
        "portfolio_state_asof": resume.state_asof if resume is not None else None,
    }


def _section_event_hold_state(session: PaperSession) -> dict[str, object]:
    return {
        "position_opened_at": session._event_shadow_bridge.controller.state.position_opened_at
        if session._event_shadow_bridge is not None
        else None,
        "maximum_hold_seconds": session._event_shadow_bridge.controller.state.maximum_hold_seconds
        if session._event_shadow_bridge is not None
        else None,
        "no_submit": True,
    }
