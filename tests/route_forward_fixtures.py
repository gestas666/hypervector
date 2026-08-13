"""Frozen report-only route-forward checkpoint fixtures."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.route_forward_spec import CandidateRouteForwardSpec

_SOURCE = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")


def frozen_source_checkpoint(
    spec: CandidateRouteForwardSpec,
) -> dict[str, object]:
    """Return a deterministic exact-v25 checkpoint for one tracker contract."""
    source = load_multi_asset_live_config(_SOURCE, mode="observe")
    executable = _route_strings(source.executable_provider_symbols)
    scores = {route: _score(index) for index, route in enumerate(spec.tracked_routes)}
    return {
        "generated_at_utc": "2026-08-09T19:00:00+00:00",
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "transition_drain": {"status": "inactive"},
        "audit": {
            "run": {
                "run_id": "frozen-v25-source-run",
                "profile_id": source.profile_id,
                "profile_fingerprint": source.profile_fingerprint,
                "executable_provider_symbols": executable,
                "observe_only_provider_symbols": [],
            },
            "strategy_scorecard": {"by_provider_symbol": scores},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "portfolio": {"final_equity_usd": 500.0},
            "health": {"faults": 0, "assets": {}},
        },
    }


def _score(index: int) -> dict[str, object]:
    return {
        "forward_evaluations": 100 + index,
        "eligible_signals": 0,
        "resolved_signal_horizons": 0,
        "forward_assessment": "descriptive_no_resolved_signal",
        "eligible_signal_horizons": {},
    }


def _route_strings(routes: object) -> list[str]:
    return sorted(f"{provider}|{symbol}" for provider, symbol in routes)
