"""Tests for the SOL range-onset venue-event replay command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from hypervector.research.mark_stop_trigger import SampledMarkSeries
from hypervector.research.oracle_price_series import CausalOraclePriceSeries

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "multi_asset_range_onset_event_replay.py"
)


def _module() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.fail("multi-asset range-onset event replay script is missing")
    spec = spec_from_file_location("multi_asset_range_onset_event_replay", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT.parent))
    return module


def test_event_trial_grid_is_small_and_predeclared() -> None:
    """Event replay must retain both anchors at low and candidate exposure."""
    module = _module()

    trials = module.event_trial_grid()

    assert len(trials) == 4
    assert {(trial.stop_bps, trial.effective_exposure) for trial in trials} == {
        (60.0, 0.5),
        (60.0, 3.0),
        (80.0, 0.5),
        (80.0, 3.0),
    }


def test_capacity_trial_grid_freezes_fillable_exposure_ladder() -> None:
    """Capacity diagnosis must vary exposure while holding the lead stop fixed."""
    module = _module()

    trials = module.capacity_trial_grid()

    assert len(trials) == 4
    assert [(trial.stop_bps, trial.effective_exposure) for trial in trials] == [
        (60.0, 0.10),
        (60.0, 0.15),
        (60.0, 0.25),
        (60.0, 0.50),
    ]


def test_v49_target_grid_binds_account_size_stop_and_exit_surface() -> None:
    """The post-hoc target challenger must match the planned v49 SOL notional."""
    module = _module()

    trials = module.v49_target_trial_grid()

    assert [trial.target_bps for trial in trials] == [
        None,
        25.0,
        40.0,
        60.0,
        80.0,
        120.0,
    ]
    assert {trial.initial_equity for trial in trials} == {5_000.0}
    assert {trial.stop_bps for trial in trials} == {80.0}
    assert {trial.effective_exposure for trial in trials} == {0.75}
    assert {trial.taker_fee_rate for trial in trials} == {0.000432}
    assert {module._event_config(trial).target_bps for trial in trials} == {
        None,
        25.0,
        40.0,
        60.0,
        80.0,
        120.0,
    }


def test_capacity_shape_grid_compares_predeclared_stops_at_fillable_size() -> None:
    """The stop challenger must hold the accepted 0.15x capacity fixed."""
    module = _module()

    trials = module.capacity_shape_trial_grid()

    assert [(trial.stop_bps, trial.effective_exposure) for trial in trials] == [
        (60.0, 0.15),
        (80.0, 0.15),
    ]


def test_posthoc_midpoint_grid_adds_only_the_seventy_bps_stop() -> None:
    """The diagnostic midpoint must not change leverage or portfolio exposure."""
    module = _module()

    trials = module.capacity_shape_midpoint_trial_grid()

    assert [(trial.stop_bps, trial.effective_exposure) for trial in trials] == [
        (60.0, 0.15),
        (70.0, 0.15),
        (80.0, 0.15),
    ]


def test_trial_report_binds_complete_execution_model() -> None:
    """Replay evidence must identify hold, fees, cooldown, and venue limit."""
    module = _module()
    trial = module.EventTrial(60.0, 0.03, 5.0)
    config = module.EventReplayConfig(
        margin_fraction=trial.margin_fraction,
        leverage=trial.leverage,
        stop_bps=trial.stop_bps,
    )
    report = module.EventReplayReport(
        "complete",
        15_000.0,
        15_000.0,
        0,
        0,
        0,
        0,
        None,
        0.0,
        0.0,
        0,
        0.0,
        0.0,
        0,
        None,
        (),
    )

    payload = module._trial_report(trial, config, report)

    assert payload["replay_config"] == {
        "initial_equity": 15_000.0,
        "margin_fraction": 0.03,
        "leverage": 5.0,
        "venue_max_leverage": 20.0,
        "stop_bps": 60.0,
        "target_bps": None,
        "max_hold_ms": 172_800_000,
        "taker_fee_rate": 0.00045,
        "reentry_cooldown_ms": 60_000,
        "decision_delay_ms": 0,
    }


def test_event_signals_become_available_after_minute_close() -> None:
    """A signal on minute T can execute only at the T+1 minute boundary."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")
    bars = pd.DataFrame({"close": [100.0, 101.0, 102.0]}, index=index)
    signals = pd.DataFrame(
        {
            "long_entry": [False, True, False],
            "short_entry": [False, False, False],
            "long_exit": [False, False, False],
            "short_exit": [False, False, False],
        },
        index=index,
    )

    events = module.to_event_signals(bars, signals)

    assert len(events) == 1
    assert events[0].decision_time_ms == int(index[1].timestamp() * 1000) + 60_000
    assert events[0].reference_price == pytest.approx(101.0)
    assert events[0].long_entry is True


