"""Clock-boundary sensitivity contracts for source-follow confidence events."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd

from hypervector.research import hypertrader_source_confidence


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_hypertrader_maker_replay.py")
    spec = importlib.util.spec_from_file_location("session_sensitivity_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load maker replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hourly_onset_labels() -> pd.DataFrame:
    index = pd.date_range("2026-01-01T04:55:00Z", "2026-01-01T17:05:00Z", freq="5min")
    labels = pd.DataFrame(
        {
            "primary_code": "RANGE",
            "secondary_code": None,
            "confidence": 0.5,
        },
        index=index,
    )
    event_times = [
        pd.Timestamp(f"2026-01-01T{hour:02d}:00:00Z") for hour in range(5, 18)
    ]
    labels.loc[event_times, "primary_code"] = "TREND_DOWN"
    labels.loc[event_times, "confidence"] = 0.8
    return labels


def test_neighboring_confidence_sessions_use_exact_half_open_hours() -> None:
    labels = _hourly_onset_labels()

    windows = {
        "05_14": hypertrader_source_confidence.extract_source_follow_session_05_14_confidence_70_events(
            labels
        ),
        "07_16": hypertrader_source_confidence.extract_source_follow_session_07_16_confidence_70_events(
            labels
        ),
        "08_17": hypertrader_source_confidence.extract_source_follow_session_08_17_confidence_70_events(
            labels
        ),
    }

    assert [stamp.hour for stamp in windows["05_14"]["label_time_utc"]] == list(
        range(5, 14)
    )
    assert [stamp.hour for stamp in windows["07_16"]["label_time_utc"]] == list(
        range(7, 16)
    )
    assert [stamp.hour for stamp in windows["08_17"]["label_time_utc"]] == list(
        range(8, 17)
    )
    assert windows["05_14"]["recipe_id"].eq("follow_td_session_05_14_conf70").all()
    assert windows["07_16"]["recipe_id"].eq("follow_td_session_07_16_conf70").all()
    assert windows["08_17"]["recipe_id"].eq("follow_td_session_08_17_conf70").all()


def test_neighboring_confidence_sessions_are_report_only_replay_families(
    tmp_path: Path,
) -> None:
    module = _load_script()
    labels_path = tmp_path / "labels.parquet"
    _hourly_onset_labels().to_parquet(labels_path)
    families = {
        "source-follow-session-05-14-confidence-70": "05_14",
        "source-follow-session-07-16-confidence-70": "07_16",
        "source-follow-session-08-17-confidence-70": "08_17",
    }

    for family, token in families.items():
        args = module._parser().parse_args(
            [
                "--labels",
                str(labels_path),
                "--development-price-context",
                "dev-prices.parquet",
                "--development-funding-context",
                "dev-funding.parquet",
                "--fresh-price-context",
                "fresh-prices.parquet",
                "--fresh-funding-context",
                "fresh-funding.parquet",
                "--candidate-family",
                family,
                "--out",
                "report.json",
            ]
        )
        contract = module._experiment_contract(args.candidate_family)
        events = module._events(labels_path, [], None, args.candidate_family)

        assert contract["event_policy"] == (
            f"trend_down_session_{token}_minimum_confidence_0_70_sensitivity"
        )
        assert contract["minimum_source_confidence"] == 0.70
        assert contract["runtime_strategy_changed"] is False
        assert contract["selection_is_promotion"] is False
        assert events["recipe_id"].eq(f"follow_td_session_{token}_conf70").all()
