"""Contracts for historical Hypertrader label generation."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import importlib.util
from argparse import Namespace
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from hypervector.research.hypertrader_source_adapter import (
    LEGACY_HYPERTRADER_REVISION,
    LEGACY_SOURCE_HASHES,
    extract_selective_recipe_events,
    load_hyperliquid_candle_segments,
    verify_source_files,
)


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_hypertrader_labels.py")
    spec = importlib.util.spec_from_file_location("revision_labels_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Hypertrader labels script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_verifier_records_explicit_historical_revision(
    tmp_path: Path,
) -> None:
    source = tmp_path / "backend"
    target = source / "app" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("legacy\n")
    expected = {"app/example.py": hashlib.sha256(b"legacy\n").hexdigest()}

    evidence = verify_source_files(
        source,
        expected_hashes=expected,
        revision=LEGACY_HYPERTRADER_REVISION,
    )

    assert evidence["revision"] == LEGACY_HYPERTRADER_REVISION
    assert len(LEGACY_SOURCE_HASHES) >= 6


def test_label_script_accepts_canonical_database_and_historical_source() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--upstream-backend",
            "upstream/backend",
            "--source-revision",
            LEGACY_HYPERTRADER_REVISION,
            "--research-database",
            "data/research/market.duckdb",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-28T00:00:00Z",
            "--out",
            "labels.parquet",
            "--metadata-out",
            "labels.json",
        ]
    )

    assert args.source_revision == LEGACY_HYPERTRADER_REVISION
    assert args.research_database == Path("data/research/market.duckdb")
    assert args.bars is None


def test_label_script_accepts_exact_prior_label_checkpoint() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--upstream-backend",
            "upstream/backend",
            "--research-database",
            "data/research/market.duckdb",
            "--prior-labels",
            "prior.parquet",
            "--start",
            "2026-07-30T05:30:00Z",
            "--end",
            "2026-07-30T08:30:00Z",
            "--out",
            "labels.parquet",
            "--metadata-out",
            "labels.json",
        ]
    )

    assert args.prior_labels == Path("prior.parquet")


def test_label_script_accepts_explicit_gap_reset_policy() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--upstream-backend",
            "upstream/backend",
            "--bars",
            "native-candles.parquet",
            "--reset-at-gaps",
            "--out",
            "labels.parquet",
            "--metadata-out",
            "labels.json",
        ]
    )

    assert args.reset_at_gaps is True


def test_gap_reset_policy_accepts_exact_candle_window(tmp_path: Path) -> None:
    """Segmented labels must clip source candles to registered window bounds."""
    module = _load_script()
    timestamps = pd.date_range("2025-04-24T23:55:00Z", periods=20, freq="1min")
    path = tmp_path / "native-candles.parquet"
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl_native_candle",
        }
    ).to_parquet(path, index=False)
    args = Namespace(
        research_database=None,
        prior_labels=None,
        start=datetime(2025, 4, 25, tzinfo=UTC),
        end=datetime(2025, 4, 25, 0, 10, tzinfo=UTC),
        bars=[path],
    )

    segments, _ = module._segmented_input(args)

    assert len(segments) == 1
    assert segments[0].index.tolist() == [
        pd.Timestamp("2025-04-25T00:00:00Z"),
        pd.Timestamp("2025-04-25T00:05:00Z"),
    ]


def test_gap_reset_policy_rejects_unaligned_window() -> None:
    """A partial five-minute boundary must fail instead of changing OHLCV."""
    module = _load_script()
    args = Namespace(
        research_database=None,
        prior_labels=None,
        start=datetime(2025, 4, 25, 0, 1, tzinfo=UTC),
        end=datetime(2025, 4, 25, 0, 10, tzinfo=UTC),
        bars=[Path("unused.parquet")],
    )

    with pytest.raises(ValueError, match="five-minute aligned"):
        module._segmented_input(args)


def test_segmented_candle_loader_discards_partial_five_minute_edges(
    tmp_path: Path,
) -> None:
    first = pd.date_range("2025-05-01T00:01:00Z", periods=9, freq="1min")
    second = pd.date_range("2025-05-01T00:15:00Z", periods=10, freq="1min")
    timestamps = first.append(second)
    candles = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl_native_candle",
        }
    )
    path = tmp_path / "gapped.parquet"
    candles.to_parquet(path, index=False)

    segments = load_hyperliquid_candle_segments([path])

    assert len(segments) == 2
    assert segments[0].index[0] == pd.Timestamp("2025-05-01T00:05:00Z")
    assert segments[0].index[-1] == pd.Timestamp("2025-05-01T00:09:00Z")
    assert len(segments[0]) == 5
    assert segments[1].index[0] == pd.Timestamp("2025-05-01T00:15:00Z")
    assert segments[1].index[-1] == pd.Timestamp("2025-05-01T00:24:00Z")
    assert len(segments[1]) == 10


def test_checkpoint_reconstructs_current_pending_and_duration_state() -> None:
    module = _load_script()
    seed = getattr(module, "_seed_state", None)
    assert seed is not None
    index = pd.date_range("2026-07-30", periods=6, freq="5min", tz="UTC")
    labels = _checkpoint_labels(
        index,
        ["RANGE", "RANGE", "TREND_DOWN", "TREND_DOWN", "TREND_DOWN", "TREND_DOWN"],
        ["RANGE", "RANGE", "TREND_DOWN", "TREND_DOWN", "TREND_UP", "TREND_UP"],
    )
    state = SimpleNamespace()
    config = SimpleNamespace(
        min_duration_bars=5,
        breakout_ttl_bars=10,
        breakout_cooldown_bars=15,
    )

    seed(
        state,
        labels,
        config,
        lambda **values: SimpleNamespace(**values),
        str,
        index[-1] + pd.Timedelta(minutes=5),
    )

    assert state.current.primary == "TREND_DOWN"
    assert state.pending.primary == "TREND_UP"
    assert state.pending_count == 2
    expected = index[2].timestamp() * 1_000 + 5 * 300_000
    assert state.transition_blocked_until == expected


def test_checkpoint_rejects_active_breakout_cooldown() -> None:
    module = _load_script()
    seed = getattr(module, "_seed_state", None)
    assert seed is not None
    index = pd.date_range("2026-07-30", periods=5, freq="5min", tz="UTC")
    labels = _checkpoint_labels(
        index,
        ["RANGE", "BREAKOUT", "BREAKOUT", "RANGE", "RANGE"],
        ["RANGE", "BREAKOUT", "BREAKOUT", "RANGE", "RANGE"],
    )
    config = SimpleNamespace(
        min_duration_bars=5,
        breakout_ttl_bars=10,
        breakout_cooldown_bars=15,
    )

    with pytest.raises(ValueError, match="breakout cooldown"):
        seed(
            SimpleNamespace(),
            labels,
            config,
            lambda **values: SimpleNamespace(**values),
            str,
            index[-1] + pd.Timedelta(minutes=5),
        )


def _checkpoint_labels(
    index: pd.DatetimeIndex,
    confirmed: list[str],
    raw: list[str],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "available_at": index + pd.Timedelta(minutes=5),
            "primary_code": confirmed,
            "secondary_code": [None] * len(index),
            "confidence": [0.8] * len(index),
            "raw_primary_code": raw,
            "raw_secondary_code": [None] * len(index),
            "raw_confidence": [0.8] * len(index),
            "volume_ratio": [1.0] * len(index),
        },
        index=index,
    )


def _unknown_labels() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "primary_code": ["UNKNOWN", "RANGE"],
            "secondary_code": [None, None],
            "confidence": [0.0, 0.5],
        },
        index=pd.date_range("2026-07-29", periods=2, freq="5min", tz="UTC"),
    )


def test_selective_recipe_empty_window_preserves_event_schema() -> None:
    events = extract_selective_recipe_events(_unknown_labels())

    assert events.empty
    assert events.columns.tolist() == [
        "recipe_id",
        "label_time_utc",
        "decision_time_utc",
        "side",
        "maximum_hold_seconds",
        "confidence",
    ]


def test_label_publication_does_not_leave_parquet_after_validation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    output = tmp_path / "labels.parquet"
    metadata = tmp_path / "labels.json"
    args = Namespace(out=output, metadata_out=metadata)

    def _fail(_: pd.DataFrame) -> pd.DataFrame:
        raise ValueError("invalid event extraction")

    monkeypatch.setattr(module, "extract_selective_recipe_events", _fail)
    with pytest.raises(ValueError, match="invalid event extraction"):
        module._write_outputs(
            args,
            _unknown_labels(),
            {"revision": LEGACY_HYPERTRADER_REVISION},
            [],
        )

    assert not output.exists()
    assert not metadata.exists()


def test_label_publication_rolls_back_parquet_if_metadata_publish_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    output = tmp_path / "labels.parquet"
    metadata = tmp_path / "labels.json"
    args = Namespace(out=output, metadata_out=metadata)

    def _fail(_: Path, __: object) -> None:
        raise OSError("metadata publish failed")

    monkeypatch.setattr(module, "write_immutable_json", _fail)
    with pytest.raises(OSError, match="metadata publish failed"):
        module._write_outputs(
            args,
            _unknown_labels(),
            {"revision": LEGACY_HYPERTRADER_REVISION},
            [],
        )

    assert not output.exists()
    assert not metadata.exists()
