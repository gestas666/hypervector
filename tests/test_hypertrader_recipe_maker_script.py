"""Command contract for authentic Hypertrader B/C maker replay."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_hypertrader_maker_replay.py")
    spec = importlib.util.spec_from_file_location("hypertrader_maker_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Hypertrader maker replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_maker_replay_requires_authentic_development_and_fresh_contexts() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--data-root",
            "data",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--out",
            "maker.json",
        ]
    )
    contract = module._experiment_contract()

    assert args.data_root == Path("data")
    assert args.fresh_funding_context == [Path("fresh-funding.parquet")]
    assert contract["initial_equity"] == 10_000.0
    assert contract["allocation_fraction"] == 0.70
    assert contract["leverage"] == 40.0
    assert contract["gross_margin_target_pct"] == 8.0
    assert contract["one_position_per_symbol"] is True
    assert contract["signal_eligibility_seconds"] == 300.0
    assert contract["model_authority"] == "observe"
    assert contract["runtime_strategy_changed"] is False


def test_maker_replay_propagates_explicit_initial_equity() -> None:
    """Capacity replay must size orders from the declared account balance."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--initial-equity",
            "15000",
            "--out",
            "maker.json",
        ]
    )

    contract = module._experiment_contract(initial_equity=args.initial_equity)
    config = module._source_follow_config(
        60.0,
        "trade-through",
        initial_equity=args.initial_equity,
    )

    assert args.initial_equity == 15_000.0
    assert contract["initial_equity"] == 15_000.0
    assert config.initial_equity == 15_000.0


def test_maker_replay_rejects_nonpositive_initial_equity() -> None:
    """Invalid capital must fail at the command boundary."""
    module = _load_script()

    with pytest.raises(SystemExit):
        module._parser().parse_args(
            [
                "--labels",
                "labels.parquet",
                "--development-price-context",
                "dev-prices.parquet",
                "--development-funding-context",
                "dev-funding.parquet",
                "--fresh-price-context",
                "fresh-prices.parquet",
                "--fresh-funding-context",
                "fresh-funding.parquet",
                "--initial-equity",
                "0",
                "--out",
                "maker.json",
            ]
        )


def test_maker_replay_accepts_contiguous_context_parts() -> None:
    """Repeated context flags retain ordered immutable bundle segments."""
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "prices-one.parquet",
            "--development-price-context",
            "prices-two.parquet",
            "--development-funding-context",
            "funding-one.parquet",
            "--development-funding-context",
            "funding-two.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--out",
            "maker.json",
        ]
    )

    assert args.development_price_context == [
        Path("prices-one.parquet"),
        Path("prices-two.parquet"),
    ]
    assert args.development_funding_context == [
        Path("funding-one.parquet"),
        Path("funding-two.parquet"),
    ]

    with pytest.raises(ValueError, match="part counts must match"):
        module._load_context_parts(
            args.development_price_context,
            args.development_funding_context[:1],
        )


def test_event_outcomes_accepts_tuple_serialized_lifecycles() -> None:
    module = _load_script()
    signal_time = pd.Timestamp("2026-07-27T12:05:00Z")
    events = pd.DataFrame(
        [
            {
                "label_time_utc": signal_time - pd.Timedelta(minutes=5),
                "decision_time_utc": signal_time,
                "recipe": "fade_td_eu",
            }
        ]
    )
    replay_payload = {
        "lifecycles": (
            {"signal_time_utc": signal_time.isoformat(), "status": "closed"},
        )
    }

    outcomes = module._event_outcomes(events, replay_payload)

    assert outcomes[0]["admission"] == "submitted"
    assert outcomes[0]["lifecycle"]["status"] == "closed"
    assert json.loads(json.dumps(outcomes))[0]["decision_time_utc"] == (
        signal_time.isoformat()
    )


def test_margin_stop_grid_is_predeclared_and_report_only() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "margin-stop",
            "--out",
            "maker-grid.json",
        ]
    )

    configs = module._tail_candidate_configs()

    assert args.candidate_family == "margin-stop"
    assert tuple(configs) == (
        "no_stop_control",
        "stop_6pct_margin",
        "stop_10pct_margin",
        "stop_14pct_margin",
        "stop_18pct_margin",
    )
    assert [config.fixed_margin_stop_pct for config in configs.values()] == [
        None,
        6.0,
        10.0,
        14.0,
        18.0,
    ]
    assert all(config.fill_rule == "trade-through" for config in configs.values())
    assert all(config.entry_ttl_seconds == 300.0 for config in configs.values())
    assert (
        module._experiment_contract("margin-stop")["runtime_strategy_changed"] is False
    )


