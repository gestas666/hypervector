"""Hermetic evidence fixtures for the v39-to-v45 report tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable


JsonMap = dict[str, object]


def _performance(closed: int = 2, net: float = 1.25) -> JsonMap:
    """Return one internally consistent performance record."""
    return {
        "closed_trades": closed,
        "wins": closed,
        "losses": 0,
        "win_rate_pct": 100.0,
        "net_pnl_usd": net,
        "profit_factor": None,
        "fees_usd": 0.10,
        "funding_usd": 0.01,
        "net_pnl_excluding_largest_winner_usd": 0.50,
        "maximum_closed_sequence_drawdown_usd": 0.0,
    }


def _checkpoint() -> JsonMap:
    """Return the minimal reconciled checkpoint consumed by the report."""
    performance = _performance()
    return {
        "generated_at_utc": "2026-08-12T12:00:00+00:00",
        "audit": {
            "trade_reflections": {
                "performance": {
                    "current_run": {"total": performance},
                    "all_time_live": {
                        "total": performance,
                        "by_provider_symbol": {
                            "hulk_expansion_short_robust_v3|BTC": performance
                        },
                    },
                }
            },
            "portfolio_archive": {"coverage": {"closed_orders": 2, "complete": True}},
            "open_trade_reflections": {"open_lifecycles": 0, "trades": []},
        },
    }


def _route_review() -> JsonMap:
    """Return route evidence matching the checkpoint fixture."""
    return {
        "summary": {
            "current_run_closed_trades": 2,
            "current_run_net_pnl_usd": 1.25,
        },
        "routes": {
            "hulk_expansion_short_robust_v3|BTC": {
                "current_run": {
                    "evaluations": 12,
                    "eligible_evaluations": 2,
                    "closed": {"closed_trades": 2, "net_pnl_usd": 1.25},
                },
                "evidence_state": "resolved",
            }
        },
    }


def _regime() -> JsonMap:
    """Return the four report horizons with deterministic state metrics."""
    state = {"directional_accuracy_pct": 55.0, "observations": 20}
    samples = {
        sample: {regime: state for regime in ("TREND_UP", "TREND_DOWN")}
        for sample in ("pooled", "episode_onsets")
    }
    return {
        "horizons": {
            horizon: {"state_fields": {"primary_regime": samples}}
            for horizon in ("5m", "15m", "30m", "60m")
        }
    }


def _stress_route(strategy: str, sides: list[str]) -> JsonMap:
    """Return one route row used by the v45 stress panels."""
    return {
        "strategy_id": strategy,
        "sides": sides,
        "margin_fraction": 0.10,
        "planned_notional_usd": 2_500.0,
        "stop_bps": 80.0,
        "target_bps": None,
        "stacked_p99_stop_loss_usd": 25.0,
    }


def _stress() -> JsonMap:
    """Return a deterministic three-slot $5,000 stress scenario."""
    strategies = {
        "BTC": ("hulk_expansion_short_robust_v3", ["short"]),
        "HYPE": (
            "hype_breakout_compression_pullback_bidirectional_v1",
            ["long", "short"],
        ),
        "xyz:SP500": (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
            ["long", "short"],
        ),
    }
    slots = {
        asset: {
            "routes": [_stress_route(strategy, sides)],
            "stacked_p99_slot_loss_usd": 25.0,
        }
        for asset, (strategy, sides) in strategies.items()
    }
    return {
        "scenarios": [
            {
                "account_value_usd": 5_000.0,
                "asset_slots": slots,
                "stacked_p99_stop_wave_loss_usd": 75.0,
                "stacked_p99_stop_wave_loss_pct_equity": 1.5,
            }
        ]
    }


def report_inputs() -> dict[str, JsonMap]:
    """Return all source documents required by the report builder."""
    return {
        "checkpoint.json": _checkpoint(),
        "route_review.json": _route_review(),
        "regime.json": _regime(),
        "v45_risk.json": {},
        "v45_stress.json": _stress(),
        "variable_sizing.json": {
            "evaluations": 286,
            "eligible_candidates": 0,
            "selected_tier_policy": "withheld_pending_forward_outcomes",
            "tier_authority": "counterfactual_only",
            "execution_authority": "none",
        },
    }


def fixture_paths(root: Path, path_factory: Callable[..., object]) -> object:
    """Build a report-path instance rooted at deterministic fixture names."""
    fixture_root = root / "tests" / "fixtures" / "v39_v45_growth_report"
    return path_factory(
        checkpoint=fixture_root / "checkpoint.json",
        route_review=fixture_root / "route_review.json",
        regime=fixture_root / "regime.json",
        v45_risk=fixture_root / "v45_risk.json",
        v45_stress=fixture_root / "v45_stress.json",
        variable_sizing=fixture_root / "variable_sizing.json",
    )
