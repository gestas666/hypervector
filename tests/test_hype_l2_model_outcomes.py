"""Exact venue-outcome joins for prospective HYPE L2 annotations."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.hype_l2_model_outcomes import (
    summarize_hype_l2_model_outcomes,
)


def test_open_annotation_uses_authoritative_marked_lifecycle() -> None:
    """An unresolved score must expose marked economics without calling it closed."""
    summary = summarize_hype_l2_model_outcomes([_observation()], _checkpoint())

    assert summary["counts"] == {
        "observations": 1,
        "scored": 1,
        "coverage_unavailable": 0,
        "awaiting_entry_fill": 0,
        "open": 1,
        "resolved": 0,
        "unreconciled": 0,
    }
    latest = summary["latest_outcome"]
    assert latest["status"] == "open"
    assert latest["entry_trade_id"] == 146114802882815
    assert latest["marked_net_pnl_usd"] == pytest.approx(-0.44622)
    assert latest["actual_net_return_bps"] is None
    assert summary["resolved_performance"]["profit_factor"] is None


def test_closed_annotation_resolves_exact_costed_return() -> None:
    """A close must join by entry timestamp and retain fees, funding, and net PnL."""
    checkpoint = _checkpoint()
    checkpoint["audit"]["execution"]["fill_details"].append(_close_fill())
    checkpoint["audit"]["execution"]["open_positions"] = []

    summary = summarize_hype_l2_model_outcomes([_observation()], checkpoint)

    latest = summary["latest_outcome"]
    assert latest["status"] == "resolved"
    assert latest["actual_gross_return_bps"] == pytest.approx(
        -0.445 / (55.764 * 1.34) * 10_000.0
    )
    assert latest["actual_net_return_bps"] == pytest.approx(
        -0.512 / (55.764 * 1.34) * 10_000.0
    )
    assert latest["fees_usd"] == pytest.approx(0.0645)
    assert latest["funding_usd"] == pytest.approx(0.001)
    assert latest["net_pnl_usd"] == pytest.approx(-0.512)
    assert summary["resolved_performance"]["losses"] == 1
    assert summary["resolved_performance"]["profit_factor"] == pytest.approx(0.0)


def test_resolved_annotations_report_band_side_and_gross_calibration() -> None:
    """Resolved scores must be diagnosable by band, side, and prediction error."""
    first = _observation()
    second = deepcopy(first)
    second.update(
        {
            "decision_time_ms": 1786000200000,
            "ledger_sequence": 77593,
            "side": "long",
            "score_band": "middle_60pct_annotation",
            "predicted_gross_return_bps": 10.0,
            "training_score_percentile": 0.5,
        }
    )
    checkpoint = _checkpoint()
    checkpoint["audit"]["execution"]["fill_details"] = [
        _entry_fill(),
        _close_fill(),
        _second_entry_fill(),
        _second_close_fill(),
    ]
    checkpoint["audit"]["execution"]["open_positions"] = []

    summary = summarize_hype_l2_model_outcomes([first, second], checkpoint)

    assert summary["resolved_by_score_band"]["top_20pct_annotation"]["losses"] == 1
    assert summary["resolved_by_score_band"]["middle_60pct_annotation"]["wins"] == 1
    assert summary["resolved_by_side"]["short"]["net_return_bps"] < 0.0
    assert summary["resolved_by_side"]["long"]["net_return_bps"] > 0.0
    calibration = summary["gross_calibration"]
    first_actual = -0.445 / (55.764 * 1.34) * 10_000.0
    second_actual = 0.75 / (50.0 * 1.5) * 10_000.0
    expected_actual = (first_actual + second_actual) / 2.0
    expected_predicted = (35.891778399577404 + 10.0) / 2.0
    assert calibration["resolved"] == 2
    assert calibration["mean_actual_gross_return_bps"] == pytest.approx(expected_actual)
    assert calibration["mean_predicted_gross_return_bps"] == pytest.approx(
        expected_predicted
    )
    assert calibration["mean_prediction_error_bps"] == pytest.approx(
        expected_actual - expected_predicted
    )
    assert calibration["directional_sign_agreement_rate"] == pytest.approx(0.5)


def test_missing_entry_is_pending_without_manufactured_zero() -> None:
    """Checkpoint latency must remain pending rather than become a zero-return trade."""
    checkpoint = _checkpoint()
    checkpoint["audit"]["execution"]["fill_details"] = []
    checkpoint["audit"]["execution"]["open_positions"] = []

    summary = summarize_hype_l2_model_outcomes([_observation()], checkpoint)

    latest = summary["latest_outcome"]
    assert latest["status"] == "awaiting_entry_fill"
    assert latest["entry_price"] is None
    assert latest["actual_net_return_bps"] is None


def test_prior_run_annotation_resolves_from_all_time_trade_reflection() -> None:
    """A restart must not erase a filled annotation's closed lifecycle outcome."""
    checkpoint = _checkpoint()
    checkpoint["audit"]["execution"]["fill_details"] = []
    checkpoint["audit"]["execution"]["open_positions"] = []
    checkpoint["audit"]["trade_reflections"] = {
        "all_time_live": {"trades": [_trade_reflection()]}
    }

    summary = summarize_hype_l2_model_outcomes([_observation()], checkpoint)

    latest = summary["latest_outcome"]
    assert latest["status"] == "resolved"
    assert latest["entry_trade_id"] is None
    assert latest["entry_timestamp_ms"] == 1785999912013
    assert latest["exit_timestamp_ms"] == 1786028722388
    assert latest["actual_gross_return_bps"] == pytest.approx(
        (55.764 - 55.84) / 55.764 * 10_000.0
    )
    assert latest["actual_net_return_bps"] == pytest.approx(
        -0.159634 / (55.764 * 1.34) * 10_000.0
    )
    assert latest["fees_usd"] == pytest.approx(0.064604)
    assert latest["funding_usd"] == pytest.approx(0.00681)
    assert summary["counts"]["resolved"] == 1
    assert summary["counts"]["awaiting_entry_fill"] == 0


