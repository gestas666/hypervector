"""Tests for v52's exact common-window report-only portfolio replay."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.hype_breakout_exit_models import HypeExitTrade
from hypervector.research.v52_common_window_portfolio import (
    HULK_ROUTE,
    HYPE_ROUTE,
    SWEEP_ROUTE,
    build_v52_common_window_portfolio,
)


def _hulk_payload() -> dict[str, object]:
    """Return one exact 3R forward Hulk lifecycle."""
    return {
        "execution_authority": "none",
        "report_only": True,
        "profile": {"name": HULK_ROUTE[0]},
        "replay_parameters": {
            "target_r_multiple": 3.0,
            "minimum_stop_bps": 20.0,
            "maximum_stop_bps": 75.0,
            "maximum_hold_bars": 48,
            "entry_fee_rate": 0.00045,
            "entry_slippage_bps": 2.0,
        },
        "replay": {
            "trades": [
                {
                    "symbol": "BTC",
                    "direction": "short",
                    "entry_time_utc": "2026-08-01T16:30:00+00:00",
                    "exit_time_utc": "2026-08-01T18:30:00+00:00",
                    "entry_price": 100.0,
                    "initial_quantity": 10.0,
                    "net_pnl_usd": 20.0,
                    "exit_reason": "target_2r",
                }
            ]
        },
    }


def _sweep_payload() -> dict[str, object]:
    """Return one exact 60/60 forward sweep lifecycle path."""
    return {
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "contract": {"stop_bps": 60.0, "maximum_mark_gap_ms": 120_000},
        "selection": {
            "target_bps": 60.0,
            "maximum_entry_delay_seconds": 30,
            "forward_path_resolved": True,
            "forward_sample_count": 1,
        },
        "grid": [
            {
                "partition": "forward",
                "entry_delay_seconds": 30,
                "target_bps": 60.0,
                "sample_count": 1,
                "wins": 1,
                "losses": 0,
                "timeouts": 0,
                "mean_net_bps": 46.0,
            }
        ],
        "path_observations": [
            {
                "partition": "forward",
                "signal_time_utc": "2026-08-06T14:00:00+00:00",
                "entry_delay_seconds": 30,
                "entry_time_ms": 1_786_024_830_000,
                "entry_ask": 64_401.0,
                "stop_time_ms": None,
                "target_times_ms": {"60.0": 1_786_027_384_000},
                "maximum_mark_gap_by_target_ms": {"60.0": 61_138},
            }
        ],
    }


def _hype_trade() -> HypeExitTrade:
    """Return one exact aligned-only later-window HYPE lifecycle."""
    return HypeExitTrade(
        side="long",
        signal_time_utc="2026-08-04T07:29:00+00:00",
        entry_time_utc="2026-08-04T07:30:00+00:00",
        exit_time_utc="2026-08-04T15:30:00+00:00",
        entry_price=54.66,
        exit_price=55.18,
        stop_price=54.22,
        gross_return_bps=95.0,
        fee_bps=9.0,
        funding_bps=-1.0,
        net_return_bps=85.0,
        hold_minutes=480,
        maximum_favorable_excursion_bps=205.0,
        maximum_adverse_excursion_bps=35.0,
        exit_reason="maximum_hold",
    )


def test_common_window_replays_exact_routes_and_stress_cost() -> None:
    """Three nonoverlapping exact routes must reconcile on one $5K account."""
    report = build_v52_common_window_portfolio(
        _hulk_payload(),
        _sweep_payload(),
        (_hype_trade(),),
    )

    nominal = report["windows"]["opened_common"]["nominal"]["v52_full"]
    stress = report["windows"]["opened_common"]["stress"]["v52_full"]
    assert nominal["completed_trades"] == 3
    assert nominal["maximum_concurrent_positions"] == 1
    assert nominal["net_pnl_usd"] == pytest.approx(165.5)
    assert stress["net_pnl_usd"] == pytest.approx(155.0)
    assert nominal["coverage"]["missing_routes"] == []
    assert report["v52_scope_coverage"] == {
        "configured_scopes": 4,
        "observed_scopes": 3,
        "missing_scopes": [f"{HYPE_ROUTE[0]}|HYPE|short"],
        "all_configured_scopes_observed": False,
    }
    assert report["observed_cadence"]["entries_per_week"] == pytest.approx(1.8327272727)
    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False


def test_common_window_priority_matches_live_higher_number_precedence() -> None:
    """A simultaneous BTC conflict must retain Hulk priority over sweep."""
    sweep = _sweep_payload()
    path = sweep["path_observations"][0]
    path["entry_time_ms"] = 1_785_601_800_000
    path["target_times_ms"]["60.0"] = 1_785_609_000_000

    report = build_v52_common_window_portfolio(
        _hulk_payload(),
        sweep,
        (_hype_trade(),),
    )

    full = report["windows"]["opened_common"]["nominal"]["v52_full"]
    assert [row["strategy_id"] for row in full["accepted"]] == [
        HULK_ROUTE[0],
        HYPE_ROUTE[0],
    ]
    assert [(row["strategy_id"], row["reason"]) for row in full["rejected"]] == [
        (SWEEP_ROUTE[0], "symbol_occupied")
    ]


def test_common_window_rejects_a_non_v52_sweep_contract() -> None:
    """The older 26.67-bps sweep replay must not masquerade as v52 evidence."""
    sweep = deepcopy(_sweep_payload())
    sweep["selection"]["target_bps"] = 26.6666666667

    with pytest.raises(ValueError, match="60 bps"):
        build_v52_common_window_portfolio(
            _hulk_payload(),
            sweep,
            (_hype_trade(),),
        )
