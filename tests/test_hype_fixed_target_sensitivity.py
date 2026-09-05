"""Fixed-entry HYPE take-profit sensitivity tests."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig
from hypervector.research.hype_fixed_target_sensitivity import (
    TARGET_GRID_BPS,
    _select_development,
    build_fixed_target_report,
    entry_identity,
    evaluate_fixed_target_period,
)


def _market(*, target_on_exit_bar: bool = False) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    highs = [100.5, 100.7, 100.55, 100.4, 100.3]
    if target_on_exit_bar:
        highs = [100.5, 100.7, 100.55, 100.4, 100.3]
    return pd.DataFrame(
        {
            "open": [100.0, 100.2, 100.3, 99.7, 99.6],
            "high": highs,
            "low": [99.8, 99.7, 99.3, 99.5, 99.4],
            "close": [100.2, 100.3, 99.5, 99.6, 99.5],
            "funding_rate": [0.0, -0.0001, 0.0, 0.0, 0.0],
        },
        index=index,
    )


def _trade(
    *,
    side: str = "long",
    exit_time: str = "2026-01-01T00:03:00+00:00",
    native_net_bps: float = -50.0,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cohort": "aligned_only",
                "side": side,
                "entry_time_utc": "2026-01-01T00:00:00+00:00",
                "exit_time_utc": exit_time,
                "entry_price": 100.0,
                "net_return_bps": native_net_bps,
                "exit_reason": "maximum_hold",
            }
        ]
    )


def _execution() -> HypeExitReplayConfig:
    return HypeExitReplayConfig(
        stop_bps=80.0,
        maximum_hold_minutes=480,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
        exit_on_opposite_signal=True,
    )


def _period(
    market: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    target_bps: float = 60.0,
    slippage_bps: float = 2.0,
) -> dict[str, object]:
    return evaluate_fixed_target_period(
        market,
        trades,
        target_bps=target_bps,
        config=_execution(),
        fold_count=1,
        target_exit_slippage_bps=slippage_bps,
    )


def test_long_target_uses_first_completed_bar_and_exact_costs() -> None:
    report = _period(_market(), _trade())
    outcome = report["outcomes"][0]
    exit_price = 100.6 * (1.0 - 2.0 / 10_000.0)
    gross = (exit_price / 100.0 - 1.0) * 10_000.0
    fees = 4.5 * (1.0 + exit_price / 100.0)
    expected = gross - fees + 1.002

    assert outcome["status"] == "target_triggered"
    assert outcome["target_timestamp_utc"] == "2026-01-01T00:01:00+00:00"
    assert outcome["target_reference_price"] == pytest.approx(100.6)
    assert outcome["challenger_net_return_bps"] == pytest.approx(expected)
    assert report["challenger"]["triggered_lifecycles"] == 1
    assert report["entry_identity_sha256"] == entry_identity(_trade())


def test_short_target_uses_directional_low() -> None:
    report = _period(_market(), _trade(side="short"))
    outcome = report["outcomes"][0]

    assert outcome["status"] == "target_triggered"
    assert outcome["target_timestamp_utc"] == "2026-01-01T00:02:00+00:00"
    assert outcome["target_reference_price"] == pytest.approx(99.4)


def test_native_exit_wins_when_target_is_only_on_exit_bar() -> None:
    report = _period(
        _market(target_on_exit_bar=True),
        _trade(exit_time="2026-01-01T00:01:00+00:00"),
    )

    assert report["outcomes"][0]["status"] == "native_exit_preserved"
    assert report["challenger"]["net_return_bps"] == -50.0


def test_target_exit_tail_slippage_is_conservative() -> None:
    nominal = _period(_market(), _trade(), slippage_bps=2.0)
    tail = _period(_market(), _trade(), slippage_bps=5.0)

    assert (
        tail["challenger"]["net_return_bps"] < nominal["challenger"]["net_return_bps"]
    )
    assert tail["native"]["net_return_bps"] == nominal["native"]["net_return_bps"]


def test_missing_lifecycle_minute_fails_closed() -> None:
    market = _market().drop(pd.Timestamp("2026-01-01T00:01:00Z"))

    with pytest.raises(ValueError, match="continuous completed one-minute path"):
        _period(market, _trade())


@pytest.mark.parametrize("target", [0.0, -1.0, float("nan")])
def test_invalid_target_fails_closed(target: float) -> None:
    with pytest.raises(ValueError, match="target_bps"):
        _period(_market(), _trade(), target_bps=target)


def test_duplicate_entry_identity_fails_closed() -> None:
    trades = pd.concat([_trade(), _trade()], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate entry identity"):
        _period(_market(), trades)


def test_confirmation_cannot_change_development_selection() -> None:
    quiet = _market().assign(high=100.2, low=99.8)
    baseline = _report((quiet, _trade(native_net_bps=10.0)))
    changed = _report((_market(), _trade(native_net_bps=-500.0)))

    assert baseline["selection"] == changed["selection"]
    assert baseline["later_confirmation"] != changed["later_confirmation"]


def test_report_retains_grid_and_grants_no_authority() -> None:
    report = _report((_market(), _trade(native_net_bps=10.0)))

    assert report["mode"] == "hype_aligned_fixed_target_sensitivity_v1"
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False
    assert tuple(row["target_bps"] for row in report["development_grid"]) == (
        40.0,
        60.0,
    )
    identities = {
        row["nominal"]["entry_identity_sha256"] for row in report["development_grid"]
    }
    assert identities == {entry_identity(_trade())}
    assert TARGET_GRID_BPS == (40.0, 60.0, 80.0, 100.0, 150.0, 200.0, 300.0, 500.0)


def test_profitable_candidate_outranks_losing_fold_breadth() -> None:
    losing = _selection_trial(
        80.0, net=-10.0, ex_largest=-20.0, folds=(1.0, 1.0, -12.0)
    )
    profitable = _selection_trial(
        500.0, net=20.0, ex_largest=5.0, folds=(30.0, -15.0, 5.0)
    )

    selected = _select_development((losing, profitable))

    assert selected["selected_target_bps"] == 500.0


def _report(
    confirmation: tuple[pd.DataFrame, pd.DataFrame],
) -> dict[str, object]:
    return build_fixed_target_report(
        _market(),
        _trade(),
        (confirmation,),
        target_grid_bps=(40.0, 60.0),
        config=_execution(),
        development_fold_count=1,
        target_exit_tail_slippage_bps=5.0,
    )


def _selection_trial(
    target: float, *, net: float, ex_largest: float, folds: tuple[float, ...]
) -> dict[str, object]:
    period = {
        "entry_identity_sha256": "fixed-entry",
        "folds": {
            "challenger_positive_folds": sum(value > 0.0 for value in folds),
            "challenger_net_bps": list(folds),
        },
        "challenger": {
            "net_return_bps": net,
            "without_largest_winner_net_bps": ex_largest,
        },
    }
    return {"target_bps": target, "nominal": period, "target_exit_tail": period}
