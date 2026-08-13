"""Command-contract tests for the report-only BBWP replay script."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_bbwp_precedence.py")
    spec = importlib.util.spec_from_file_location("hypervelocity_bbwp_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load BBWP replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _minimum_age_args(module: ModuleType, *extra: str) -> argparse.Namespace:
    parser = getattr(module, "_parser")()
    return parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            *extra,
            "--out",
            "report.json",
        ]
    )


def test_parser_accepts_supplemental_creator_positions() -> None:
    module = _load_script()
    parser = getattr(module, "_parser")()

    args = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--supplemental-positions",
            "supplemental.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-07-09T04:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--out",
            "report.json",
        ]
    )

    assert args.supplemental_positions == Path("supplemental.csv")


def test_source_positions_merge_supplemental_outcome_rows(tmp_path: Path) -> None:
    module = _load_script()
    positions_path = tmp_path / "positions.csv"
    supplemental_path = tmp_path / "supplemental.csv"
    pd.DataFrame(
        {
            "open_time_utc": ["2026-07-24T15:06:32.209297Z"],
            "close_time_utc": [None],
            "side": ["short"],
            "entry_price": [63_893.0],
            "exit_price": [None],
            "status": ["open"],
        }
    ).to_csv(positions_path, index=False)
    pd.DataFrame(
        {
            "open_time_utc": [
                "2026-07-24T15:06:32.209297Z",
                "2026-07-25T18:50:00Z",
            ],
            "side": ["short", "long"],
            "entry_price": [63_893.0, 64_395.0],
            "exit_price": [63_766.0, 64_523.0],
            "outcome_time_utc": [None, None],
        }
    ).to_csv(supplemental_path, index=False)

    positions = getattr(module, "_source_positions")(
        positions_path,
        supplemental_path,
    )

    assert len(positions) == 2
    assert positions["side"].tolist() == ["short", "long"]
    assert positions["exit_price"].tolist() == [63_766.0, 64_523.0]
    assert positions["open_time_utc"].tolist() == [
        "2026-07-24T15:06:32.209297+00:00",
        "2026-07-25T18:50:00+00:00",
    ]


def test_event_entry_ttl_is_forwarded_to_maker_replay_config() -> None:
    """The declared TTL challenger must reach the event-engine config."""
    module = _load_script()
    parser = getattr(module, "_parser")()
    args = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--event-entry-ttl-seconds",
            "60",
            "--out",
            "report.json",
        ]
    )

    config = getattr(module, "_maker_replay_config")(args)

    assert config.entry_ttl_seconds == 60.0


def test_event_initial_equity_is_forwarded_to_maker_replay_config() -> None:
    """The declared capacity challenger must reach the event-engine config."""
    module = _load_script()
    parser = getattr(module, "_parser")()
    args = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--event-initial-equity",
            "120",
            "--out",
            "report.json",
        ]
    )

    config = getattr(module, "_maker_replay_config")(args)

    assert config.initial_equity == 120.0


def test_event_entry_depth_is_forwarded_to_maker_replay_config() -> None:
    module = _load_script()
    parser = getattr(module, "_parser")()
    args = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--event-entry-depth-ticks",
            "1",
            "--out",
            "report.json",
        ]
    )

    config = getattr(module, "_maker_replay_config")(args)

    assert config.entry_depth_ticks == 1


def test_event_breakout_confirmation_option_transforms_identity() -> None:
    module = _load_script()
    parser = getattr(module, "_parser")()
    args = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--event-breakout-confirmation",
            "1m-trend",
            "--out",
            "report.json",
        ]
    )
    decisions = pd.DataFrame(
        {
            "state_1m": ["TREND_UP"],
            "state_5m": ["BREAKOUT"],
            "structural_direction": ["long"],
            "entry_direction": [None],
            "reason": ["5m_breakout_awaiting_1m_confirmation"],
        }
    )

    transformed, candidate = getattr(module, "_apply_breakout_confirmation")(
        decisions, args, "hard_recovery6"
    )

    assert transformed["entry_direction"].iloc[0] == "long"
    assert candidate == "hard_recovery6_breakout_confirm_1m_trend"


def test_event_breakout_onset_option_transforms_only_onset_identity() -> None:
    module = _load_script()
    parser = getattr(module, "_parser")()
    args = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--event-breakout-confirmation",
            "range-onset-1m-trend",
            "--out",
            "report.json",
        ]
    )
    decisions = pd.DataFrame(
        {
            "state_1m": ["RANGE", "TREND_UP"],
            "state_5m": ["RANGE", "BREAKOUT"],
            "structural_direction": [None, "long"],
            "entry_direction": [None, None],
            "reason": [
                "5m_bbwp_compression_range",
                "5m_breakout_awaiting_1m_confirmation",
            ],
            "bbwp_5m_hard_range": [True, False],
        }
    )

    transformed, candidate = getattr(module, "_apply_breakout_confirmation")(
        decisions, args, "hard_recovery6"
    )

    assert transformed["entry_direction"].tolist() == [None, "long"]
    assert candidate == "hard_recovery6_breakout_confirm_range_onset_1m_trend"


def test_event_breakout_confirmation_default_preserves_decisions() -> None:
    module = _load_script()
    parser = getattr(module, "_parser")()
    args = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--out",
            "report.json",
        ]
    )
    decisions = pd.DataFrame({"entry_direction": [None]})

    transformed, candidate = getattr(module, "_apply_breakout_confirmation")(
        decisions, args, "hard_recovery6"
    )

    pd.testing.assert_frame_equal(transformed, decisions)
    assert candidate == "hard_recovery6"


def test_event_direction_policy_applies_report_only_1m_first_fusion() -> None:
    module = _load_script()
    args = _minimum_age_args(
        module,
        "--event-direction-policy",
        "prefer-1m-direction",
    )
    decisions = pd.DataFrame(
        {
            "state_1m": ["TREND_UP", "RANGE"],
            "entry_direction": ["short", "short"],
        }
    )

    transformed, candidate = getattr(module, "_apply_direction_policy")(
        decisions,
        args,
        "faithful_control_cooldown_300s",
    )

    assert transformed["entry_direction"].tolist() == ["long", "short"]
    assert candidate == ("faithful_control_cooldown_300s_prefer_1m_direction_else_5m")


def test_event_variants_add_direction_fusion_to_serial_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    args = _minimum_age_args(
        module,
        "--event-direction-policy",
        "prefer-1m-direction",
    )
    decisions = pd.DataFrame({"state_1m": ["TREND_UP"], "entry_direction": ["short"]})
    screened: list[str] = []

    def record_screen(_rows: object, candidate: str, *_args: object) -> None:
        screened.append(candidate)

    monkeypatch.setattr(module, "_append_screening", record_screen)
    transformed, candidate = getattr(module, "_apply_event_variants")(
        args,
        decisions,
        "faithful_control_cooldown_300s",
        [],
        pd.DataFrame(),
        pd.DataFrame(),
        25.0,
    )

    assert transformed["entry_direction"].tolist() == ["long"]
    assert screened == [candidate]


def test_event_minimum_regime_age_transforms_entries_and_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    args = _minimum_age_args(module, "--event-minimum-regime-age", "5")
    decisions = pd.DataFrame(
        {
            "state_5m": ["TREND_UP"] * 6,
            "entry_direction": ["long"] * 6,
        }
    )

    def ignore_screening(*_args: object) -> None:
        return None

    monkeypatch.setattr(module, "_append_screening", ignore_screening)
    transformed, candidate = getattr(module, "_apply_age_variant")(
        args,
        decisions,
        "hard_recovery6",
        [],
        pd.DataFrame(),
        pd.DataFrame(),
    )

    assert transformed["entry_direction"].iloc[:5].isna().all()
    assert transformed["entry_direction"].iloc[5] == "long"
    assert transformed["regime_entry_minimum_age_blocked"].sum() == 5
    assert candidate == "hard_recovery6_regime_age_gte_5"


def test_event_minimum_and_maximum_regime_age_are_mutually_exclusive(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()

    with pytest.raises(SystemExit):
        _minimum_age_args(
            module,
            "--event-minimum-regime-age",
            "5",
            "--event-maximum-regime-age",
            "20",
        )
    assert "not allowed with argument" in capsys.readouterr().err
