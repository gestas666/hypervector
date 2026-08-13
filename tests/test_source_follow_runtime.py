"""Causal runtime contract for the pinned source-follow shadow candidate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import pandas as pd

from hypervector.regime.source_follow_runtime import (
    FiveMinuteBar,
    FiveMinuteBarAssembler,
    SourceFollowDecision,
    SourceFollowRuntime,
    SourceLongObservation,
    SourceRegimeLabel,
)
from hypervector.regime.source_follow_session import SourceFollowSessionSignal
from hypervector.regime.pinned_hypertrader import PinnedHypertraderClassifier
from hypervector.regime import pinned_hypertrader


class _FakeClassifier:
    def __init__(self, labels: tuple[tuple[str, float], ...]) -> None:
        self._labels = labels
        self._position = 0

    def classify(self, bar: FiveMinuteBar) -> SourceRegimeLabel:
        primary, confidence = self._labels[self._position]
        self._position += 1
        return SourceRegimeLabel(
            label_time_utc=bar.timestamp_utc,
            primary=primary,
            secondary=None,
            confidence=confidence,
        )


class _RecipeClassifier:
    def __init__(self, labels: tuple[tuple[str, str | None, float], ...]) -> None:
        self._labels = labels
        self._position = 0

    def classify(self, bar: FiveMinuteBar) -> SourceRegimeLabel:
        primary, secondary, confidence = self._labels[self._position]
        self._position += 1
        return SourceRegimeLabel(
            label_time_utc=bar.timestamp_utc,
            primary=primary,
            secondary=secondary,
            confidence=confidence,
        )


def _bar(
    position: int,
    *,
    opening: float = 100.0,
    high: float = 100.5,
    low: float = 99.5,
) -> FiveMinuteBar:
    return FiveMinuteBar(
        timestamp_utc=datetime(2026, 7, 29, tzinfo=UTC)
        + timedelta(minutes=5 * position),
        open=opening,
        high=high,
        low=low,
        close=100.0,
        volume=10.0,
    )


def _bar_at(timestamp: datetime) -> FiveMinuteBar:
    return FiveMinuteBar(
        timestamp_utc=timestamp,
        open=100.0,
        high=100.5,
        low=99.5,
        close=100.0,
        volume=10.0,
    )


def test_source_decision_retains_authoritative_completed_bar() -> None:
    """A regime decision must retain the exact measured candle used to classify it."""
    runtime = SourceFollowRuntime(_FakeClassifier((("RANGE", 0.6),)))
    bar = FiveMinuteBar(
        timestamp_utc=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
        open=63_950.0,
        high=64_020.0,
        low=63_900.0,
        close=64_000.0,
        volume=123.45,
    )

    decision = runtime.update(bar)

    assert decision.bar_open == bar.open
    assert decision.bar_high == bar.high
    assert decision.bar_low == bar.low
    assert decision.bar_close == bar.close
    assert decision.bar_volume == bar.volume


def test_exact_source_long_recipes_are_observed_without_entry_authority() -> None:
    """Pinned B/C long rules remain visible but cannot alter short execution."""
    breakout = SourceFollowRuntime(
        _RecipeClassifier(
            (
                ("RANGE", None, 0.5),
                ("BREAKOUT", "BK_UPWARD", 0.6),
            )
        )
    )
    breakout.update(_bar_at(datetime(2026, 7, 29, 0, 0, tzinfo=UTC)))
    recipe_b = breakout.update(_bar_at(datetime(2026, 7, 29, 0, 5, tzinfo=UTC)))

    fade = SourceFollowRuntime(
        _RecipeClassifier(
            (
                ("RANGE", None, 0.5),
                ("TREND_DOWN", None, 0.4),
            )
        )
    )
    fade.update(_bar_at(datetime(2026, 7, 29, 6, 55, tzinfo=UTC)))
    recipe_c = fade.update(_bar_at(datetime(2026, 7, 29, 7, 0, tzinfo=UTC)))

    assert recipe_b.source_long_observation == SourceLongObservation(
        recipe_id="bk_up_asia_conf06",
        maximum_hold_seconds=14_400.0,
    )
    assert recipe_b.entry_eligible is False
    assert recipe_b.entry_direction is None
    assert recipe_c.source_long_observation == SourceLongObservation(
        recipe_id="fade_td_eu",
        maximum_hold_seconds=86_400.0,
    )
    assert recipe_c.entry_eligible is False
    assert recipe_c.entry_direction is None


def test_source_long_observer_marks_out_of_session_rules_as_challengers() -> None:
    """24/7 challengers must remain distinct from exact B/C source recipes."""
    for timestamp, primary, secondary, expected in (
        (
            datetime(2026, 7, 29, 8, 0, tzinfo=UTC),
            "BREAKOUT",
            "BK_UPWARD",
            "bk_up_24h_challenger",
        ),
        (
            datetime(2026, 7, 29, 16, 0, tzinfo=UTC),
            "TREND_DOWN",
            None,
            "trend_down_24h_direction_challenger",
        ),
    ):
        runtime = SourceFollowRuntime(
            _RecipeClassifier((("RANGE", None, 0.5), (primary, secondary, 0.9)))
        )
        runtime.update(_bar_at(timestamp - timedelta(minutes=5)))
        decision = runtime.update(_bar_at(timestamp))

        observation = decision.source_long_observation
        assert observation is not None
        assert observation.recipe_id == expected
        assert observation.authority == "observe_only"


def test_trend_up_onset_is_recorded_as_a_24h_long_challenger() -> None:
    runtime = SourceFollowRuntime(
        _RecipeClassifier((("RANGE", None, 0.5), ("TREND_UP", None, 0.9)))
    )
    runtime.update(_bar_at(datetime(2026, 7, 29, 18, 0, tzinfo=UTC)))

    decision = runtime.update(_bar_at(datetime(2026, 7, 29, 18, 5, tzinfo=UTC)))

    assert decision.source_long_observation == SourceLongObservation(
        "trend_up_24h_challenger",
        86_400.0,
    )
    assert decision.entry_eligible is False
    assert decision.entry_direction is None


def test_bidirectional_runtime_routes_aligned_trend_and_breakout_onsets() -> None:
    """Bidirectional mode routes only aligned up/down source onsets."""
    runtime = SourceFollowRuntime(
        _RecipeClassifier(
            (
                ("RANGE", None, 0.5),
                ("TREND_UP", None, 0.9),
                ("RANGE", None, 0.5),
                ("BREAKOUT", "BK_UPWARD", 0.9),
                ("RANGE", None, 0.5),
                ("TREND_DOWN", None, 0.9),
            )
        ),
        direction_mode="trend_bidirectional",
    )

    decisions = tuple(runtime.update(_bar(position)) for position in range(6))

    assert [decision.entry_direction for decision in decisions] == [
        None,
        "long",
        None,
        "long",
        None,
        "short",
    ]
    assert decisions[1].entry_eligible is True
    assert decisions[3].entry_eligible is True
    assert decisions[5].entry_eligible is True
    assert runtime.entry_direction_at(decisions[5].available_at_utc) == "short"


def test_bidirectional_runtime_does_not_promote_countertrend_fade_long() -> None:
    """A TREND_DOWN onset has one executable side even when fade-long is observed."""
    runtime = SourceFollowRuntime(
        _RecipeClassifier((("RANGE", None, 0.5), ("TREND_DOWN", None, 0.9))),
        direction_mode="trend_bidirectional",
    )
    runtime.update(_bar_at(datetime(2026, 7, 29, 6, 55, tzinfo=UTC)))

    decision = runtime.update(_bar_at(datetime(2026, 7, 29, 7, 0, tzinfo=UTC)))

    assert decision.entry_direction == "short"
    assert decision.source_long_observation == SourceLongObservation(
        "fade_td_eu",
        86_400.0,
    )


def _load_parity_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_runtime_parity.py")
    spec = importlib.util.spec_from_file_location("source_runtime_parity", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"source runtime parity script could not load: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_follow_emits_only_qualified_trend_down_onset() -> None:
    """Confidence qualification applies to a fresh confirmed onset only."""
    runtime = SourceFollowRuntime(
        _FakeClassifier(
            (
                ("RANGE", 0.50),
                ("TREND_DOWN", 0.69),
                ("RANGE", 0.50),
                ("TREND_DOWN", 0.70),
                ("TREND_DOWN", 0.95),
            )
        )
    )

    decisions = tuple(runtime.update(_bar(position)) for position in range(5))

    assert [decision.entry_eligible for decision in decisions] == [
        False,
        False,
        False,
        True,
        False,
    ]
    qualified = decisions[3]
    assert qualified.primary == "TREND_DOWN"
    assert qualified.primary_onset is True
    assert qualified.entry_direction == "short"
    assert qualified.maximum_hold_seconds == 86_400.0
    assert qualified.available_at_utc == _bar(3).timestamp_utc + timedelta(minutes=5)
    assert runtime.entry_direction_at(qualified.available_at_utc) == "short"
    assert (
        runtime.entry_direction_at(
            qualified.available_at_utc + timedelta(seconds=59, microseconds=999_999)
        )
        == "short"
    )
    assert (
        runtime.entry_direction_at(qualified.available_at_utc + timedelta(seconds=60))
        is None
    )
    assert decisions[4].primary_onset is False


def test_source_follow_range_filter_consumes_the_onset() -> None:
    """A wide onset cannot become eligible later without a regime reset."""
    runtime = SourceFollowRuntime(
        _FakeClassifier((("RANGE", 0.5), ("TREND_DOWN", 0.9), ("TREND_DOWN", 0.9)))
    )

    runtime.update(_bar(0))
    wide = runtime.update(_bar(1, high=101.01, low=100.0))
    later = runtime.update(_bar(2))

    assert wide.signal_range_bps == pytest.approx(101.0)
    assert wide.source_event is True
    assert wide.entry_eligible is False
    assert wide.exclusion_reason == "signal_range"
    assert later.signal_range_bps == pytest.approx(100.0)
    assert later.primary_onset is False
    assert later.entry_eligible is False


def test_source_follow_minimum_range_consumes_a_weak_onset() -> None:
    """A configured weak-onset floor must not rearm inside the same regime."""
    runtime = SourceFollowRuntime(
        _FakeClassifier(
            (
                ("TREND_DOWN", 0.9),
                ("TREND_DOWN", 0.9),
            )
        ),
        minimum_range_bps=12.0,
    )

    weak = runtime.update(_bar(0, high=100.06, low=99.95))
    later = runtime.update(_bar(1, high=100.5, low=99.5))

    assert weak.signal_range_bps == pytest.approx(11.0)
    assert weak.source_event is True
    assert weak.entry_eligible is False
    assert weak.exclusion_reason == "signal_range_below_minimum"
    assert later.primary_onset is False
    assert later.entry_eligible is False


def test_source_follow_rejects_an_inverted_range_contract() -> None:
    """A minimum above the maximum must fail before any market decision."""
    with pytest.raises(ValueError, match="minimum range must not exceed maximum"):
        SourceFollowRuntime(
            _FakeClassifier((("TREND_DOWN", 0.9),)),
            minimum_range_bps=101.0,
            maximum_range_bps=100.0,
        )


def test_source_follow_requires_contiguous_aligned_five_minute_bars() -> None:
    """Missing or misaligned source bars fail closed instead of inventing state."""
    runtime = SourceFollowRuntime(
        _FakeClassifier((("RANGE", 0.5), ("TREND_DOWN", 0.8)))
    )
    runtime.update(_bar(0))

    with pytest.raises(ValueError, match="contiguous five-minute bars"):
        runtime.update(_bar(2))
    with pytest.raises(ValueError, match="five-minute boundary"):
        FiveMinuteBar(
            timestamp_utc=datetime(2026, 7, 29, 0, 1, tzinfo=UTC),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )


def test_five_minute_assembler_emits_only_completed_contiguous_groups() -> None:
    """A 5m source bar becomes visible only after all five 1m bars complete."""
    assembler = FiveMinuteBarAssembler()
    emitted = [
        assembler.update(
            timestamp_utc=datetime(2026, 7, 28, 12, minute, tzinfo=UTC),
            open=100.0 + minute,
            high=102.0 + minute,
            low=99.0 + minute,
            close=101.0 + minute,
            volume=10.0 + minute,
        )
        for minute in range(5)
    ]

    assert emitted[:4] == [None, None, None, None]
    assert emitted[4] == FiveMinuteBar(
        timestamp_utc=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
        open=100.0,
        high=106.0,
        low=99.0,
        close=105.0,
        volume=60.0,
    )


def test_five_minute_assembler_skips_leading_partial_group() -> None:
    """An incomplete leading bucket warms nothing and cannot leak a label."""
    assembler = FiveMinuteBarAssembler()
    for minute in (3, 4):
        assert (
            assembler.update(
                timestamp_utc=datetime(2026, 7, 28, 12, minute, tzinfo=UTC),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1.0,
            )
            is None
        )

    completed = None
    for minute in range(5, 10):
        completed = assembler.update(
            timestamp_utc=datetime(2026, 7, 28, 12, minute, tzinfo=UTC),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )
    assert completed is not None
    assert completed.timestamp_utc == datetime(2026, 7, 28, 12, 5, tzinfo=UTC)


def test_five_minute_assembler_fails_closed_on_one_minute_gap() -> None:
    """A feed gap cannot be converted into a synthetic completed source bar."""
    assembler = FiveMinuteBarAssembler()
    assembler.update(
        timestamp_utc=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1.0,
    )

    with pytest.raises(ValueError, match="contiguous one-minute bars"):
        assembler.update(
            timestamp_utc=datetime(2026, 7, 28, 12, 2, tzinfo=UTC),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )


def test_session_signal_exposes_exact_one_minute_entry_pulse() -> None:
    """A completed source label becomes an entry only at its causal boundary."""
    signal = SourceFollowSessionSignal(
        SourceFollowRuntime(_FakeClassifier((("TREND_DOWN", 0.9),)))
    )
    for minute in range(5):
        decision = signal.update_minute(
            timestamp_utc=datetime(2026, 7, 28, 12, minute, tzinfo=UTC),
            open=100.0,
            high=100.4,
            low=99.6,
            close=100.0,
            volume=1.0,
        )

    available = datetime(2026, 7, 28, 12, 5, tzinfo=UTC)
    assert decision is not None
    assert decision.available_at_utc == available
    assert signal.directions_at(available) == ("short", "short")
    assert signal.directions_at(available + timedelta(seconds=60)) == (None, None)
    assert signal.latest_decision is decision


def test_session_signal_enforces_half_open_utc_entry_window() -> None:
    """The promoted session permits entries at 06:00 but excludes 15:00 UTC."""
    inside = SourceFollowSessionSignal(
        SourceFollowRuntime(_FakeClassifier((("TREND_DOWN", 0.9),))),
        entry_session_utc="[06:00,15:00)",
    )
    outside = SourceFollowSessionSignal(
        SourceFollowRuntime(_FakeClassifier((("TREND_DOWN", 0.9),))),
        entry_session_utc="[06:00,15:00)",
    )
    for minute in range(55, 60):
        inside.update_minute(
            timestamp_utc=datetime(2026, 7, 28, 5, minute, tzinfo=UTC),
            open=100.0,
            high=100.4,
            low=99.6,
            close=100.0,
            volume=1.0,
        )
        outside.update_minute(
            timestamp_utc=datetime(2026, 7, 28, 14, minute, tzinfo=UTC),
            open=100.0,
            high=100.4,
            low=99.6,
            close=100.0,
            volume=1.0,
        )

    start = datetime(2026, 7, 28, 6, 0, tzinfo=UTC)
    end = datetime(2026, 7, 28, 15, 0, tzinfo=UTC)
    assert inside.directions_at(start) == ("short", "short")
    assert outside.directions_at(end) == (None, None)
    assert inside.entry_session_active_at(start) is True
    assert outside.entry_session_active_at(end) is False


def test_pinned_classifier_fails_closed_without_verified_source(
    tmp_path: Path,
) -> None:
    """A missing external source tree cannot silently change classification."""
    with pytest.raises(FileNotFoundError, match="pinned Hypertrader source is missing"):
        PinnedHypertraderClassifier(tmp_path / "missing-backend")


def test_pinned_classifier_reuses_the_same_verified_namespace() -> None:
    """Independent classifiers may share one checksum-pinned module tree."""
    backend = Path("data/cache/vendor/hypertrader_ad15/backend")

    first = PinnedHypertraderClassifier(backend)
    second = PinnedHypertraderClassifier(backend)

    assert first.source_identity == second.source_identity
    assert first.classify(_bar(0)) == second.classify(_bar(0))


def test_pinned_namespace_rejects_a_different_backend_root() -> None:
    """Namespace reuse must remain fail-closed across backend identities."""
    backend = Path("data/cache/vendor/hypertrader_ad15/backend")
    PinnedHypertraderClassifier(backend)

    with pytest.raises(RuntimeError, match="different or unmanaged backend"):
        pinned_hypertrader._isolate_regime_namespace(Path("other/backend").resolve())


def test_source_runtime_parity_command_is_report_only() -> None:
    """Parity validation records evidence and has no execution authority."""
    module = _load_parity_script()
    args = module._parser().parse_args(
        [
            "--upstream-backend",
            "upstream/backend",
            "--labels",
            "labels.parquet",
            "--labels-metadata",
            "labels.json",
            "--candles",
            "candles.parquet",
            "--out",
            "parity.json",
        ]
    )
    contract = module._experiment_contract()

    assert args.upstream_backend == Path("upstream/backend")
    assert contract["report_only"] is True
    assert contract["runtime_strategy_changed"] is False
    assert contract["execution_authority"] == "none"
    assert contract["entry_family"] == "source-follow-all-day-confidence-70"
    assert contract["decision_delay_seconds"] == 300
    assert contract["entry_pulse_seconds"] == 60


def test_parity_comparison_detects_changed_source_label() -> None:
    """A label disagreement is explicit rather than success-shaped parity."""
    module = _load_parity_script()
    timestamp = datetime(2026, 7, 29, tzinfo=UTC)
    labels = pd.DataFrame(
        {
            "primary_code": ["RANGE"],
            "secondary_code": [None],
            "confidence": [0.5],
        },
        index=pd.DatetimeIndex([timestamp]),
    )
    decision = SourceFollowDecision(
        label_time_utc=timestamp,
        available_at_utc=timestamp + timedelta(minutes=5),
        primary="TREND_DOWN",
        secondary=None,
        confidence=0.5,
        primary_onset=True,
        source_event=False,
        signal_range_bps=50.0,
        entry_eligible=False,
        entry_direction=None,
        maximum_hold_seconds=None,
        exclusion_reason="source_confidence",
        bar_open=100.0,
        bar_high=100.5,
        bar_low=99.5,
        bar_close=100.0,
        bar_volume=10.0,
    )

    result = module._compare_labels(labels, [decision])

    assert result["exact"] is False
    assert result["mismatch_count"] == 1
    assert result["mismatches"][0]["expected_primary"] == "RANGE"
    assert result["mismatches"][0]["actual_primary"] == "TREND_DOWN"


def test_event_parity_retains_range_filtered_source_onset() -> None:
    """A qualified onset remains an event when the range ceiling filters entry."""
    module = _load_parity_script()
    timestamp = datetime(2026, 7, 29, tzinfo=UTC)
    expected = pd.DataFrame(
        {
            "label_time_utc": [timestamp],
            "decision_time_utc": [timestamp + timedelta(minutes=5)],
            "confidence": [0.9],
            "signal_range_bps": [101.0],
            "entry_eligible": [False],
        }
    )
    decision = SourceFollowDecision(
        label_time_utc=timestamp,
        available_at_utc=timestamp + timedelta(minutes=5),
        primary="TREND_DOWN",
        secondary=None,
        confidence=0.9,
        primary_onset=True,
        source_event=True,
        signal_range_bps=101.0,
        entry_eligible=False,
        entry_direction=None,
        maximum_hold_seconds=None,
        exclusion_reason="signal_range",
        bar_open=100.0,
        bar_high=101.01,
        bar_low=100.0,
        bar_close=100.5,
        bar_volume=10.0,
    )

    result = module._compare_events(expected, [decision])

    assert result["exact"] is True
    assert result["expected_event_count"] == 1
    assert result["actual_event_count"] == 1
    assert result["eligible_entry_count"] == 0
