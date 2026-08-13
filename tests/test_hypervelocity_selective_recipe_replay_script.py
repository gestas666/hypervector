"""Contracts for pinned Hypertrader-v2 regime extraction and recipe events."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research import hypertrader_source_adapter
from hypervector.research.hypertrader_source_adapter import (
    PINNED_HYPERTRADER_REVISION,
    PINNED_SOURCE_HASHES,
    annotate_signal_range_eligibility,
    extract_selective_recipe_events,
    resample_hyperliquid_5m,
    selective_recipe_maker_decisions,
    trend_aligned_selective_recipe_events,
    verify_source_files,
)
from hypervector.research.maker_replay_signals import (
    available_directions,
    available_maximum_holds,
)
from hypervector.research.maker_replay import replay_maker_orders
from hypervector.research.maker_replay_models import MakerReplayConfig


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_hypertrader_labels.py")
    spec = importlib.util.spec_from_file_location("hypertrader_labels_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Hypertrader labels script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_source_files_accepts_exact_hashes(tmp_path: Path) -> None:
    source = tmp_path / "backend"
    target = source / "app" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("frozen\n")
    expected = {"app/example.py": hashlib.sha256(b"frozen\n").hexdigest()}

    evidence = verify_source_files(source, expected_hashes=expected)

    assert evidence == {
        "revision": PINNED_HYPERTRADER_REVISION,
        "files": {"app/example.py": expected["app/example.py"]},
    }


def test_pinned_source_boundary_includes_recipe_and_backtest_contract() -> None:
    assert "app/services/regime/classif_dry_run.py" in PINNED_SOURCE_HASHES
    assert "scripts/run_classif_dry_run_backtest.py" in PINNED_SOURCE_HASHES


def test_empty_selective_recipe_decisions_keep_utc_index_contract() -> None:
    events = pd.DataFrame(
        columns=[
            "recipe_id",
            "label_time_utc",
            "decision_time_utc",
            "side",
            "maximum_hold_seconds",
        ]
    )

    decisions = selective_recipe_maker_decisions(events)

    assert isinstance(decisions.index, pd.DatetimeIndex)
    assert str(decisions.index.tz) == "UTC"
    assert decisions.index.empty
    assert decisions.columns.tolist() == [
        "recipe_id",
        "label_time_utc",
        "entry_direction",
        "structural_direction",
        "maximum_hold_seconds",
    ]


def test_verify_source_files_fails_on_revision_drift(tmp_path: Path) -> None:
    source = tmp_path / "backend"
    target = source / "app" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("changed\n")

    with pytest.raises(ValueError, match="source checksum mismatch"):
        verify_source_files(
            source,
            expected_hashes={"app/example.py": hashlib.sha256(b"frozen\n").hexdigest()},
        )


def test_resample_hyperliquid_5m_uses_completed_one_minute_bars() -> None:
    index = pd.date_range("2026-07-27T00:00:00Z", periods=10, freq="1min")
    candles = pd.DataFrame(
        {
            "open": range(100, 110),
            "high": range(101, 111),
            "low": range(99, 109),
            "close": range(100, 110),
            "volume": [1.0] * 10,
        },
        index=index,
    )

    bars = resample_hyperliquid_5m(candles)

    assert list(bars.index) == [index[0], index[5]]
    assert bars.loc[index[0]].to_dict() == {
        "open": 100.0,
        "high": 105.0,
        "low": 99.0,
        "close": 104.0,
        "volume": 5.0,
    }


def test_extract_selective_events_matches_exact_source_onsets_and_causal_time() -> None:
    index = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-27T07:50:00Z",
                "2026-07-27T07:55:00Z",
                "2026-07-27T08:00:00Z",
                "2026-07-27T08:05:00Z",
                "2026-07-27T09:00:00Z",
                "2026-07-27T09:05:00Z",
            ],
            utc=True,
        )
    )
    labels = pd.DataFrame(
        {
            "primary_code": [
                "RANGE",
                "BREAKOUT",
                "BREAKOUT",
                "RANGE",
                "TREND_DOWN",
                "TREND_DOWN",
            ],
            "secondary_code": [None, "BK_UPWARD", "BK_UPWARD", None, None, None],
            "confidence": [0.8, 0.7, 0.9, 0.5, 0.4, 0.8],
        },
        index=index,
    )

    events = extract_selective_recipe_events(labels)

    assert events["recipe_id"].tolist() == ["bk_up_asia_conf06", "fade_td_eu"]
    assert events["label_time_utc"].tolist() == [index[1], index[4]]
    assert events["decision_time_utc"].tolist() == [
        index[1] + pd.Timedelta(minutes=5),
        index[4] + pd.Timedelta(minutes=5),
    ]
    assert events["maximum_hold_seconds"].tolist() == [14_400.0, 86_400.0]
    assert events["side"].tolist() == ["long", "long"]


def _symmetric_source_labels() -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    index = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-27T00:00:00Z",
                "2026-07-27T00:05:00Z",
                "2026-07-27T06:55:00Z",
                "2026-07-27T07:00:00Z",
                "2026-07-27T07:05:00Z",
                "2026-07-27T08:00:00Z",
                "2026-07-27T08:05:00Z",
                "2026-07-27T15:55:00Z",
                "2026-07-27T16:00:00Z",
            ],
            utc=True,
        )
    )
    labels = pd.DataFrame(
        {
            "primary_code": [
                "RANGE",
                "BREAKOUT",
                "RANGE",
                "TREND_UP",
                "TREND_UP",
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_UP",
            ],
            "secondary_code": [
                None,
                "BK_UPWARD",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ],
            "confidence": [0.8, 0.7, 0.5, 0.65, 0.9, 0.5, 0.75, 0.5, 0.95],
        },
        index=index,
    )
    return labels, index


def test_symmetric_trend_events_add_only_eu_trend_up_and_down_onsets() -> None:
    labels, index = _symmetric_source_labels()

    events = hypertrader_source_adapter.extract_symmetric_trend_events(labels)

    assert events["recipe_id"].tolist() == [
        "bk_up_asia_conf06",
        "follow_tu_eu",
        "follow_td_eu",
    ]
    assert events["label_time_utc"].tolist() == [index[1], index[3], index[6]]
    assert events["decision_time_utc"].tolist() == [
        index[1] + pd.Timedelta(minutes=5),
        index[3] + pd.Timedelta(minutes=5),
        index[6] + pd.Timedelta(minutes=5),
    ]
    assert events["side"].tolist() == ["long", "long", "short"]
    assert events["maximum_hold_seconds"].tolist() == [
        14_400.0,
        86_400.0,
        86_400.0,
    ]


def test_four_hour_long_events_change_only_eu_trend_up_hold() -> None:
    index = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-27T00:00:00Z",
                "2026-07-27T00:05:00Z",
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
            "primary_code": [
                "RANGE",
                "BREAKOUT",
                "RANGE",
                "TREND_UP",
                "RANGE",
                "TREND_DOWN",
            ],
            "secondary_code": [None, "BK_UPWARD", None, None, None, None],
            "confidence": [0.5, 0.7, 0.5, 0.8, 0.5, 0.9],
        },
        index=index,
    )

    control = hypertrader_source_adapter.extract_symmetric_trend_events(labels)
    candidate = hypertrader_source_adapter.extract_four_hour_long_trend_events(labels)

    unchanged = [column for column in control if column != "maximum_hold_seconds"]
    pd.testing.assert_frame_equal(candidate[unchanged], control[unchanged])
    assert candidate["maximum_hold_seconds"].tolist() == [
        14_400.0,
        14_400.0,
        86_400.0,
    ]


def test_source_fade_events_exclude_but_do_not_modify_recipe_b() -> None:
    index = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2026-07-27T00:00:00Z",
                "2026-07-27T00:05:00Z",
                "2026-07-27T07:00:00Z",
                "2026-07-27T07:05:00Z",
            ],
            utc=True,
        )
    )
    labels = pd.DataFrame(
        {
            "primary_code": ["RANGE", "BREAKOUT", "RANGE", "TREND_DOWN"],
            "secondary_code": [None, "BK_UPWARD", None, None],
            "confidence": [0.5, 0.7, 0.5, 0.85],
        },
        index=index,
    )

    control = hypertrader_source_adapter.extract_selective_recipe_events(labels)
    candidate = hypertrader_source_adapter.extract_source_fade_events(labels)

    expected = control.loc[control["recipe_id"].eq("fade_td_eu")].reset_index(drop=True)
    pd.testing.assert_frame_equal(candidate, expected)


def test_maker_decisions_submit_at_causal_close_with_recipe_deadline() -> None:
    decision_time = pd.Timestamp("2026-07-27T14:55:00Z")
    events = pd.DataFrame(
        [
            {
                "recipe_id": "fade_td_eu",
                "label_time_utc": decision_time - pd.Timedelta(minutes=5),
                "decision_time_utc": decision_time,
                "side": "long",
                "maximum_hold_seconds": 86_400.0,
                "confidence": 0.85,
            }
        ]
    )

    decisions = selective_recipe_maker_decisions(events)
    available = available_directions(decisions)
    maximum_holds = available_maximum_holds(decisions)

    assert list(available.index) == [
        decision_time - pd.Timedelta(seconds=5),
        decision_time,
        decision_time + pd.Timedelta(minutes=5),
    ]
    assert available.tolist() == [None, "long", None]
    assert maximum_holds.tolist() == [None, 86_400.0, None]


def test_signal_range_annotation_blocks_only_explicit_shock_candidate() -> None:
    index = pd.date_range("2026-07-27T10:00:00Z", periods=2, freq="10min")
    events = pd.DataFrame(
        {
            "recipe_id": ["follow_td_eu", "follow_td_eu"],
            "label_time_utc": index,
            "decision_time_utc": index + pd.Timedelta(minutes=5),
            "side": ["short", "short"],
            "maximum_hold_seconds": [86_400.0, 86_400.0],
        }
    )
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [100.4, 100.8],
            "low": [99.9, 99.7],
            "close": [100.1, 99.9],
            "volume": [1.0, 1.0],
        },
        index=index,
    )

    annotated = annotate_signal_range_eligibility(
        events,
        bars,
        maximum_range_bps=100.0,
    )
    decisions = selective_recipe_maker_decisions(annotated)
    available = available_directions(decisions)

    assert annotated["signal_range_bps"].tolist() == pytest.approx([50.0, 110.0])
    assert annotated["entry_eligible"].tolist() == [True, False]
    assert annotated["entry_exclusion_reason"].tolist() == [None, "signal_range"]
    assert available.loc[index[0] + pd.Timedelta(minutes=5)] == "short"
    assert pd.isna(available.loc[index[1] + pd.Timedelta(minutes=5)])


def test_recipe_c_range_split_selects_direction_without_filtering() -> None:
    index = pd.date_range("2026-07-27T10:00:00Z", periods=2, freq="10min")
    events = pd.DataFrame(
        {
            "recipe_id": ["fade_td_eu", "fade_td_eu"],
            "label_time_utc": index,
            "decision_time_utc": index + pd.Timedelta(minutes=5),
            "side": ["long", "long"],
            "maximum_hold_seconds": [86_400.0, 86_400.0],
        }
    )
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [100.7, 100.8],
            "low": [99.7, 99.7],
            "close": [99.8, 99.9],
            "volume": [1.0, 1.0],
        },
        index=index,
    )

    selected = hypertrader_source_adapter.range_split_recipe_c_events(
        events,
        bars,
        split_bps=100.0,
    )

    assert selected["signal_range_bps"].tolist() == pytest.approx([100.0, 110.0])
    assert selected["recipe_id"].tolist() == ["follow_td_eu", "fade_td_eu"]
    assert selected["side"].tolist() == ["short", "long"]
    assert selected["entry_eligible"].tolist() == [True, True]
    assert selected["entry_exclusion_reason"].isna().all()
    assert events["side"].tolist() == ["long", "long"]


def test_trend_aligned_variant_flips_only_trend_down_fade_direction() -> None:
    events = pd.DataFrame(
        [
            {
                "recipe_id": "bk_up_asia_conf06",
                "side": "long",
                "maximum_hold_seconds": 14_400.0,
            },
            {
                "recipe_id": "fade_td_eu",
                "side": "long",
                "maximum_hold_seconds": 86_400.0,
            },
        ]
    )

    aligned = trend_aligned_selective_recipe_events(events)

    assert aligned["recipe_id"].tolist() == [
        "bk_up_asia_conf06",
        "follow_td_eu",
    ]
    assert aligned["side"].tolist() == ["long", "short"]
    assert aligned["maximum_hold_seconds"].tolist() == [14_400.0, 86_400.0]
    assert events.loc[1, "recipe_id"] == "fade_td_eu"
    assert events.loc[1, "side"] == "long"


def test_occupied_position_does_not_submit_an_expired_onset_later() -> None:
    origin = pd.Timestamp("2026-07-27T00:00:00Z")
    events = pd.DataFrame(
        [
            {
                "recipe_id": "first",
                "label_time_utc": origin,
                "decision_time_utc": origin + pd.Timedelta(minutes=1),
                "side": "long",
                "maximum_hold_seconds": 3_600.0,
            },
            {
                "recipe_id": "second",
                "label_time_utc": origin + pd.Timedelta(minutes=1),
                "decision_time_utc": origin + pd.Timedelta(minutes=2),
                "side": "short",
                "maximum_hold_seconds": 3_600.0,
            },
        ]
    )
    seconds = (60, 70, 120, 420, 480)
    book = pd.DataFrame(
        {
            "ts_ms": [
                int((origin + pd.Timedelta(seconds=value)).timestamp() * 1_000)
                for value in seconds
            ],
            "best_bid": (100.0, 99.0, 99.0, 99.0, 100.2),
            "best_ask": (101.0, 100.0, 100.0, 100.0, 100.3),
        }
    )

    report = replay_maker_orders(
        book,
        selective_recipe_maker_decisions(events),
        MakerReplayConfig(maker_fee_rate=0.0, fill_rule="touch"),
    )

    assert report.completed_trades == 1
    assert report.submitted_entries == 1
    assert (
        report.lifecycles[0].signal_time_utc
        == (origin + pd.Timedelta(minutes=1)).isoformat()
    )


def test_script_contract_is_report_only_and_requires_pinned_source() -> None:
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--upstream-backend",
            "upstream/backend",
            "--bars",
            "older.parquet",
            "--bars",
            "fresh.parquet",
            "--out",
            "labels.parquet",
            "--metadata-out",
            "labels.json",
        ]
    )
    contract = module._experiment_contract()

    assert args.bars == [Path("older.parquet"), Path("fresh.parquet")]
    assert args.upstream_backend == Path("upstream/backend")
    assert contract["upstream_revision"] == PINNED_HYPERTRADER_REVISION
    assert contract["report_only"] is True
    assert contract["runtime_strategy_changed"] is False
    assert contract["decision_delay_seconds"] == 300
    assert contract["model_authority"] == "observe"
