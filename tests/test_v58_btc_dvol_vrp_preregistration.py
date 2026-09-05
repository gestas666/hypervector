"""Frozen contract tests for the V58 BTC DVOL-VRP long research."""

from __future__ import annotations

import json
from pathlib import Path


_RECORD = Path(
    "docs/research-journal/"
    "v58-btc-dvol-vrp-continuation-long-preregistration-20260821-v1.json"
)


def _load_record() -> dict[str, object]:
    return json.loads(_RECORD.read_text(encoding="utf-8"))


def test_preregistration_freezes_identity_source_and_authority() -> None:
    record = _load_record()

    assert record["hypothesis_id"] == "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1"
    assert record["status"] == "preregistered_before_source_acquisition_or_outcomes"
    assert record["active_profile"] == (
        "multi_asset_growth_first_5000_eight_asset_incremental_v58"
    )
    source = record["source_contract"]
    assert isinstance(source, dict)
    assert source["endpoint"] == (
        "https://www.deribit.com/api/v2/public/get_volatility_index_data"
    )
    assert source["parameters"] == {
        "currency": "BTC",
        "resolution": "3600",
        "start_utc": "2025-07-28T00:00:00Z",
        "end_utc": "2026-07-28T00:00:00Z",
    }
    assert source["outcome_blind_coverage_rows_inclusive"] == 8761
    assert record["execution_authority"] == "none"
    assert record["automatic_promotion"] is False
    assert record["runtime_strategy_changed"] is False


def test_preregistration_freezes_features_entries_and_exits() -> None:
    record = _load_record()
    strategy = record["strategy_contract"]
    assert isinstance(strategy, dict)

    assert strategy["dvol_available_at"] == "timestamp_plus_1_hour"
    assert strategy["realized_volatility"] == {
        "return_cadence": "1h_completed_hyperliquid_btc",
        "lookback_hours": 720,
        "standard_deviation": "population_ddof_0",
        "annualization": "sqrt_24_times_365_times_100",
    }
    assert strategy["vrp"] == (
        "square_dvol_close_fraction_minus_square_realized_volatility_fraction"
    )
    assert strategy["thresholds"] == {
        "window_hours": 2160,
        "minimum_prior_observations": 720,
        "high_quantile": 0.75,
        "median_quantile": 0.50,
        "low_quantile": 0.25,
        "current_observation_excluded": True,
    }
    assert strategy["primary_entry"] == (
        "false_to_true_onset_of_high_vrp_and_close_above_shifted_prior_24h_high_"
        "and_close_above_ema168"
    )
    assert strategy["strategic_exit"] == (
        "completed_hour_close_below_ema24_or_vrp_below_prior_window_median"
    )
    assert strategy["protective_exit"] == {
        "stop_bps": 100.0,
        "target_bps": 250.0,
        "maximum_hold_hours": 72,
    }
    assert strategy["entry_execution"] == "next_one_minute_open_after_signal"


def test_preregistration_freezes_controls_economics_and_acceptance() -> None:
    record = _load_record()

    assert record["trial_arms"] == [
        "dvol_vrp_bullish_breakout_long",
        "price_only_bullish_breakout_long",
        "high_vrp_only_long",
        "low_vrp_bullish_breakout_long_placebo",
        "v58_liquidity_sweep_long_control",
        "no_action",
    ]
    assert record["partitions"] == {
        "development": ["2025-07-28T00:00:00Z", "2026-01-28T00:00:00Z"],
        "validation": ["2026-01-28T00:00:00Z", "2026-04-28T00:00:00Z"],
        "pseudo_holdout": ["2026-04-28T00:00:00Z", "2026-07-28T00:00:00Z"],
    }
    economics = record["economics"]
    assert isinstance(economics, dict)
    assert economics["scenarios"] == {
        "nominal": {"slippage_bps_per_market_side": 2.0, "extra_delay_minutes": 0},
        "stress": {"slippage_bps_per_market_side": 5.0, "extra_delay_minutes": 5},
        "delayed": {
            "slippage_bps_per_market_side": 10.0,
            "extra_delay_minutes": 60,
        },
    }
    assert economics["fees"] == {
        "taker_entry": 0.00045,
        "maker_target": 0.00015,
        "taker_market_exit": 0.00045,
        "liquidation": 0.00045,
        "funding": "exact_hyperliquid_hourly",
    }
    assert economics["sizing"] == {
        "initial_equity_usd": 5000.0,
        "margin_fraction": 0.10,
        "leverage": 10.0,
        "maximum_notional_usd": 5000.0,
        "venue_max_leverage": 40.0,
    }
    acceptance = record["acceptance"]
    assert isinstance(acceptance, dict)
    assert acceptance["minimum_primary_trades_per_oos_partition"] == 10
    assert acceptance["positive_net_all_oos_scenarios"] is True
    assert acceptance["profit_factor_above_one_all_oos_scenarios"] is True
    assert acceptance["positive_excluding_largest_all_oos_scenarios"] is True
    assert acceptance["zero_liquidations_and_no_insolvency"] is True
    assert acceptance["delayed_scenario_is_cost_headroom_lower_bound"] is True
    assert record["outcomes_inspected_before_preregistration"] is False
    assert record["candidate_signal_counts_inspected"] is False
    assert record["prior_price_partitions_opened"] is True