def test_funding_rows_preserve_exact_hour_oracle_and_rate() -> None:
    """Only nonzero venue settlements with causal oracle evidence are counted."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=3, freq="1h", tz="UTC")
    bars = pd.DataFrame(
        {"open": [100.0, 101.0, 102.0], "funding_rate": [0.0, 0.001, 0.0]},
        index=index,
    )

    settlement_ms = int(index[1].timestamp() * 1_000)
    oracle_prices = CausalOraclePriceSeries(
        pd.DataFrame({"ts_ms": [settlement_ms - 1_000], "oracle_price": [111.0]}),
        maximum_staleness_ms=120_000,
    )

    funding = module.to_event_funding(bars, oracle_prices)

    assert len(funding) == 1
    assert funding[0].timestamp_ms == int(index[1].timestamp() * 1000)
    assert funding[0].rate == pytest.approx(0.001)
    assert funding[0].reference_price == pytest.approx(111.0)


def test_cli_requires_database_and_chronological_boundaries() -> None:
    """Venue evidence and every evaluation boundary must be explicit."""
    module = _module()

    args = module.build_parser().parse_args(
        [
            "--symbol",
            "SOL",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--database",
            "market.duckdb",
            "--price-data-root",
            "data",
            "--development-start",
            "2025-07-28T00:00:00Z",
            "--development-end",
            "2026-01-28T00:00:00Z",
            "--validation-end",
            "2026-04-28T00:00:00Z",
            "--pseudo-holdout-end",
            "2026-07-28T00:00:00Z",
            "--output",
            "report.json",
        ]
    )

    assert args.database == Path("market.duckdb")
    assert args.price_data_root == Path("data")
    assert args.symbol == "SOL"
    assert args.surface == "standard"


def test_cli_accepts_capacity_trial_surface() -> None:
    """The capacity ladder must be an explicit reproducible CLI choice."""
    module = _module()

    args = module.build_parser().parse_args(
        [
            "--symbol",
            "SOL",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--database",
            "market.duckdb",
            "--development-start",
            "2025-07-28T00:00:00Z",
            "--development-end",
            "2026-01-28T00:00:00Z",
            "--validation-end",
            "2026-04-28T00:00:00Z",
            "--pseudo-holdout-end",
            "2026-07-28T00:00:00Z",
            "--surface",
            "capacity",
            "--output",
            "report.json",
        ]
    )

    assert args.surface == "capacity"


def test_cli_accepts_v49_target_exit_surface() -> None:
    """The target surface is explicit and cannot masquerade as preregistered."""
    module = _module()

    args = module.build_parser().parse_args(
        [
            "--symbol",
            "SOL",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--database",
            "market.duckdb",
            "--development-start",
            "2025-01-01T00:00:00Z",
            "--development-end",
            "2025-02-01T00:00:00Z",
            "--validation-end",
            "2025-03-01T00:00:00Z",
            "--pseudo-holdout-end",
            "2025-04-01T00:00:00Z",
            "--surface",
            "v49-target-exit-posthoc",
            "--output",
            "report.json",
        ]
    )

    assert args.surface == "v49-target-exit-posthoc"


def test_cli_accepts_capacity_shape_trial_surface() -> None:
    """The fixed-size stop comparison must be an explicit CLI choice."""
    module = _module()

    args = module.build_parser().parse_args(
        [
            "--symbol",
            "SOL",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--database",
            "market.duckdb",
            "--development-start",
            "2025-07-28T00:00:00Z",
            "--development-end",
            "2026-01-28T00:00:00Z",
            "--validation-end",
            "2026-04-28T00:00:00Z",
            "--pseudo-holdout-end",
            "2026-07-28T00:00:00Z",
            "--surface",
            "capacity-shape",
            "--output",
            "report.json",
        ]
    )

    assert args.surface == "capacity-shape"


def test_cli_labels_midpoint_trial_surface_as_posthoc() -> None:
    """The new midpoint must never be confused with a predeclared surface."""
    module = _module()

    args = module.build_parser().parse_args(
        [
            "--symbol",
            "SOL",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--database",
            "market.duckdb",
            "--development-start",
            "2025-07-28T00:00:00Z",
            "--development-end",
            "2026-01-28T00:00:00Z",
            "--validation-end",
            "2026-04-28T00:00:00Z",
            "--pseudo-holdout-end",
            "2026-07-28T00:00:00Z",
            "--surface",
            "capacity-shape-midpoint-posthoc",
            "--output",
            "report.json",
        ]
    )

    assert args.surface == "capacity-shape-midpoint-posthoc"


def test_cli_accepts_explicit_signal_warmup_start() -> None:
    """Gap-safe blocks must be able to retain prior causal signal state."""
    module = _module()

    args = module.build_parser().parse_args(
        [
            "--symbol",
            "SOL",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--database",
            "market.duckdb",
            "--signal-warmup-start",
            "2026-04-29T00:00:00Z",
            "--development-start",
            "2026-05-01T00:00:00Z",
            "--development-end",
            "2026-05-03T00:00:00Z",
            "--validation-end",
            "2026-05-05T00:00:00Z",
            "--pseudo-holdout-end",
            "2026-05-07T00:00:00Z",
            "--output",
            "report.json",
        ]
    )

    assert args.signal_warmup_start == module._utc_datetime("2026-04-29T00:00:00Z")


def test_cli_accepts_explicit_hourly_mark_partitioning() -> None:
    """Older hourly mark bundles must be selected without implicit fallback."""
    module = _module()

    args = module.build_parser().parse_args(
        [
            "--symbol",
            "SOL",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--database",
            "market.duckdb",
            "--price-chunk-hours",
            "1",
            "--development-start",
            "2025-03-01T00:00:00Z",
            "--development-end",
            "2025-03-02T00:00:00Z",
            "--validation-end",
            "2025-03-03T00:00:00Z",
            "--pseudo-holdout-end",
            "2025-03-04T00:00:00Z",
            "--output",
            "report.json",
        ]
    )

    assert args.price_chunk_hours == 1


def test_sampled_mark_adapter_preserves_mark_crossing_time() -> None:
    """The mark-bound challenger must expose the sampled venue timestamp."""
    module = _module()
    marks = SampledMarkSeries(
        pd.DataFrame(
            {"ts_ms": [1_000, 2_000, 3_000], "mark_price": [100.0, 99.0, 98.0]}
        ),
        maximum_gap_ms=1_000,
    )

    crossing = module._SampledMarkStop(marks).stop_crossing("long", 99.5, 1_000, 3_001)

    assert crossing == 2_000


def test_mark_context_loads_enclosing_utc_day_partitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Intraday replay bounds must map to the UTC-day archive partitioning."""
    module = _module()
    observed: dict[str, object] = {}
    frame = pd.DataFrame(
        {
            "ts_ms": [0, 60_000, 600_000, 660_000],
            "mark_price": [100.0, 101.0, 99.0, 98.0],
            "oracle_price": [100.0, 101.0, 99.0, 98.0],
        }
    )

    def load_archive(config: object) -> SimpleNamespace:
        observed["config"] = config
        return SimpleNamespace(
            frame=frame,
            partition_count=6,
            row_count=4,
            maximum_observed_gap_ms=540_000,
        )

    monkeypatch.setattr(module, "load_verified_price_archive", load_archive)
    start = module._utc_datetime("2026-05-23T08:00:00Z")
    end = module._utc_datetime("2026-05-27T21:00:00Z")

    context = module._mark_context(Path("data"), "SOL", start, end)

    assert context is not None
    config = observed["config"]
    assert config.start == module._utc_datetime("2026-05-23T00:00:00Z")
    assert config.end == module._utc_datetime("2026-05-28T00:00:00Z")
    assert config.maximum_gap.total_seconds() == 86_400
    marks, _oracle_prices, _evidence = context
    assert len(marks.observations(0, 60_001)) == 2
    with pytest.raises(ValueError, match="query gap"):
        marks.observations(0, 660_001)


