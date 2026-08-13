"""Causal contract tests for cross-asset impulse events and labels."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.cross_asset_impulse_models import (
    CrossAssetImpulseConfig,
    CrossAssetImpulseEvent,
    ImpulseSignalVariant,
    declared_impulse_variants,
)
from hypervector.research.cross_asset_impulse_signal import (
    build_impulse_states,
    label_impulse_events,
    sample_impulse_events,
)

_START = pd.Timestamp("2026-01-01T00:00:00Z")


def _config(**updates: object) -> CrossAssetImpulseConfig:
    values: dict[str, object] = {
        "warmup_start": _START - pd.Timedelta(minutes=20),
        "development_start": _START,
        "development_end": _START + pd.Timedelta(minutes=90),
        "impulse_return_minutes": 2,
        "lookback_minutes": 6,
        "minimum_valid_returns": 5,
        "leader_z_threshold": 1.0,
        "catchup_gap_threshold": 0.25,
        "cooldown_minutes": 30,
        "horizons_minutes": (2, 5),
        "fold_count": 3,
        "delayed_entry_minutes": 1,
        "placebo_lag_minutes": 4,
        "minimum_events_per_fold": 2,
        "minimum_direction_events_per_fold": 1,
    }
    values.update(updates)
    return CrossAssetImpulseConfig(**values)  # type: ignore[arg-type]


def _close(values: list[float], start: pd.Timestamp | None = None) -> pd.Series:
    index = pd.date_range(start or _START, periods=len(values), freq="1min")
    return pd.Series(values, index=index, dtype=float)


def _valid(series: pd.Series, invalid: tuple[int, ...] = ()) -> pd.Series:
    output = pd.Series(True, index=series.index, dtype=bool)
    output.iloc[list(invalid)] = False
    return output


def _state_fixture(periods: int = 50) -> pd.DataFrame:
    bars = pd.date_range(_START - pd.Timedelta(minutes=1), periods=periods, freq="1min")
    decisions = bars + pd.Timedelta(minutes=1)
    frame = pd.DataFrame(
        {
            "bar_open_at": bars,
            "decision_time_utc": decisions,
            "leader_zscore": 3.0,
            "follower_zscore": 0.5,
            "catchup_gap_z": 2.5,
            "lagged_leader_zscore": 3.0,
            "lagged_catchup_gap_z": 2.5,
            "lagged_leader_valid_returns": 6,
            "leader_valid_returns": 6,
            "follower_valid_returns": 6,
        }
    )
    for variant in declared_impulse_variants():
        frame[f"{variant}_qualifies"] = False
        frame[f"{variant}_direction"] = pd.Series([None] * periods, dtype="object")
    return frame


def _mark_onsets(
    states: pd.DataFrame,
    variant: ImpulseSignalVariant,
    rows: tuple[int, ...],
    direction: str = "long",
) -> None:
    states.loc[list(rows), f"{variant}_qualifies"] = True
    states.loc[list(rows), f"{variant}_direction"] = direction


def _event(
    decision_minute: int,
    *,
    variant: ImpulseSignalVariant = "primary",
    direction: str = "long",
) -> CrossAssetImpulseEvent:
    decision = _START + pd.Timedelta(minutes=decision_minute)
    return CrossAssetImpulseEvent(
        bar_open_at=(decision - pd.Timedelta(minutes=1)).isoformat(),
        decision_time_utc=decision.isoformat(),
        entry_time_utc=decision.isoformat(),
        leader_symbol="BTC",
        follower_symbol="SOL",
        signal_variant=variant,
        direction=direction,  # type: ignore[arg-type]
        leader_zscore=3.0,
        follower_zscore=0.5,
        catchup_gap_z=2.5,
        leader_valid_returns=6,
        follower_valid_returns=6,
    )


def _bars(periods: int = 91, gaps: tuple[int, ...] = ()) -> pd.DataFrame:
    timestamps = pd.date_range(_START, periods=periods, freq="1min")
    source = np.full(periods, "hl", dtype=object)
    source[list(gaps)] = "hl_gap_fill"
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0 + np.arange(periods, dtype=float),
            "source": source,
        }
    )


def test_states_use_bar_clock_exact_returns_and_prior_fixed_window() -> None:
    start = _START - pd.Timedelta(minutes=12)
    leader = _close([100, 101, 99, 103, 102, 106, 104, 109, 108, 112, 111, 115], start)
    follower = _close(
        [50, 50.2, 50.1, 50.5, 50.4, 50.8, 50.7, 51, 50.9, 51.2, 51.1, 51.4], start
    )
    config = _config()

    states = build_impulse_states(
        leader,
        follower,
        config,
        leader_valid=_valid(leader),
        follower_valid=_valid(follower),
    )
    expected_return = np.log(leader).diff(2)
    expected_vol = expected_return.shift(1).rolling(6, min_periods=5).std(ddof=1)
    expected_vol.iloc[:6] = np.nan
    leader_zscore = expected_return / expected_vol
    follower_return = np.log(follower).diff(2)
    follower_vol = follower_return.shift(1).rolling(6, min_periods=5).std(ddof=1)
    follower_vol.iloc[:6] = np.nan
    expected_gap = leader_zscore.abs() - np.sign(leader_zscore) * (
        follower_return / follower_vol
    )

    assert states.loc[0, "bar_open_at"] == leader.index[0]
    assert states.loc[0, "decision_time_utc"] == leader.index[0] + pd.Timedelta(
        minutes=1
    )
    assert np.allclose(states["leader_return"], expected_return, equal_nan=True)
    assert np.allclose(states["leader_vol"], expected_vol, equal_nan=True)
    assert np.allclose(states["catchup_gap_z"], expected_gap, equal_nan=True)
    assert states.loc[7, "leader_valid_returns"] == 5


def test_inclusive_source_mask_and_coverage_floor_do_not_reset_history() -> None:
    start = _START - pd.Timedelta(minutes=20)
    leader = _close([100 + np.sin(i / 2) + i * 0.1 for i in range(24)], start)
    follower = _close([80 + np.cos(i / 3) + i * 0.05 for i in range(24)], start)
    leader_valid = _valid(leader, (10,))

    states = build_impulse_states(
        leader,
        follower,
        _config(),
        leader_valid=leader_valid,
        follower_valid=_valid(follower),
    )

    assert states.loc[10:12, "leader_return_valid"].eq(False).all()  # noqa: E712
    assert states.loc[9, "leader_return_valid"]
    assert states.loc[13, "leader_return_valid"]
    assert states.loc[13, "leader_valid_returns"] == 3
    assert np.isnan(states.loc[13, "leader_vol"])
    assert states.loc[18, "leader_valid_returns"] == 5
    assert np.isfinite(states.loc[18, "leader_vol"])
    assert not states.loc[10:15, "primary_qualifies"].any()


def test_state_builder_rejects_invalid_close_or_mask_identity() -> None:
    leader = _close([100, 101, 102, 103, 104, 105, 106, 107])
    follower = _close([50, 51, 52, 53, 54, 55, 56, 57])
    config = _config()

    with pytest.raises(ValueError, match="contiguous"):
        build_impulse_states(
            leader.drop(leader.index[2]),
            follower,
            config,
            leader_valid=_valid(leader.drop(leader.index[2])),
            follower_valid=_valid(follower),
        )
    bad_mask = _valid(leader).set_axis(leader.index + pd.Timedelta(minutes=1))
    with pytest.raises(ValueError, match="validity mask timestamps"):
        build_impulse_states(
            leader,
            follower,
            config,
            leader_valid=bad_mask,
            follower_valid=_valid(follower),
        )


def test_primary_and_fixed_controls_follow_frozen_equations() -> None:
    start = _START - pd.Timedelta(minutes=30)
    leader = _close([100 + np.sin(i / 2) + i * 0.2 for i in range(30)], start)
    follower = _close([80 + np.cos(i / 3) + i * 0.04 for i in range(30)], start)
    config = _config(placebo_lag_minutes=4)

    states = build_impulse_states(
        leader,
        follower,
        config,
        leader_valid=_valid(leader),
        follower_valid=_valid(follower),
    )
    base_valid = states[["leader_zscore", "follower_zscore"]].notna().all(axis=1)
    expected_primary = (
        base_valid
        & states["leader_zscore"].abs().ge(config.leader_z_threshold)
        & states["catchup_gap_z"].ge(config.catchup_gap_threshold)
    )
    lagged = states["leader_zscore"].shift(config.placebo_lag_minutes)
    lagged_gap = lagged.abs() - np.sign(lagged) * states["follower_zscore"]

    assert states["primary_qualifies"].equals(expected_primary)
    assert states["leader_only_ablation_qualifies"].equals(
        base_valid & states["leader_zscore"].abs().ge(config.leader_z_threshold)
    )
    assert states["follower_only_momentum_qualifies"].equals(
        base_valid & states["follower_zscore"].abs().ge(config.leader_z_threshold)
    )
    assert np.allclose(states["lagged_catchup_gap_z"], lagged_gap, equal_nan=True)
    assert (
        states.loc[states["follower_zscore"].lt(0), "follower_only_momentum_direction"]
        .eq("short")
        .all()
    )


def test_appending_future_rows_cannot_change_prior_states() -> None:
    start = _START - pd.Timedelta(minutes=30)
    leader = _close([100 + np.sin(i / 2) + i * 0.1 for i in range(30)], start)
    follower = _close([80 + np.cos(i / 3) + i * 0.05 for i in range(30)], start)
    config = _config()

    before = build_impulse_states(
        leader.iloc[:20],
        follower.iloc[:20],
        config,
        leader_valid=_valid(leader.iloc[:20]),
        follower_valid=_valid(follower.iloc[:20]),
    )
    after = build_impulse_states(
        leader,
        follower,
        config,
        leader_valid=_valid(leader),
        follower_valid=_valid(follower),
    ).iloc[:20]

    pd.testing.assert_frame_equal(before, after)


@pytest.mark.parametrize(("separation", "expected"), ((29, 1), (30, 2), (31, 2)))
def test_per_variant_cooldown_accepts_equality(
    separation: int,
    expected: int,
) -> None:
    states = _state_fixture()
    _mark_onsets(states, "primary", (1, 1 + separation))

    events = sample_impulse_events(
        states,
        "BTC",
        "SOL",
        _config(),
        signal_variant="primary",
    )

    assert len(events) == expected
    assert events[0].entry_time_utc == events[0].decision_time_utc
    assert pd.Timestamp(events[0].bar_open_at) + pd.Timedelta(
        minutes=1
    ) == pd.Timestamp(events[0].decision_time_utc)


def test_four_variants_sample_independently_and_warmup_never_emits() -> None:
    states = _state_fixture()
    states.loc[:, "decision_time_utc"] -= pd.Timedelta(minutes=5)
    states.loc[:, "bar_open_at"] -= pd.Timedelta(minutes=5)
    for offset, variant in enumerate(declared_impulse_variants()):
        _mark_onsets(states, variant, (offset, 6 + offset))

    sampled = {
        variant: sample_impulse_events(
            states,
            "BTC",
            "SOL",
            _config(),
            signal_variant=variant,
        )
        for variant in declared_impulse_variants()
    }

    assert all(len(events) == 1 for events in sampled.values())
    assert {
        event.signal_variant for events in sampled.values() for event in events
    } == set(declared_impulse_variants())
    assert all(
        pd.Timestamp(events[0].decision_time_utc) >= _START
        for events in sampled.values()
    )


def test_warmup_bar_with_development_boundary_decision_never_emits() -> None:
    states = _state_fixture()
    _mark_onsets(states, "primary", (0, 2))

    events = sample_impulse_events(
        states,
        "BTC",
        "SOL",
        _config(),
        signal_variant="primary",
    )

    assert [event.decision_time_utc for event in events] == [
        (_START + pd.Timedelta(minutes=2)).isoformat()
    ]


def test_labels_emit_base_and_delayed_exact_anchors() -> None:
    event = _event(2)
    config = _config(development_end=_START + pd.Timedelta(minutes=30))

    labels = label_impulse_events((event,), _bars(31), config)
    indexed = {(label.anchor, label.horizon_minutes): label for label in labels}

    assert len(labels) == 4
    base = indexed[("base", 2)]
    delayed = indexed[("delayed", 2)]
    assert base.entry_time_utc == (_START + pd.Timedelta(minutes=2)).isoformat()
    assert base.exit_time_utc == (_START + pd.Timedelta(minutes=4)).isoformat()
    assert delayed.entry_time_utc == (_START + pd.Timedelta(minutes=3)).isoformat()
    assert delayed.exit_time_utc == (_START + pd.Timedelta(minutes=5)).isoformat()
    assert base.directional_gross_return_bps == pytest.approx((104 / 102 - 1) * 10_000)
    assert all(label.status == "resolved" for label in labels)


def test_labels_require_authentic_inclusive_path_for_both_anchors() -> None:
    config = _config(development_end=_START + pd.Timedelta(minutes=30))

    labels = label_impulse_events((_event(2),), _bars(31, gaps=(4,)), config)

    assert len(labels) == 4
    assert all(label.status == "technical_gap" for label in labels)
    assert all(label.directional_gross_return_bps is None for label in labels)


def test_fold_boundary_and_development_end_have_exact_statuses() -> None:
    config = _config(development_end=_START + pd.Timedelta(minutes=30))
    events = (_event(8), _event(28))

    labels = label_impulse_events(events, _bars(31), config)
    by_decision = {
        (label.decision_time_utc, label.anchor, label.horizon_minutes): label
        for label in labels
    }

    fold_event = (_START + pd.Timedelta(minutes=8)).isoformat()
    end_event = (_START + pd.Timedelta(minutes=28)).isoformat()
    assert by_decision[(fold_event, "base", 2)].status == "fold_boundary_purged"
    assert by_decision[(fold_event, "delayed", 2)].status == "fold_boundary_purged"
    assert by_decision[(end_event, "base", 2)].status == "right_censored"
    assert by_decision[(end_event, "delayed", 2)].status == "right_censored"

    truncated = label_impulse_events((_event(8),), _bars(9), config)
    assert all(label.status == "fold_boundary_purged" for label in truncated)


def test_resolved_labels_are_append_invariant_and_short_signed() -> None:
    config = _config(development_end=_START + pd.Timedelta(minutes=30))
    event = _event(2, direction="short")

    before = label_impulse_events((event,), _bars(10), config)
    after = label_impulse_events((event,), _bars(31), config)

    assert before == after
    assert all(
        label.directional_gross_return_bps is not None
        and label.directional_gross_return_bps < 0.0
        for label in before
    )


def test_labeler_rejects_unexpected_source_or_noncontiguous_bars() -> None:
    config = _config(development_end=_START + pd.Timedelta(minutes=30))
    unexpected = _bars(31)
    unexpected.loc[4, "source"] = "vendor"
    with pytest.raises(ValueError, match="unexpected source"):
        label_impulse_events((_event(2),), unexpected, config)

    missing = _bars(31).drop(index=4).reset_index(drop=True)
    with pytest.raises(ValueError, match="contiguous"):
        label_impulse_events((_event(2),), missing, config)