def test_source_peak_tier0_grid_is_exact_and_report_only() -> None:
    """The source constants are frozen before the final April holdout."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "source-follow-session-06-15-confidence-70-peak-tier0",
            "--out",
            "maker-grid.json",
        ]
    )

    configs = module._peak_candidate_configs(60.0, "trade-through")
    contract = module._experiment_contract(args.candidate_family)

    assert tuple(configs) == ("no_peak_control", "source_peak_tier0")
    assert configs["no_peak_control"].peak_protection_activation_margin_pct is None
    assert configs["source_peak_tier0"].peak_protection_activation_margin_pct == 6.0
    assert configs["source_peak_tier0"].peak_protection_lock_ratio == 0.55
    assert (
        configs["source_peak_tier0"].peak_protection_minimum_price_move_fraction
        == 0.0005
    )
    assert configs["source_peak_tier0"].peak_protection_update_cooldown_seconds == 60.0
    assert contract["selection_is_promotion"] is False
    assert contract["model_authority"] == "observe"
    assert contract["peak_protection_policy"] == "source tier0: +6% peak, lock 55%"


def test_source_peak_activation7_is_one_parameter_sensitivity() -> None:
    """Activation 7 changes one frozen field and remains report-only."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "source-follow-session-06-15-confidence-70-peak-activation7",
            "--out",
            "maker-grid.json",
        ]
    )

    configs = module._peak_candidate_configs(
        60.0,
        "trade-through",
        activation_margin_pct=7.0,
        candidate_name="source_peak_activation7",
    )
    contract = module._experiment_contract(args.candidate_family)

    assert tuple(configs) == ("no_peak_control", "source_peak_activation7")
    assert (
        configs["source_peak_activation7"].peak_protection_activation_margin_pct == 7.0
    )
    assert configs["source_peak_activation7"].peak_protection_lock_ratio == 0.55
    assert contract["peak_protection_policy"] == (
        "source sensitivity: +7% peak, lock 55%"
    )
    assert contract["runtime_strategy_changed"] is False
    assert contract["selection_is_promotion"] is False


def test_wide_margin_stop_grid_is_predeclared_and_report_only() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "source-follow-wide-margin-stop",
            "--out",
            "maker-grid.json",
        ]
    )

    configs = module._tail_candidate_configs(wide=True)

    assert args.candidate_family == "source-follow-wide-margin-stop"
    assert tuple(configs) == (
        "no_stop_control",
        "stop_25pct_margin",
        "stop_35pct_margin",
        "stop_45pct_margin",
    )
    assert [config.fixed_margin_stop_pct for config in configs.values()] == [
        None,
        25.0,
        35.0,
        45.0,
    ]
    contract = module._experiment_contract("source-follow-wide-margin-stop")
    assert contract["runtime_strategy_changed"] is False
    assert contract["stop_policy"] == "fixed margin grid: none, 25%, 35%, 45%"


def test_maker_replay_accepts_report_only_trend_aligned_variant() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "trend-aligned",
            "--out",
            "maker-aligned.json",
        ]
    )

    contract = module._experiment_contract("trend-aligned")

    assert args.candidate_family == "trend-aligned"
    assert contract["candidate_family"] == "trend-aligned"
    assert contract["stop_policy"] == "none"
    assert contract["runtime_strategy_changed"] is False


def test_all_day_opposite_exit_changes_only_exit_authority() -> None:
    module = _load_script()

    control = module._source_follow_config(60.0, "trade-through")
    candidate = module._source_follow_config(
        60.0,
        "trade-through",
        opposite_regime_exit=True,
    )

    differences = {
        name
        for name in control.__dataclass_fields__
        if getattr(control, name) != getattr(candidate, name)
    }
    assert differences == {"opposite_regime_exit"}
    assert candidate.opposite_regime_exit is True


def test_maker_replay_discloses_bounded_entry_eligibility() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "trend-aligned",
            "--entry-eligibility-seconds",
            "60",
            "--out",
            "maker-aligned-60s.json",
        ]
    )

    contract = module._experiment_contract(
        "trend-aligned",
        entry_eligibility_seconds=args.entry_eligibility_seconds,
    )

    assert args.entry_eligibility_seconds == 60.0
    assert contract["entry_ttl_seconds"] == 60.0
    assert contract["signal_eligibility_seconds"] == 60.0


