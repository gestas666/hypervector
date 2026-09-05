"""Fixed-entry sensitivity tests for the mature HYPE profit floor."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.cohort_profit_lock_policy import ProfitLockPolicy
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_mature_profit_floor_sensitivity import (
    build_fixed_entry_profit_floor_period,
    build_hype_mature_profit_floor_report,
    combine_fixed_entry_profit_floor_periods,
)


def _market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0, 100.5, 100.4, 99.5],
            "high": [101.1, 100.6, 100.5, 99.7],
            "low": [99.9, 100.2, 100.3, 99.4],
            "close": [101.0, 100.4, 100.4, 99.6],
            "funding_rate": [0.0, -0.0001, 0.0, 0.0],
        },
        index=index,
    )


def _trade(*, net_bps: float = -50.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "side": "long",
                "entry_time_utc": "2026-01-01T00:00:00+00:00",
                "exit_time_utc": "2026-01-01T00:03:00+00:00",
                "entry_price": 100.0,
                "net_return_bps": net_bps,
                "exit_reason": "maximum_hold",
            }
        ]
    )


def _quiet_market() -> pd.DataFrame:
    market = _market()
    market.loc[:, "high"] = [100.5, 100.6, 100.5, 99.7]
    market.loc[:, "close"] = [100.4, 100.4, 100.4, 99.6]
    return market


def _policy() -> ProfitLockPolicy:
    return ProfitLockPolicy("a100_floor25_only", 100.0, 25.0, 10_000.0)


def test_mature_floor_uses_next_bar_and_exact_costs() -> None:
    report = build_fixed_entry_profit_floor_period(
        _market(),
        _trade(),
        policy=_policy(),
        config=HypeExitReplayConfig(),
        fold_count=1,
    )

    exit_price = 100.25 * (1.0 - 2.0 / 10_000.0)
    gross_bps = (exit_price / 100.0 - 1.0) * 10_000.0
    fee_bps = 4.5 * (1.0 + exit_price / 100.0)
    funding_bps = 1.005
    expected = gross_bps - fee_bps + funding_bps
    outcome = report["outcomes"][0]

    assert outcome["trigger_timestamp_utc"] == "2026-01-01T00:01:00+00:00"
    assert outcome["estimated_net_return_bps"] == pytest.approx(expected)
    assert report["challenger"]["net_return_bps"] == pytest.approx(expected)
    assert report["native"]["triggered_lifecycles"] == 0
    assert report["challenger"]["triggered_lifecycles"] == 1
    assert report["challenger_minus_native_net_bps"] == pytest.approx(expected + 50.0)


def test_untriggered_floor_preserves_native_exit() -> None:
    report = build_fixed_entry_profit_floor_period(
        _quiet_market(),
        _trade(net_bps=12.5),
        policy=_policy(),
        config=HypeExitReplayConfig(),
        fold_count=1,
    )

    assert report["outcomes"][0]["status"] == "not_triggered"
    assert report["challenger"]["net_return_bps"] == 12.5
    assert report["challenger_minus_native_net_bps"] == 0.0


def test_missing_lifecycle_minute_fails_closed() -> None:
    with pytest.raises(ValueError, match="continuous completed one-minute path"):
        build_fixed_entry_profit_floor_period(
            _market().drop(pd.Timestamp("2026-01-01T00:01:00Z")),
            _trade(),
            policy=_policy(),
            config=HypeExitReplayConfig(),
            fold_count=1,
        )


def test_combined_period_recomputes_robustness_from_all_outcomes() -> None:
    first = build_fixed_entry_profit_floor_period(
        _market(),
        _trade(),
        policy=_policy(),
        config=HypeExitReplayConfig(),
        fold_count=1,
    )
    second = build_fixed_entry_profit_floor_period(
        _market(),
        _trade(net_bps=20.0),
        policy=_policy(),
        config=HypeExitReplayConfig(),
        fold_count=1,
    )

    combined = combine_fixed_entry_profit_floor_periods((first, second))

    assert combined["native"]["trades"] == 2
    assert combined["native"]["net_return_bps"] == -30.0
    assert combined["native"]["without_largest_winner_net_bps"] == -50.0


def test_report_keeps_confirmation_separate_and_grants_no_authority() -> None:
    report = build_hype_mature_profit_floor_report(
        _market(),
        _trade(),
        ((_quiet_market(), _trade(net_bps=20.0)),),
        policy=_policy(),
        config=HypeExitReplayConfig(),
        development_fold_count=1,
    )

    assert report["mode"] == "hype_mature_profit_floor_fixed_entry_sensitivity_v1"
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False
    assert report["development"]["native"]["net_return_bps"] == -50.0
    assert report["later_confirmation"]["native"]["net_return_bps"] == 20.0
    assert report["disposition"] == "defer_until_independent_trigger_evidence"
