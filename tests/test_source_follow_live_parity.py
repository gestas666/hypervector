"""Live-ledger parity tests for the source-follow shadow candidate."""

from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.source_follow_live_parity import (
    SourceFollowParityPolicy,
    assemble_source_follow_live_candles,
    audit_source_follow_live_rows,
)


_PROFILE_ID = "hypervelocity_source_follow_minrange12_alloc35_shadow_v1"


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_live_runtime_parity.py")
    spec = importlib.util.spec_from_file_location("source_live_runtime_parity", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"live parity script could not load: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_candle_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_live_candles.py")
    spec = importlib.util.spec_from_file_location("source_live_candles", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"live candle script could not load: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _labels() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "primary_code": ["RANGE", "TREND_DOWN"],
            "secondary_code": [None, "BREAKOUT"],
            "confidence": [0.5, 0.9],
        },
        index=pd.DatetimeIndex(
            [
                datetime(2026, 7, 30, 10, 30, tzinfo=UTC),
                datetime(2026, 7, 30, 10, 35, tzinfo=UTC),
            ]
        ),
    )


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [100.1, 100.12],
            "low": [99.9, 99.92],
            "close": [100.0, 100.0],
            "volume": [10.0, 12.0],
        },
        index=_labels().index,
    )


def _row(feed_ts: str, *, direction: str | None) -> dict[str, object]:
    return {
        "action": "regime_observation",
        "profile_id": _PROFILE_ID,
        "feed_ts": feed_ts,
        "primary_regime": "TREND_DOWN",
        "state_5m": "TREND_DOWN",
        "confidence": 0.9,
        "regime_reason": "source_follow_entry_pulse",
        "source_follow_label_time_utc": "2026-07-30T10:35:00+00:00",
        "source_follow_available_at_utc": "2026-07-30T10:40:00+00:00",
        "source_follow_signal_range_bps": 20.0,
        "entry_direction": direction,
        "structural_direction": direction,
        "entry_allowed": direction is not None,
        "submitted": False,
        "place_attempted": False,
    }


def test_live_parity_matches_label_and_exact_entry_pulse_boundary() -> None:
    """The label persists after its one-minute execution pulse expires."""
    rows = [
        _row("2026-07-30T10:40:00+00:00", direction="short"),
        _row("2026-07-30T10:41:00+00:00", direction=None),
    ]

    report = audit_source_follow_live_rows(
        rows,
        _labels(),
        _bars(),
        SourceFollowParityPolicy(profile_id=_PROFILE_ID),
    )

    assert report["exact"] is True
    assert report["observations"] == 2
    assert report["covered_observations"] == 2
    assert report["mismatch_count"] == 0
    assert report["uncovered_count"] == 0
    assert report["submitted_true"] == 0


def test_live_parity_exposes_mismatch_and_missing_offline_evidence() -> None:
    """Wrong pulse state and an unseen label cannot be success-shaped parity."""
    wrong = _row("2026-07-30T10:40:00+00:00", direction=None)
    uncovered = _row("2026-07-30T10:45:00+00:00", direction=None)
    uncovered["source_follow_label_time_utc"] = "2026-07-30T10:40:00+00:00"
    uncovered["source_follow_available_at_utc"] = "2026-07-30T10:45:00+00:00"

    report = audit_source_follow_live_rows(
        [wrong, uncovered],
        _labels(),
        _bars(),
        SourceFollowParityPolicy(profile_id=_PROFILE_ID),
    )

    assert report["exact"] is False
    assert report["covered_observations"] == 1
    assert report["mismatch_count"] == 1
    assert report["mismatches"][0]["fields"]["entry_direction"] == {
        "expected": "short",
        "actual": None,
    }
    assert report["uncovered_count"] == 1
    assert report["uncovered"][0]["label_time_utc"] == ("2026-07-30T10:40:00+00:00")


def test_live_parity_requires_matching_profile_observations() -> None:
    """An empty or wrong-profile ledger is not evidence of parity."""
    report = audit_source_follow_live_rows(
        [{"action": "regime_observation", "profile_id": "different"}],
        _labels(),
        _bars(),
        SourceFollowParityPolicy(profile_id=_PROFILE_ID),
    )

    assert report["exact"] is False
    assert report["observations"] == 0
    assert report["failure_reason"] == "no_matching_regime_observations"


