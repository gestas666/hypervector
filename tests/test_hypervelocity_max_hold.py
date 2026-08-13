"""Source-bounded maximum-hold replay contracts."""

from __future__ import annotations

import importlib

import pandas as pd
import pytest

from hypervector.research.maker_replay import MakerReplayConfig, replay_maker_orders


def _decisions(count: int) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=count, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"primary_regime": ["TREND_UP"] * count, "breakout_direction": None},
        index=index,
    )


def _book(seconds: list[int], bids: list[float], asks: list[float]) -> pd.DataFrame:
    origin = pd.Timestamp("2026-01-01T00:00:00Z")
    timestamps = [origin + pd.Timedelta(seconds=value) for value in seconds]
    return pd.DataFrame(
        {
            "ts_ms": [int(value.timestamp() * 1000) for value in timestamps],
            "best_bid": bids,
            "best_ask": asks,
        }
    )


@pytest.mark.parametrize("value", [0.0, -1.0, True, float("inf"), float("nan")])
def test_maximum_hold_rejects_invalid_values(value: object) -> None:
    """A configured holding deadline must be finite and strictly positive."""
    with pytest.raises(ValueError, match="maximum_hold_seconds"):
        MakerReplayConfig(maximum_hold_seconds=value)


def test_maximum_hold_exits_at_first_deadline_bbo_with_taker_fee() -> None:
    """A surviving position exits at adverse BBO, not before its deadline."""
    report = replay_maker_orders(
        _book(
            [60, 70, 89, 90],
            [100.0, 99.0, 99.5, 99.4],
            [101.0, 100.0, 99.6, 99.5],
        ),
        _decisions(4),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.00015,
            taker_fee_rate=0.00045,
            fill_rule="touch",
            maximum_hold_seconds=20.0,
        ),
    )

    assert report.time_exits == 1
    assert report.completed_trades == 1
    assert report.trades[0].status == "time_exited"
    assert report.trades[0].hold_seconds == 20.0
    assert report.trades[0].exit_price == 99.4
    assert report.trades[0].fees == pytest.approx(1.67244)
    assert report.final_equity == pytest.approx(81.52756)
    assert report.lifecycles[0].status == "time_exited"


def test_signal_specific_maximum_hold_overrides_default_for_mixed_recipes() -> None:
    """One serialized replay can retain a different deadline per entry signal."""
    decisions = _decisions(4)
    decisions["maximum_hold_seconds"] = [10.0, None, None, None]

    report = replay_maker_orders(
        _book(
            [60, 70, 79, 80],
            [100.0, 99.0, 99.5, 99.4],
            [101.0, 100.0, 99.6, 99.5],
        ),
        decisions,
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            fill_rule="touch",
            maximum_hold_seconds=20.0,
        ),
    )

    assert report.time_exits == 1
    assert report.trades[0].hold_seconds == 10.0


def test_liquidation_precedes_time_exit_on_the_same_book_event() -> None:
    """A deadline cannot relabel an already-liquidatable position as timed out."""
    report = replay_maker_orders(
        _book(
            [60, 70, 80],
            [100.0, 99.0, 98.0],
            [101.0, 100.0, 98.1],
        ),
        _decisions(3),
        MakerReplayConfig(
            initial_equity=100.0,
            maker_fee_rate=0.0,
            taker_fee_rate=0.00045,
            fill_rule="touch",
            maximum_hold_seconds=10.0,
        ),
    )

    assert report.liquidations == 1
    assert report.time_exits == 0
    assert report.trades[0].status == "liquidated"


def test_maximum_hold_candidate_grid_is_exact_and_frozen() -> None:
    """The source-bounded family cannot grow after its outcomes are observed."""
    module = importlib.import_module(
        "hypervector.research.hypervelocity_margin_stop_compare"
    )

    configs = module.maximum_hold_candidate_configs(10_000.0)

    assert list(configs) == [
        "no_timeout_control",
        "max_hold_6h",
        "max_hold_12h",
        "max_hold_24h",
    ]
    assert [config.maximum_hold_seconds for config in configs.values()] == [
        None,
        21_600.0,
        43_200.0,
        86_400.0,
    ]
    assert all(config.fixed_margin_stop_pct is None for config in configs.values())


def test_source_hold_compatibility_counts_closed_and_open_positions() -> None:
    """Deadline compatibility uses closed logical holds and exposes open rows."""
    module = importlib.import_module(
        "hypervector.research.hypervelocity_margin_stop_compare"
    )
    opens = pd.date_range("2026-01-01", periods=4, freq="1D", tz="UTC")
    positions = pd.DataFrame(
        {
            "open_time_utc": opens,
            "close_time_utc": [
                opens[0] + pd.Timedelta(hours=5),
                opens[1] + pd.Timedelta(hours=8),
                opens[2] + pd.Timedelta(hours=20),
                pd.NaT,
            ],
            "side": ["long", "short", "long", "short"],
            "entry_price": [100.0, 101.0, 102.0, 103.0],
            "status": ["closed", "closed", "closed", "open"],
        }
    )
    configs = module.maximum_hold_candidate_configs()

    result = module.source_hold_compatibility(positions, configs)

    assert result["logical_positions"] == 4
    assert result["closed_positions"] == 3
    assert result["open_or_missing_close"] == 1
    assert result["candidates"]["no_timeout_control"]["compatible_closed"] == 3
    assert result["candidates"]["max_hold_6h"]["compatible_closed"] == 1
    assert result["candidates"]["max_hold_12h"]["compatible_closed"] == 2
    assert result["candidates"]["max_hold_24h"]["compatible_closed"] == 3
