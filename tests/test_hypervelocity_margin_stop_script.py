"""Command contracts for the faithful fixed-margin stop comparison."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_margin_stop_compare.py")
    spec = importlib.util.spec_from_file_location("margin_stop_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load margin-stop comparison script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arguments() -> list[str]:
    return [
        "--bars",
        "bars.parquet",
        "--config",
        "config.toml",
        "--start",
        "2026-04-28T00:00:00Z",
        "--end",
        "2026-07-27T00:00:00Z",
        "--price-context",
        "prices.parquet",
        "--funding-context",
        "funding.parquet",
        "--out",
        "report.json",
    ]


def test_parser_defaults_match_current_shadow_contract() -> None:
    module = _load_script()

    args = module._parser().parse_args(_arguments())

    assert args.initial_equity == 10_000.0
    assert args.segment_days == 30
    assert module._replay_contract(args) == {
        "initial_equity": 10_000.0,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "maker_fee_rate": 0.00015,
        "taker_fee_rate": 0.00045,
        "fill_rule": "trade-through",
        "entry_ttl_seconds": 300.0,
        "reentry_cooldown_seconds": 60.0,
        "same_direction_reentry_policy": "regime_reset",
    }


def test_parser_selects_source_bounded_maximum_hold_family() -> None:
    module = _load_script()

    args = module._parser().parse_args(
        _arguments()
        + [
            "--candidate-family",
            "max-hold",
            "--creator-positions",
            "positions.csv",
        ]
    )

    assert args.candidate_family == "max-hold"
    assert args.creator_positions == Path("positions.csv")


def test_parser_selects_tight_margin_stop_family() -> None:
    module = _load_script()

    args = module._parser().parse_args(
        _arguments() + ["--candidate-family", "tight-margin-stop"]
    )

    assert args.candidate_family == "tight-margin-stop"
    assert module._replay_contract(args)["same_direction_reentry_policy"] == (
        "regime_reset"
    )


def test_parser_selects_bounded_target_ladder_family() -> None:
    module = _load_script()

    args = module._parser().parse_args(
        _arguments()
        + [
            "--candidate-family",
            "target-ladder",
            "--creator-positions",
            "positions.csv",
            "--supplemental-positions",
            "supplemental.csv",
        ]
    )

    assert args.candidate_family == "target-ladder"
    assert args.creator_positions == Path("positions.csv")
    assert args.supplemental_positions == Path("supplemental.csv")
    assert module._replay_contract(args)["same_direction_reentry_policy"] == (
        "candidate_specific"
    )


def test_max_hold_family_selects_frozen_configs_and_identity() -> None:
    module = _load_script()
    args = SimpleNamespace(candidate_family="max-hold", initial_equity=10_000.0)

    configs = module._candidate_configs(args)

    assert list(configs) == [
        "no_timeout_control",
        "max_hold_6h",
        "max_hold_12h",
        "max_hold_24h",
    ]
    assert module._experiment_identity(args) == ("source_bounded_maximum_hold_grid_v1")


def test_tight_stop_family_selects_frozen_configs_and_identity() -> None:
    module = _load_script()
    args = SimpleNamespace(
        candidate_family="tight-margin-stop",
        initial_equity=10_000.0,
    )

    configs = module._candidate_configs(args)

    assert list(configs) == [
        "no_stop_control",
        "stop_2pct_margin",
        "stop_3pct_margin",
        "stop_4pct_margin",
    ]
    assert module._experiment_identity(args) == (
        "reverse_engineered_tight_margin_stop_grid_v1"
    )


def test_tight_stop_creator_context_retains_scorecard_calibration() -> None:
    module = _load_script()
    args = SimpleNamespace(
        candidate_family="tight-margin-stop",
        creator_positions=None,
    )

    context = module._creator_context(args, {})

    assert len(context["creator_calibration"]) == 2
    assert context["creator_calibration"][0]["wins"] == 42


def test_tight_stop_limitations_describe_stop_execution() -> None:
    module = _load_script()
    args = SimpleNamespace(candidate_family="tight-margin-stop")

    limitations = module._limitations(args)

    assert any("Stop execution" in value for value in limitations)
    assert any(
        "Liquidation is evaluated before a stop" in value for value in limitations
    )


def test_target_ladder_family_selects_frozen_configs_and_identity() -> None:
    module = _load_script()
    args = SimpleNamespace(candidate_family="target-ladder", initial_equity=10_000.0)

    configs = module._candidate_configs(args)

    assert list(configs) == [
        "regime_reset_60s",
        "target_ladder_cap2",
        "target_ladder_cap3",
        "target_ladder_cap6",
    ]
    assert module._experiment_identity(args) == "source_bounded_target_ladder_v1"


def test_mature_continuation_family_selects_frozen_configs_and_identity() -> None:
    module = _load_script()
    args = SimpleNamespace(
        candidate_family="mature-continuation",
        initial_equity=10_000.0,
    )

    configs = module._candidate_configs(args)

    assert list(configs) == [
        "regime_reset_60s",
        "target_ladder_cap2",
        "mature_target_ladder_cap2",
    ]
    assert module._experiment_identity(args) == ("source_mature_target_continuation_v1")


def test_max_hold_family_requires_creator_positions() -> None:
    module = _load_script()
    args = SimpleNamespace(candidate_family="max-hold", creator_positions=None)

    with pytest.raises(ValueError, match="creator-positions"):
        module._validate_family_args(args)


@pytest.mark.parametrize(
    ("creator", "supplemental", "missing"),
    [
        (None, Path("supplemental.csv"), "creator-positions"),
        (Path("positions.csv"), None, "supplemental-positions"),
    ],
)
def test_target_ladder_requires_both_source_files(
    creator: Path | None,
    supplemental: Path | None,
    missing: str,
) -> None:
    module = _load_script()
    args = SimpleNamespace(
        candidate_family="target-ladder",
        creator_positions=creator,
        supplemental_positions=supplemental,
    )

    with pytest.raises(ValueError, match=missing):
        module._validate_family_args(args)


def test_max_hold_creator_context_reports_source_duration(
    tmp_path: Path,
) -> None:
    module = _load_script()
    source = tmp_path / "positions.csv"
    pd.DataFrame(
        {
            "open_time_utc": ["2026-01-01T00:00:00Z"],
            "close_time_utc": ["2026-01-01T05:00:00Z"],
            "side": ["long"],
            "entry_price": [100.0],
            "status": ["closed"],
        }
    ).to_csv(source, index=False)
    args = SimpleNamespace(candidate_family="max-hold", creator_positions=source)
    configs = module.maximum_hold_candidate_configs()

    result = module._creator_context(args, configs)

    compatibility = result["source_hold_compatibility"]
    assert compatibility["closed_positions"] == 1
    assert compatibility["candidates"]["max_hold_6h"]["compatible_closed"] == 1


def test_target_ladder_creator_context_reports_episode_compatibility(
    tmp_path: Path,
) -> None:
    module = _load_script()
    source = tmp_path / "positions.csv"
    supplemental = tmp_path / "supplemental.csv"
    pd.DataFrame(
        {
            "open_time_utc": ["2026-01-01T00:01:30Z"],
            "close_time_utc": ["2026-01-01T00:02:00Z"],
            "side": ["long"],
            "entry_price": [100.0],
            "status": ["closed"],
        }
    ).to_csv(source, index=False)
    pd.DataFrame(
        {
            "open_time_utc": ["2026-01-01T00:02:30Z"],
            "side": ["long"],
            "entry_price": [100.2],
        }
    ).to_csv(supplemental, index=False)
    decisions = pd.DataFrame(
        {"structural_direction": ["long", "long", "long"]},
        index=pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC"),
    )
    args = SimpleNamespace(
        candidate_family="target-ladder",
        creator_positions=source,
        supplemental_positions=supplemental,
    )

    result = module._creator_context(args, {}, decisions)

    compatibility = result["source_episode_compatibility"]
    assert compatibility["logical_positions"] == 2
    assert compatibility["direction_matched_positions"] == 2
    assert compatibility["limit_compatibility"]["2"]["preserved_entries"] == 2


def test_max_hold_limitations_describe_deadline_execution() -> None:
    module = _load_script()
    args = SimpleNamespace(candidate_family="max-hold")

    limitations = module._limitations(args)

    assert any("first BBO at or after the deadline" in value for value in limitations)
    assert all("Stop execution" not in value for value in limitations)


def test_target_ladder_limitations_describe_source_bounded_reentry() -> None:
    module = _load_script()
    args = SimpleNamespace(candidate_family="target-ladder")

    limitations = module._limitations(args)

    assert any("does not prove a ladder counter" in value for value in limitations)
    assert any("successful target" in value for value in limitations)


def test_faithful_decisions_are_not_rewritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    bars = pd.DataFrame(
        {"timestamp": [pd.Timestamp("2026-01-01T00:00:00Z")]},
        index=pd.date_range("2026-01-01", periods=1, freq="1min", tz="UTC"),
    )
    expected = pd.DataFrame(
        {"entry_direction": ["long"], "structural_direction": ["long"]},
        index=bars.index,
    )
    regime_config = object()
    monkeypatch.setattr(
        module,
        "load_hypervelocity_profile",
        lambda _path: SimpleNamespace(regime_config=regime_config),
    )
    monkeypatch.setattr(
        module,
        "classify_multitimeframe",
        lambda frame, config: expected
        if frame is bars and config is regime_config
        else None,
    )

    result = module._faithful_decisions(bars, Path("config.toml"))

    assert result is expected


def test_config_hash_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    monkeypatch.setattr(
        module,
        "file_evidence",
        lambda _path: {"sha256": "incorrect", "bytes": 1},
    )

    with pytest.raises(ValueError, match="faithful config checksum mismatch"):
        module._verify_faithful_config(Path("config.toml"))


def test_report_write_is_immutable(tmp_path: Path) -> None:
    module = _load_script()
    output = tmp_path / "report.json"

    module._write_immutable_report(output, {"ok": True})

    assert json.loads(output.read_text(encoding="utf-8")) == {"ok": True}
    with pytest.raises(FileExistsError, match="margin-stop output exists"):
        module._write_immutable_report(output, {"ok": False})