def test_live_parity_command_is_read_only_and_time_bounded() -> None:
    """The operator command carries evidence paths but no execution authority."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--profile",
            "candidate.toml",
            "--decisions",
            "decisions.jsonl",
            "--labels",
            "labels.parquet",
            "--labels-metadata",
            "labels.json",
            "--database",
            "market.duckdb",
            "--start",
            "2026-07-30T10:40:00Z",
            "--end",
            "2026-07-30T10:50:00Z",
            "--out",
            "parity.json",
        ]
    )

    assert args.profile == Path("candidate.toml")
    assert args.start == datetime(2026, 7, 30, 10, 40, tzinfo=UTC)
    assert args.end == datetime(2026, 7, 30, 10, 50, tzinfo=UTC)
    assert module._experiment_contract() == {
        "report_only": True,
        "runtime_strategy_changed": False,
        "execution_authority": "none",
    }


def test_live_parity_command_accepts_exact_rest_candle_evidence() -> None:
    """REST-candle parity can use the same venue input family as live runtime."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--profile",
            "candidate.toml",
            "--decisions",
            "decisions.jsonl",
            "--labels",
            "labels.parquet",
            "--labels-metadata",
            "labels.json",
            "--bars",
            "warmup.parquet",
            "--out",
            "parity.json",
        ]
    )

    assert args.database is None
    assert args.bars == [Path("warmup.parquet")]


def test_live_candle_assembly_publishes_only_complete_five_minute_groups() -> None:
    """Ledger bars extend warm-up exactly while the forming group stays out."""
    timestamps = pd.date_range("2026-07-30T10:55:00Z", periods=10, freq="1min")
    warmup = pd.DataFrame(
        {
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
            "volume": [1.0] * 10,
            "source": ["hl"] * 10,
        },
        index=timestamps,
    )
    rows = [_ledger_bar(minute) for minute in range(5, 12)]

    assembly = assemble_source_follow_live_candles(warmup, rows, _PROFILE_ID)

    assert len(assembly.candles) == 15
    assert assembly.candles.index[-1] == pd.Timestamp("2026-07-30T11:09:00Z")
    assert assembly.candles.iloc[-1]["close"] == 100.5
    assert assembly.appended_rows == 5
    assert assembly.trailing_rows_discarded == 2


def test_live_candle_assembly_fails_on_missing_backend_minute() -> None:
    """A missing live minute cannot be hidden inside a complete source bar."""
    timestamps = pd.date_range("2026-07-30T11:00:00Z", periods=5, freq="1min")
    warmup = pd.DataFrame(
        {
            "open": [100.0] * 5,
            "high": [101.0] * 5,
            "low": [99.0] * 5,
            "close": [100.0] * 5,
            "volume": [1.0] * 5,
        },
        index=timestamps,
    )

    with pytest.raises(ValueError, match="contiguous one-minute candles"):
        assemble_source_follow_live_candles(
            warmup,
            [_ledger_bar(5), _ledger_bar(7)],
            _PROFILE_ID,
        )


def test_live_candle_command_is_read_only_evidence_assembly() -> None:
    """Candle publication carries no strategy or execution authority."""
    module = _load_candle_script()
    args = module._parser().parse_args(
        [
            "--profile",
            "candidate.toml",
            "--warmup-bars",
            "warmup.parquet",
            "--decisions",
            "decisions.jsonl",
            "--out",
            "extended.parquet",
            "--metadata-out",
            "extended.json",
        ]
    )

    assert args.profile == Path("candidate.toml")
    assert args.warmup_bars == Path("warmup.parquet")
    assert module._experiment_contract() == {
        "report_only": True,
        "runtime_strategy_changed": False,
        "execution_authority": "none",
    }


def _ledger_bar(minute: int) -> dict[str, object]:
    opened = pd.Timestamp("2026-07-30T11:00:00Z") + pd.Timedelta(minutes=minute)
    return {
        "action": "regime_observation",
        "profile_id": _PROFILE_ID,
        "feed_ts": (opened + pd.Timedelta(minutes=1)).isoformat(),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "mark_px": 100.5,
        "volume": 2.0,
    }