def test_execution_capable_annotation_is_rejected() -> None:
    """The outcome join must fail if an annotation claims trading authority."""
    observation = deepcopy(_observation())
    observation["execution_authority"] = "hyperliquid_mainnet"

    with pytest.raises(ValueError, match="report-only contract"):
        summarize_hype_l2_model_outcomes([observation], _checkpoint())


def _observation() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_l2_ridge_prospective_observe_v1",
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
        "run_id": "bidirectional-live-1785976389611",
        "ledger_sequence": 77592,
        "decision_time_ms": 1785999900000,
        "decision_observed_at_utc": "2026-08-06T07:05:10.858434+00:00",
        "scored_at_utc": "2026-08-06T07:05:14.819163+00:00",
        "side": "short",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "bundle_sha256": "5" * 64,
        "status": "scored",
        "predicted_gross_return_bps": 35.891778399577404,
        "training_score_percentile": 0.8879492600422833,
        "score_band": "top_20pct_annotation",
        "coverage": {"books": 60},
    }


def _checkpoint() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-06T08:49:39+00:00",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "audit": {
            "execution": {
                "fill_details": [_entry_fill()],
                "open_positions": [
                    {
                        "symbol": "HYPE",
                        "side": "short",
                        "status": "provisional_open",
                        "entry_price": 55.764,
                        "mark_price": 56.097,
                        "active_lifecycle_marked_net_pnl_usd": -0.44622,
                        "fees_usd": 0.03228,
                        "funding_usd": 0.000937,
                    }
                ],
            }
        },
    }


def _entry_fill() -> dict[str, object]:
    return {
        "symbol": "HYPE",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "origin_run_id": "bidirectional-live-1785976389611",
        "trade_id": 146114802882815,
        "venue_timestamp_ms": 1785999912013,
        "price": 55.764,
        "size": 1.34,
        "direction": "Open Short",
        "fee_usd": 0.03228,
    }


def _close_fill() -> dict[str, object]:
    return {
        "symbol": "HYPE",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "origin_run_id": "bidirectional-live-1785976389611",
        "trade_id": 146114802882999,
        "venue_timestamp_ms": 1786007100000,
        "price": 56.0975,
        "size": 1.34,
        "direction": "Close Short",
        "fee_usd": 0.03222,
        "closed_pnl_usd": -0.445,
        "entry_price": 55.764,
        "entry_venue_timestamp_ms": 1785999912013,
        "lifecycle_fees_usd": 0.0645,
        "lifecycle_funding_usd": 0.001,
        "net_pnl_usd": -0.512,
        "holding_time_ms": 7_187_987,
        "exit_reason": "maximum_hold_seconds",
    }


def _second_entry_fill() -> dict[str, object]:
    return {
        "symbol": "HYPE",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "origin_run_id": "bidirectional-live-1785976389611",
        "trade_id": 146114802882900,
        "venue_timestamp_ms": 1786000210000,
        "price": 50.0,
        "size": 1.5,
        "direction": "Open Long",
        "fee_usd": 0.03,
    }


def _second_close_fill() -> dict[str, object]:
    return {
        "symbol": "HYPE",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "origin_run_id": "bidirectional-live-1785976389611",
        "trade_id": 146114802883000,
        "venue_timestamp_ms": 1786003800000,
        "price": 50.5,
        "size": 1.5,
        "direction": "Close Long",
        "fee_usd": 0.03,
        "closed_pnl_usd": 0.75,
        "entry_price": 50.0,
        "entry_venue_timestamp_ms": 1786000210000,
        "lifecycle_fees_usd": 0.06,
        "lifecycle_funding_usd": -0.01,
        "net_pnl_usd": 0.7,
        "holding_time_ms": 3_590_000,
        "exit_reason": "opposite_intent",
    }


def _trade_reflection() -> dict[str, object]:
    return {
        "symbol": "HYPE",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "entry_strategy_id": "hype_breakout_onset_bidirectional_v1",
        "source_run_id": "bidirectional-live-1785976389611",
        "side": "short",
        "entry_oid": 511264150124,
        "entry": {
            "price": 55.764,
            "size": 1.34,
            "venue_timestamp_ms": 1785999912013,
        },
        "exit_oid": 511548607201,
        "exit": {
            "price": 55.84,
            "size": 1.34,
            "venue_timestamp_ms": 1786028722388,
        },
        "exit_reason": "maximum_hold_seconds",
        "holding_time_ms": 28_810_375,
        "fees_usd": 0.064604,
        "funding_usd": 0.00681,
        "net_pnl_usd": -0.159634,
    }