def test_trend_aligned_entry_grid_predeclares_neighboring_windows() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "trend-aligned-ttl-grid",
            "--out",
            "maker-aligned-grid.json",
        ]
    )
    configs = module._entry_eligibility_candidate_configs()
    contract = module._experiment_contract(args.candidate_family)
    assert tuple(configs) == (
        "ttl_30s",
        "ttl_60s",
        "ttl_90s",
        "ttl_120s",
        "ttl_180s",
        "ttl_240s",
        "ttl_300s",
    )
    assert [config.entry_ttl_seconds for config in configs.values()] == [
        30.0,
        60.0,
        90.0,
        120.0,
        180.0,
        240.0,
        300.0,
    ]
    assert contract["entry_ttl_seconds"] == [
        30.0,
        60.0,
        90.0,
        120.0,
        180.0,
        240.0,
        300.0,
    ]
    assert contract["runtime_strategy_changed"] is False


def test_maker_replay_discloses_explicit_signal_range_candidate() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--candles",
            "development-candles.parquet",
            "--candles",
            "fresh-candles.parquet",
            "--maximum-signal-range-bps",
            "100",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "trend-aligned",
            "--entry-eligibility-seconds",
            "60",
            "--out",
            "maker-aligned-60s-range100.json",
        ]
    )

    contract = module._experiment_contract(
        args.candidate_family,
        entry_eligibility_seconds=args.entry_eligibility_seconds,
        maximum_signal_range_bps=args.maximum_signal_range_bps,
    )

    assert args.candles == [
        Path("development-candles.parquet"),
        Path("fresh-candles.parquet"),
    ]
    assert contract["maximum_signal_range_bps"] == 100.0
    assert contract["signal_range_policy"] == "completed_5m_high_low_range"
    assert contract["runtime_strategy_changed"] is False


def test_maker_replay_discloses_range_direction_candidate() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--candles",
            "candles.parquet",
            "--maximum-signal-range-bps",
            "100",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "source-range-direction",
            "--entry-eligibility-seconds",
            "60",
            "--out",
            "range-direction.json",
        ]
    )

    contract = module._experiment_contract(
        args.candidate_family,
        entry_eligibility_seconds=args.entry_eligibility_seconds,
        maximum_signal_range_bps=args.maximum_signal_range_bps,
    )

    assert contract["event_policy"] == "recipe_c_low_range_follow_high_range_fade"
    assert contract["signal_range_policy"] == (
        "completed_5m_high_low_range_direction_split"
    )
    assert contract["model_authority"] == "observe"
    assert contract["runtime_strategy_changed"] is False


def test_event_outcomes_marks_explicitly_filtered_events() -> None:
    module = _load_script()
    signal_time = pd.Timestamp("2026-07-27T12:05:00Z")
    events = pd.DataFrame(
        [
            {
                "label_time_utc": signal_time - pd.Timedelta(minutes=5),
                "decision_time_utc": signal_time,
                "entry_eligible": False,
                "entry_exclusion_reason": "signal_range",
            }
        ]
    )

    outcomes = module._event_outcomes(events, {"lifecycles": ()})

    assert outcomes[0]["admission"] == "filtered"
    assert outcomes[0]["entry_exclusion_reason"] == "signal_range"


def test_maker_replay_discloses_fill_assumption() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--fill-rule",
            "through",
            "--out",
            "maker-through.json",
        ]
    )

    contract = module._experiment_contract(fill_rule=args.fill_rule)

    assert args.fill_rule == "through"
    assert contract["fill_rule"] == "through"
    assert contract["entry"] == "post-only maker through"


def test_maker_replay_discloses_symmetric_trend_onset_contract() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--candles",
            "candles.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "symmetric-trend-aligned",
            "--entry-eligibility-seconds",
            "60",
            "--maximum-signal-range-bps",
            "100",
            "--fill-rule",
            "touch",
            "--out",
            "symmetric.json",
        ]
    )

    contract = module._experiment_contract(
        args.candidate_family,
        entry_eligibility_seconds=args.entry_eligibility_seconds,
        maximum_signal_range_bps=args.maximum_signal_range_bps,
        fill_rule=args.fill_rule,
    )

    assert contract["candidate_family"] == "symmetric-trend-aligned"
    assert contract["event_policy"] == (
        "source_b_asia_breakout_plus_eu_trend_up_down_onsets"
    )
    assert contract["signal_eligibility_seconds"] == 60.0
    assert contract["maximum_signal_range_bps"] == 100.0
    assert contract["fill_rule"] == "touch"
    assert contract["model_authority"] == "observe"
    assert contract["runtime_strategy_changed"] is False