def test_mark_context_can_load_explicit_hourly_partitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The historical backfill cadence must reach the archive loader unchanged."""
    module = _module()
    observed: dict[str, object] = {}

    def load_archive(config: object) -> SimpleNamespace:
        observed["chunk"] = config.chunk
        return SimpleNamespace(
            frame=pd.DataFrame(
                {
                    "ts_ms": [0, 60_000],
                    "mark_price": [100.0, 101.0],
                    "oracle_price": [100.0, 101.0],
                }
            ),
            partition_count=1,
            row_count=2,
            maximum_observed_gap_ms=60_000,
        )

    monkeypatch.setattr(module, "load_verified_price_archive", load_archive)
    start = module._utc_datetime("2025-03-02T06:00:00Z")
    end = module._utc_datetime("2025-03-02T07:00:00Z")

    context = module._mark_context(Path("data"), "SOL", start, end, 1)

    assert context is not None
    assert observed["chunk"].total_seconds() == 3_600


def test_run_surface_passes_each_segment_boundary_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Top-level orchestration must call the mark surface with four boundaries."""
    module = _module()
    start = module._utc_datetime("2025-07-28T00:00:00Z")
    development_end = module._utc_datetime("2026-01-28T00:00:00Z")
    validation_end = module._utc_datetime("2026-04-28T00:00:00Z")
    holdout_end = module._utc_datetime("2026-07-28T00:00:00Z")
    warmup_start = module._utc_datetime("2025-07-26T00:00:00Z")
    empty = pd.DataFrame()
    loaded: dict[str, object] = {}
    mark_loaded: dict[str, object] = {}
    connection = MagicMock()
    connection.__enter__.return_value = connection

    def load_window(
        _bars: Path,
        _funding: list[Path],
        start: object,
        end: object,
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        loaded.update(start=start, end=end)
        return empty, {}

    monkeypatch.setattr(module, "load_causal_window", load_window)
    monkeypatch.setattr(module, "build_range_onset_signals", lambda _bars: empty)
    monkeypatch.setattr(module, "to_event_signals", lambda *_args: ())
    monkeypatch.setattr(
        module,
        "to_event_funding",
        lambda _bars, _oracle, **_kwargs: (),
    )
    monkeypatch.setattr(module, "_coverage", lambda *_args: {})

    def mark_context(*args: object) -> None:
        mark_loaded.update(start=args[2], partition_hours=args[-1])
        return None

    monkeypatch.setattr(module, "_mark_context", mark_context)
    monkeypatch.setattr(module, "_segments", lambda *_args: {})
    monkeypatch.setattr(module.duckdb, "connect", lambda *_args, **_kwargs: connection)

    result = module.run_event_surface(
        symbol="SOL",
        bars_path=Path("bars.parquet"),
        funding_paths=[Path("funding.parquet")],
        database_path=Path("market.duckdb"),
        price_data_root=Path("data"),
        development_start=start,
        development_end=development_end,
        validation_end=validation_end,
        pseudo_holdout_end=holdout_end,
        signal_warmup_start=warmup_start,
        price_chunk_hours=1,
    )

    assert result["sampled_mark_surface"] is None
    assert result["signal_warmup_start_utc"] == warmup_start.isoformat()
    assert loaded == {"start": warmup_start, "end": holdout_end}
    assert mark_loaded == {"start": warmup_start, "partition_hours": 1}


def test_mark_segments_preserve_public_result_when_marks_are_censored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An active mark gap must become explicit evidence, not lose public replay."""
    module = _module()
    start = module._utc_datetime("2026-05-01T00:00:00Z")
    end = module._utc_datetime("2026-05-02T00:00:00Z")

    def fail_gap(*_args: object) -> dict[str, object]:
        raise module.MarkQueryGapError("mark query gap 166224ms exceeds 120000ms")

    monkeypatch.setattr(module, "_segments", fail_gap)
    context = (
        MagicMock(),
        MagicMock(),
        {"partition_count": 2, "row_count": 2_800},
    )

    result = module._mark_segments(
        (),
        (),
        MagicMock(),
        context,
        start,
        end,
        end,
        end,
        (),
    )

    assert result == {
        "price_archive": {"partition_count": 2, "row_count": 2_800},
        "mark_validation_status": "censored",
        "censor_reason": "mark query gap 166224ms exceeds 120000ms",
    }
