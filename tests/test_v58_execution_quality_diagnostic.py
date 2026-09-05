"""Current-run execution-quality diagnosis for the V58 research loop."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.v58_execution_quality_diagnostic import (
    build_v58_execution_quality_diagnostic,
)


def test_diagnoses_path_variance_without_hiding_stop_cost_tail() -> None:
    """Exact fills must separate entry quality from lifecycle concentration."""
    report = build_v58_execution_quality_diagnostic(_checkpoint())

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }
    assert report["sample"] == {
        "submitted_entries": 5,
        "entry_fills": 5,
        "all_fills": 9,
        "closed_lifecycles": 3,
        "open_lifecycles": 2,
        "rejected_submissions": 0,
        "late_submitted_entries": 0,
        "minimum_submission_headroom_ms": 16_842,
    }
    attribution = report["closed_lifecycle_attribution"]
    assert attribution["net_pnl_usd"] == pytest.approx(16.169133)
    assert attribution["net_pnl_excluding_largest_winner_usd"] == pytest.approx(-11.028)
    assert attribution["sides_observed"] == ["long"]
    assert attribution["stop_exit_slippage_bps"]["mean"] == pytest.approx(6.2098)
    assert attribution["stop_exit_slippage_bps"]["maximum"] == pytest.approx(9.1113)
    diagnosis = report["diagnosis"]
    assert diagnosis["entry_execution_degradation_supported"] is False
    assert diagnosis["stop_exit_cost_tail_observed"] is True
    assert diagnosis["strategy_breakage_supported"] is False
    assert diagnosis["live_change_supported"] is False
    assert diagnosis["primary_attribution"] == (
        "insufficient_sample_path_variance_with_stop_exit_cost_tail"
    )
    assert report["uncertainties_and_failure_modes"][1] == (
        "stop slippage has 2 observations and the two-bps comparison is a "
        "research proxy"
    )


def test_rejects_fill_count_that_disagrees_with_exact_rows() -> None:
    """A success-shaped aggregate cannot hide missing fill evidence."""
    checkpoint = deepcopy(_checkpoint())
    checkpoint["audit"]["execution"]["current_run_fills"] = 8

    with pytest.raises(ValueError, match="fill count"):
        build_v58_execution_quality_diagnostic(checkpoint)


def test_scopes_compatible_history_to_current_process_execution() -> None:
    """A restart must not contaminate current-process execution attribution."""
    checkpoint = deepcopy(_checkpoint())
    execution = checkpoint["audit"]["execution"]
    execution["fill_details"].append(
        _fill(
            "entry",
            100.0,
            origin_run_id="bidirectional-live-prior",
            strategy_id="eth",
            symbol="ETH",
            venue_timestamp_ms=50,
        )
    )
    execution["closed_trades"] = 4
    execution["net_pnl_usd"] = 116.169133
    checkpoint["audit"]["trade_reflections"]["trades"].append(
        _closed_lifecycle(
            index=4,
            pnl=100.0,
            source_run_id="bidirectional-live-prior",
            exit_timestamp_ms=50,
        )
    )
    eth_friction = execution["friction_parity"]["by_provider_symbol"]["eth|ETH"]
    eth_friction["observed_entry"]["fills"] = 4
    eth_friction["observed_entry"]["slippage_mean_minus_modeled_bps"] = 10.0

    report = build_v58_execution_quality_diagnostic(checkpoint)

    assert report["sample"]["all_fills"] == 9
    assert report["sample"]["closed_lifecycles"] == 3
    assert report["closed_lifecycle_attribution"]["net_pnl_usd"] == pytest.approx(
        16.169133
    )
    assert report["diagnosis"]["entry_execution_degradation_supported"] is False


def test_includes_prior_lifecycle_resolved_by_current_process() -> None:
    """A current-process close must count even when its entry predates restart."""
    checkpoint = deepcopy(_checkpoint())
    execution = checkpoint["audit"]["execution"]
    execution["fill_details"].append(
        _fill(
            "reduce_only_close",
            0.5,
            strategy_id="sp500",
            symbol="xyz:SP500",
            venue_timestamp_ms=900,
        )
    )
    execution["current_run_fills"] = 10
    execution["closed_trades"] = 4
    execution["net_pnl_usd"] = 18.169133
    checkpoint["audit"]["trade_reflections"]["trades"].append(
        _closed_lifecycle(
            index=4,
            pnl=2.0,
            source_run_id="bidirectional-live-prior",
            exit_timestamp_ms=900,
            symbol="xyz:SP500",
            side="short",
        )
    )

    report = build_v58_execution_quality_diagnostic(checkpoint)

    assert report["sample"]["all_fills"] == 10
    assert report["sample"]["closed_lifecycles"] == 4
    attribution = report["closed_lifecycle_attribution"]
    assert attribution["net_pnl_usd"] == pytest.approx(18.169133)
    assert attribution["sides_observed"] == ["long", "short"]


def test_all_loss_sample_does_not_invent_a_largest_winner() -> None:
    """Largest-winner sensitivity must remain literal when no winner exists."""
    checkpoint = deepcopy(_checkpoint())
    trades = checkpoint["audit"]["trade_reflections"]["trades"]
    for trade, pnl in zip(trades, (-1.0, -2.0, -3.0), strict=True):
        trade["net_pnl_usd"] = pnl
    checkpoint["audit"]["execution"]["net_pnl_usd"] = -6.0

    report = build_v58_execution_quality_diagnostic(checkpoint)

    attribution = report["closed_lifecycle_attribution"]
    assert attribution["largest_winner_usd"] is None
    assert attribution["net_pnl_excluding_largest_winner_usd"] == -6.0


def test_uncertainty_uses_singular_stop_observation() -> None:
    """One measured stop must not be described with plural grammar."""
    checkpoint = deepcopy(_checkpoint())
    checkpoint["audit"]["execution"]["fill_details"][-1]["operation"] = (
        "reduce_only_close"
    )

    report = build_v58_execution_quality_diagnostic(checkpoint)

    assert report["uncertainties_and_failure_modes"][1] == (
        "stop slippage has 1 observation and the two-bps comparison is a research proxy"
    )


def _checkpoint() -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-20T21:30:01+00:00",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_retuning": False,
            "performance_gate": False,
            "runtime_strategy_changed": False,
        },
        "lifecycle": {
            "state": "running_consistent",
            "backend_process_health": "healthy",
            "cohort_heartbeat_status": "running",
            "faulted_assets": [],
        },
        "audit": {
            "coverage": {"complete": True, "technical_gaps": []},
            "run": {
                "run_id": "bidirectional-live-v58",
                "profile_id": "multi_asset_v58",
                "profile_fingerprint": "a" * 64,
                "symbols": [
                    "BTC",
                    "ETH",
                    "SOL",
                    "HYPE",
                    "xyz:SP500",
                    "xyz:SPCX",
                    "xyz:SNDK",
                    "xyz:BRENTOIL",
                ],
            },
            "routing": {"entry_age_diagnostics": _entry_timing()},
            "execution": _execution(),
            "trade_reflections": {"trades": _closed_lifecycles()},
        },
    }


def _entry_timing() -> dict[str, object]:
    return {
        "eligible_evaluations": 9,
        "enter_actions": 5,
        "submitted_entries": 5,
        "stale_entries_withheld": 0,
        "submission_timestamp_observed": True,
        "entry_submission_enforcement_observed": True,
        "executed_late_entries_proven": False,
        "by_provider_symbol": {
            "eth|ETH": {
                "submitted_entries": 3,
                "submitted_entries_over_limit": 0,
                "minimum_submission_headroom_ms": 42_862,
            },
            "brent|xyz:BRENTOIL": {
                "submitted_entries": 1,
                "submitted_entries_over_limit": 0,
                "minimum_submission_headroom_ms": 17_741,
            },
            "sp500|xyz:SP500": {
                "submitted_entries": 1,
                "submitted_entries_over_limit": 0,
                "minimum_submission_headroom_ms": 16_842,
            },
        },
    }


def _execution() -> dict[str, object]:
    fills = [
        _fill("entry", -25.4026, venue_timestamp_ms=100),
        _fill(
            "entry",
            0.1092,
            strategy_id="brent",
            symbol="xyz:BRENTOIL",
            venue_timestamp_ms=200,
        ),
        _fill("reduce_only_close", -13.5959, venue_timestamp_ms=300),
        _fill("reduce_only_close", -13.5959, venue_timestamp_ms=300),
        _fill(
            "entry",
            -0.3900,
            strategy_id="sp500",
            symbol="xyz:SP500",
            venue_timestamp_ms=400,
        ),
        _fill("entry", 13.4560, venue_timestamp_ms=500),
        _fill("protective_stop", 3.3083, venue_timestamp_ms=600),
        _fill("entry", -13.6222, venue_timestamp_ms=700),
        _fill("protective_stop", 9.1113, venue_timestamp_ms=800),
    ]
    return {
        "current_run_fills": 9,
        "fill_details": fills,
        "closed_trades": 3,
        "open_lifecycles": 2,
        "net_pnl_usd": 16.169133,
        "current_run_submission_outcomes": {
            "outcomes": 11,
            "accepted": 11,
            "rejected": 0,
        },
        "friction_parity": _friction(),
        "by_strategy_side": {
            "eth|long": {
                "closed_trades": 3,
                "net_pnl_usd": 16.169133,
                "wins": 1,
                "losses": 2,
            }
        },
    }


def _fill(
    operation: str,
    slippage_bps: float,
    *,
    origin_run_id: str = "bidirectional-live-v58",
    strategy_id: str = "eth",
    symbol: str = "ETH",
    venue_timestamp_ms: int,
) -> dict[str, object]:
    return {
        "origin_run_id": origin_run_id,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "operation": operation,
        "venue_timestamp_ms": venue_timestamp_ms,
        "slippage_bps": slippage_bps,
        "acknowledgement_latency_ms": 1_200,
    }


def _friction() -> dict[str, object]:
    def row(
        fills: int,
        delta: float,
        modeled_slippage_bps: float = 2.0,
    ) -> dict[str, object]:
        return {
            "parity_state": "runtime_shape_aligned",
            "mismatches": [],
            "modeled_contract": {"entry_slippage_bps": modeled_slippage_bps},
            "observed_entry": {
                "fills": fills,
                "slippage_mean_minus_modeled_bps": delta,
            },
        }

    return {
        "summary": {
            "provider_symbols": 10,
            "provider_symbols_with_entry_fills": 3,
            "runtime_shape_aligned": 10,
            "contract_mismatch": 0,
            "runtime_contract_missing": 0,
            "unsupported_contract": 0,
        },
        "by_provider_symbol": {
            "eth|ETH": row(3, -10.5229),
            "brent|xyz:BRENTOIL": row(1, -0.0110, 0.1202),
            "sp500|xyz:SP500": row(1, -0.5102, 0.1202),
        },
    }


def _closed_lifecycles() -> list[dict[str, object]]:
    pnls = [27.197133, -5.30867, -5.71933]
    exit_times = [300, 600, 800]
    rows: list[dict[str, object]] = []
    for index, (pnl, exit_time) in enumerate(zip(pnls, exit_times, strict=True)):
        rows.append(_closed_lifecycle(index, pnl, exit_timestamp_ms=exit_time))
    return rows


def _closed_lifecycle(
    index: int,
    pnl: float,
    *,
    source_run_id: str = "bidirectional-live-v58",
    exit_timestamp_ms: int,
    symbol: str = "ETH",
    side: str = "long",
) -> dict[str, object]:
    return {
        "lifecycle_id": f"{symbol}:{index}",
        "symbol": symbol,
        "side": side,
        "net_pnl_usd": pnl,
        "source_run_id": source_run_id,
        "source_profile_fingerprint": "a" * 64,
        "exit": {"venue_timestamp_ms": exit_timestamp_ms},
    }
