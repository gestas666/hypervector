"""Contract tests for the report-only v30 forward-readiness prefix."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.research.v30_forward_readiness import (
    build_v30_forward_readiness,
)


PROFILE = Path("configs/multi_asset_bidirectional_lean_successor_canary_v30.toml")


def _scorecard(
    *, eligible: int, closed: int, net: float, net_ex_largest: float | None
) -> dict[str, object]:
    score: dict[str, object] = {
        "forward_evaluations": 100,
        "eligible_signals": eligible,
        "resolved_signal_horizons": 1 if eligible else 0,
        "forward_assessment": "observed" if eligible else "no_eligible_signal_evidence",
        "eligible_signal_horizons": {
            "5": {
                "independent": eligible,
                "resolved": eligible,
                "mean_directional_return_bps": -1.0,
                "positive_directional_rate": 0.4,
            }
        },
        "execution_performance": {
            "closed_trades": closed,
            "wins": closed,
            "losses": 0,
            "fees_usd": 0.1,
            "funding_usd": -0.01,
            "net_pnl_usd": net,
            "profit_factor": None,
        }
        if closed
        else None,
    }
    if closed:
        score["execution_performance_by_side"] = {"long": {"closed_trades": closed}}
        score["repeatability_evidence"] = {
            "net_pnl_excluding_largest_winner_usd": net_ex_largest
        }
    return score


def _checkpoint() -> dict[str, object]:
    routes = {
        "range_onset_bidirectional_v1|SOL": _scorecard(
            eligible=0, closed=0, net=0.0, net_ex_largest=None
        ),
        "range_onset_bidirectional_v1|ETH": _scorecard(
            eligible=0, closed=0, net=0.0, net_ex_largest=None
        ),
        "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX": _scorecard(
            eligible=2, closed=2, net=1.0, net_ex_largest=-0.5
        ),
    }
    return {
        "generated_at_utc": "2026-08-09T17:00:00+00:00",
        "mode": "live",
        "transition_drain": {"status": "inactive"},
        "lifecycle": {"asset_states": {"SOL": "OPEN"}},
        "audit": {
            "run": {
                "run_id": "run-one",
                "profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
                "profile_fingerprint": "source-fingerprint",
            },
            "strategy_scorecard": {"by_provider_symbol": routes},
            "execution": {"closed_trades": 3, "net_pnl_usd": 1.2},
            "portfolio": {"final_equity_usd": 501.2},
            "health": {
                "faults": 0,
                "assets": {
                    "SOL": {
                        "final_state": "OPEN",
                        "position_size_signed": 1.0,
                        "protected_if_open": True,
                        "stop_oid": 123,
                        "open_order_ids": [123],
                    }
                },
            },
        },
    }


def test_prefix_retains_inactive_candidate_when_route_coverage_is_missing() -> None:
    """Opened historical evidence cannot substitute for absent forward routes."""
    checkpoint = _checkpoint()
    eth = checkpoint["audit"]["strategy_scorecard"]["by_provider_symbol"][
        "range_onset_bidirectional_v1|ETH"
    ]
    eth.pop("repeatability_evidence", None)
    eth.pop("execution_performance_by_side", None)
    report = build_v30_forward_readiness(checkpoint, PROFILE)

    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert report["assessment"]["confidence"] == "low"
    assert report["assessment"]["routes_with_zero_eligible_signals"] == 2
    assert report["assessment"]["routes_with_zero_closed_trades"] == 2
    assert report["assessment"]["recommendation"] == (
        "retain_v30_inactive_collect_exact_forward_evidence"
    )
    assert report["live_state"]["open_positions"][0]["stop_oid"] == 123
    assert report["routes"][0]["repeatability_evidence_state"] == (
        "no_closed_execution"
    )


def test_prefix_rejects_missing_exact_route_scorecard() -> None:
    """A missing selected route cannot be silently replaced or defaulted."""
    checkpoint = _checkpoint()
    routes = checkpoint["audit"]["strategy_scorecard"]["by_provider_symbol"]
    routes.pop("range_onset_bidirectional_v1|ETH")

    with pytest.raises(ValueError, match="missing exact v30 route scorecards"):
        build_v30_forward_readiness(checkpoint, PROFILE)
