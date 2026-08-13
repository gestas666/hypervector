"""Causal taker-entry parity screen for the BTC liquidity-sweep long."""

from __future__ import annotations

import pytest
import pandas as pd

from hypervector.research.btc_liquidity_sweep_taker_parity import (
    SignalPathObservation,
    TakerFriction,
    build_taker_parity_report,
    derive_signal_paths,
)


def _path(
    signal: str,
    partition: str,
    delay: int,
    stop_time_ms: int | None,
    targets: dict[float, int | None],
) -> SignalPathObservation:
    return SignalPathObservation(
        signal_time_utc=signal,
        partition=partition,
        entry_delay_seconds=delay,
        entry_time_ms=1_000 + delay * 1_000,
        entry_ask=100.0,
        stop_time_ms=stop_time_ms,
        target_times_ms=targets,
        maximum_mark_gap_ms=5_000,
        maximum_mark_gap_by_target_ms={target: 5_000 for target in targets},
    )


def _fixture_paths() -> tuple[SignalPathObservation, ...]:
    paths: list[SignalPathObservation] = []
    for delay in (0, 15, 30, 60):
        for index in range(6):
            loss = index == 5 or (delay == 60 and index == 3)
            stop = 90_000 if loss else None
            targets = {
                26.666666666666668: None if loss else 70_000,
                40.0: None if loss else 75_000,
                60.0: None if loss else 80_000,
                80.0: None if loss or index == 1 else 85_000,
            }
            paths.append(_path(f"dev-{index}", "development", delay, stop, targets))
        paths.append(
            _path(
                "forward-0",
                "forward",
                delay,
                None,
                {
                    26.666666666666668: 70_000,
                    40.0: 75_000,
                    60.0: 80_000,
                    80.0: None,
                },
            )
        )
    return tuple(paths)


def test_screen_selects_largest_stable_target_and_entry_delay() -> None:
    """Development selects 60 bps and rejects the degraded 60-second entry."""
    report = build_taker_parity_report(
        _fixture_paths(),
        target_grid_bps=(26.666666666666668, 40.0, 60.0, 80.0),
        stop_bps=60.0,
        friction=TakerFriction(win_bps=13.3533, loss_bps=25.2371),
    )

    selection = report["selection"]
    assert selection["target_bps"] == pytest.approx(60.0)
    assert selection["maximum_entry_delay_seconds"] == 30
    assert selection["development"] == {"wins": 5, "losses": 1, "timeouts": 0}
    assert selection["forward"] == {"wins": 1, "losses": 0, "timeouts": 0}
    assert selection["friction_adjusted_breakeven_win_rate"] == pytest.approx(
        0.6463, abs=0.0002
    )


def test_screen_is_report_only_and_discloses_posthoc_selection() -> None:
    """The screen cannot grant live authority or relabel tuning as validation."""
    report = build_taker_parity_report(
        _fixture_paths(),
        target_grid_bps=(26.666666666666668, 40.0, 60.0, 80.0),
        stop_bps=60.0,
        friction=TakerFriction(win_bps=13.3533, loss_bps=25.2371),
    )

    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["selection"]["development_selected"] is True
    assert report["selection"]["forward_sample_count"] == 1
    assert report["selection"]["confidence"] == "low"


def test_screen_rejects_missing_delay_or_unresolved_mark_path() -> None:
    """Incomplete grids reject; mark-gap paths remain explicit unresolved rows."""
    paths = list(_fixture_paths())
    paths.pop()
    with pytest.raises(ValueError, match="rectangular"):
        build_taker_parity_report(
            tuple(paths),
            target_grid_bps=(26.666666666666668, 40.0, 60.0, 80.0),
            stop_bps=60.0,
            friction=TakerFriction(win_bps=13.3533, loss_bps=25.2371),
        )

    unresolved = list(_fixture_paths())
    unresolved[14] = SignalPathObservation(
        **{
            **unresolved[14].__dict__,
            "maximum_mark_gap_ms": 121_000,
            "maximum_mark_gap_by_target_ms": {
                **unresolved[14].maximum_mark_gap_by_target_ms,
                60.0: 121_000,
            },
        }
    )
    report = build_taker_parity_report(
        tuple(unresolved),
        target_grid_bps=(26.666666666666668, 40.0, 60.0, 80.0),
        stop_bps=60.0,
        friction=TakerFriction(win_bps=13.3533, loss_bps=25.2371),
    )
    assert report["selection"]["development_path_resolved"] is False
    assert report["selection"]["unresolved_development_signals"] == ["dev-0"]


def test_path_derivation_uses_post_delay_ask_and_causal_barriers() -> None:
    """Every delay enters at its first later ask and compares later mark/BBO time."""
    signal_ms = 1_800_000_000_000
    books = pd.DataFrame(
        {
            "ts_ms": [
                signal_ms,
                signal_ms + 15_000,
                signal_ms + 30_000,
                signal_ms + 60_000,
                signal_ms + 90_000,
            ],
            "best_bid": [99.99, 100.00, 100.03, 101.00, 121.00],
            "best_ask": [100.00, 100.10, 110.00, 120.00, 121.10],
        }
    )
    marks = pd.DataFrame(
        {
            "ts_ms": [signal_ms, signal_ms + 30_000, signal_ms + 90_000],
            "mark_price": [100.0, 100.2, 99.0],
        }
    )

    paths = derive_signal_paths(
        signal_time_utc=pd.Timestamp(signal_ms, unit="ms", tz="UTC").isoformat(),
        partition="development",
        books=books,
        marks=marks,
        entry_delays_seconds=(0, 30, 60),
        target_grid_bps=(40.0, 60.0),
        stop_bps=60.0,
        evidence_end_ms=signal_ms + 100_000,
    )

    assert [path.entry_ask for path in paths] == [100.0, 110.0, 120.0]
    assert paths[0].target_times_ms[60.0] == signal_ms + 60_000
    assert paths[0].maximum_mark_gap_ms == 30_000
    assert paths[0].maximum_mark_gap_by_target_ms[60.0] == 30_000
    assert paths[1].target_times_ms[40.0] == signal_ms + 90_000
    assert paths[2].stop_time_ms == signal_ms + 90_000