def test_symmetric_events_are_extracted_before_range_annotation(
    tmp_path: Path,
) -> None:
    module = _load_script()
    label_index = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-27T06:55:00Z",
                "2026-07-27T07:00:00Z",
                "2026-07-27T07:05:00Z",
                "2026-07-27T07:10:00Z",
            ],
            utc=True,
        )
    )
    labels = pd.DataFrame(
        {
            "primary_code": ["RANGE", "TREND_UP", "RANGE", "TREND_DOWN"],
            "secondary_code": [None, None, None, None],
            "confidence": [0.5, 0.7, 0.5, 0.8],
        },
        index=label_index,
    )
    labels_path = tmp_path / "labels.parquet"
    labels.to_parquet(labels_path)
    candle_index = pd.date_range("2026-07-27T07:00:00Z", periods=15, freq="1min")
    candles = pd.DataFrame(
        {
            "timestamp": candle_index,
            "open": [100.0] * 15,
            "high": [100.2] * 15,
            "low": [99.8] * 15,
            "close": [100.0] * 15,
            "volume": [1.0] * 15,
            "source": ["hl"] * 15,
        }
    )
    candles_path = tmp_path / "candles.parquet"
    candles.to_parquet(candles_path)

    events = module._events(
        labels_path,
        [candles_path],
        100.0,
        "symmetric-trend-aligned",
    )

    assert events["recipe_id"].tolist() == ["follow_tu_eu", "follow_td_eu"]
    assert events["entry_eligible"].tolist() == [True, True]


def test_range_direction_family_routes_both_recipe_c_sides(tmp_path: Path) -> None:
    module = _load_script()
    label_index = pd.date_range("2026-07-27T07:00:00Z", periods=4, freq="5min")
    labels = pd.DataFrame(
        {
            "primary_code": ["RANGE", "TREND_DOWN", "RANGE", "TREND_DOWN"],
            "secondary_code": [None, None, None, None],
            "confidence": [0.5, 0.7, 0.5, 0.8],
        },
        index=label_index,
    )
    labels_path = tmp_path / "labels.parquet"
    labels.to_parquet(labels_path)
    candle_index = pd.date_range("2026-07-27T07:00:00Z", periods=20, freq="1min")
    candles = pd.DataFrame(
        {
            "timestamp": candle_index,
            "open": [100.0] * 20,
            "high": [100.0] * 20,
            "low": [100.0] * 20,
            "close": [100.0] * 20,
            "volume": [1.0] * 20,
            "source": ["hl"] * 20,
        }
    )
    candles.loc[5, ["high", "low"]] = [100.7, 99.7]
    candles.loc[15, ["high", "low"]] = [100.8, 99.7]
    candles_path = tmp_path / "candles.parquet"
    candles.to_parquet(candles_path)

    events = module._events(
        labels_path,
        [candles_path],
        100.0,
        "source-range-direction",
    )

    assert events["recipe_id"].tolist() == ["follow_td_eu", "fade_td_eu"]
    assert events["side"].tolist() == ["short", "long"]
    assert events["entry_eligible"].tolist() == [True, True]

    with pytest.raises(ValueError, match="requires an explicit range split"):
        module._events(
            labels_path,
            [],
            None,
            "source-range-direction",
        )


def test_maker_replay_discloses_four_hour_long_onset_contract() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--development-price-context",
            "dev-prices.parquet",
            "--development-funding-context",
            "dev-funding.parquet",
            "--fresh-price-context",
            "fresh-prices.parquet",
            "--fresh-funding-context",
            "fresh-funding.parquet",
            "--candidate-family",
            "symmetric-trend-aligned-long4h",
            "--out",
            "long4h.json",
        ]
    )

    contract = module._experiment_contract(args.candidate_family)

    assert contract["event_policy"] == (
        "source_b_asia_breakout_plus_eu_trend_up_down_onsets_long4h"
    )
    assert contract["model_authority"] == "observe"
    assert contract["runtime_strategy_changed"] is False


def test_four_hour_long_family_routes_to_bounded_hold(tmp_path: Path) -> None:
    module = _load_script()
    index = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-27T06:55:00Z",
                "2026-07-27T07:00:00Z",
                "2026-07-27T07:05:00Z",
                "2026-07-27T07:10:00Z",
            ],
            utc=True,
        )
    )
    labels = pd.DataFrame(
        {
            "primary_code": ["RANGE", "TREND_UP", "RANGE", "TREND_DOWN"],
            "secondary_code": [None, None, None, None],
            "confidence": [0.5, 0.7, 0.5, 0.8],
        },
        index=index,
    )
    path = tmp_path / "labels.parquet"
    labels.to_parquet(path)

    events = module._events(path, [], None, "symmetric-trend-aligned-long4h")

    assert events["recipe_id"].tolist() == ["follow_tu_eu", "follow_td_eu"]
    assert events["maximum_hold_seconds"].tolist() == [14_400.0, 86_400.0]
