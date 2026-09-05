"""Tests for the V62 all-executable-route stop diagnostic."""

from __future__ import annotations

from hypervector.research.route_stop_diagnostic import build_route_stop_diagnostic


def test_diagnostic_accounts_for_every_executable_route_and_missing_evidence() -> None:
    """Routes without trades remain explicit instead of disappearing from the report."""
    config = {
        "profile": "v61",
        "providers": [
            {
                "strategy_id": "eth_route",
                "execution": {
                    "stop_policy": "fixed_bps",
                    "stop_bps": 60.0,
                    "target_policy": "none",
                    "maximum_hold_seconds": 43_200,
                },
            },
            {
                "strategy_id": "btc_route",
                "execution": {
                    "stop_policy": "structural_clamped_bps",
                    "minimum_stop_bps": 20.0,
                    "maximum_stop_bps": 75.0,
                    "target_policy": "reward_risk",
                    "target_r_multiple": 3.0,
                },
            },
        ],
    }
    checkpoint = _checkpoint([_stopped_trade()])

    report = build_route_stop_diagnostic(config, checkpoint)

    assert report["summary"]["executable_routes"] == 2
    assert set(report["routes"]) == {"eth_route|ETH", "btc_route|BTC"}
    eth = report["routes"]["eth_route|ETH"]
    assert eth["closed_trades"] == 1
    assert eth["protective_stop_trades"] == 1
    assert eth["possible_control_whipsaws_15m"] == 1
    assert eth["evidence_status"] == "protective_stop_recovery_evidence_available"
    assert eth["configured_exit_contract"]["stop_bps"] == 60.0
    btc = report["routes"]["btc_route|BTC"]
    assert btc["closed_trades"] == 0
    assert btc["evidence_status"] == "insufficient_no_closed_trades"


def _checkpoint(trades: list[dict[str, object]]) -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-25T17:00:00Z",
        "configuration_generation": {
            "matches_runtime": True,
            "current_profile_fingerprint": "a" * 64,
        },
        "audit": {
            "run": {"executable_provider_symbols": ["eth_route|ETH", "btc_route|BTC"]},
            "trade_reflections": {"all_time_live": {"trades": trades}},
            "open_trade_reflections": {"trades": []},
        },
    }


def _stopped_trade() -> dict[str, object]:
    return {
        "lifecycle_id": "ETH:1",
        "source_run_id": "run-v61",
        "source_profile_fingerprint": "b" * 64,
        "strategy_id": "eth_route",
        "symbol": "ETH",
        "side": "long",
        "exit_reason": "protective_stop",
        "entry": {"price": 100.0, "size": 1.0},
        "exit": {"price": 99.4},
        "protective_stop": {"trigger_price": 99.4},
        "entry_followthrough_path": {
            "15": {
                "status": "resolved",
                "adverse_excursion_bps": 100.0,
                "favorable_excursion_bps": 80.0,
                "directional_close_return_bps": 10.0,
            }
        },
        "post_exit_path": {
            "15": {
                "status": "resolved",
                "favorable_excursion_bps": 70.0,
                "directional_close_return_bps": 10.0,
            }
        },
    }
