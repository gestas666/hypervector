"""Contracts for the source-bounded pullback re-entry experiment."""

from __future__ import annotations

from dataclasses import asdict
import importlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd

_MODULE = "hypervector.research.hypervelocity_pullback_reentry"


def _module() -> object:
    return importlib.import_module(_MODULE)


def _script() -> ModuleType:
    path = Path("scripts/hypervelocity_pullback_reentry.py")
    spec = importlib.util.spec_from_file_location("pullback_reentry_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load pullback re-entry script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time_utc": [
                "2026-01-01T00:00:30Z",
                "2026-01-01T00:04:30Z",
                "2026-01-01T00:08:30Z",
                "2026-01-01T00:12:30Z",
            ],
            "close_time_utc": [
                "2026-01-01T00:01:30Z",
                "2026-01-01T00:05:30Z",
                None,
                None,
            ],
            "side": ["long"] * 4,
            "entry_price": [100.0] * 4,
            "exit_price": [100.2, 100.2, 100.2, None],
            "status": ["closed", "closed", "closed", "open"],
            "timestamp_provenance": ["trade_backed"] * 4,
        }
    )


def _decisions() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=13, freq="1min", tz="UTC")
    state = ["TREND_UP"] * 13
    state[2] = "RANGE"
    state[3] = "TREND_UP"
    state[6] = "RANGE"
    state[7] = "TREND_UP"
    structural: list[str | None] = ["long"] * 13
    structural[5] = None
    return pd.DataFrame(
        {
            "state_1m": state,
            "structural_direction": structural,
            "entry_direction": ["long"] * 13,
        },
        index=index,
    )


def test_candidate_configs_differ_only_by_frozen_reentry_controls() -> None:
    module = _module()

    configs = module.target_pullback_candidate_configs()

    assert list(configs) == [
        "regime_reset_60s",
        "target_pullback_transition_cap6_mature30",
    ]
    control, candidate = configs.values()
    differences = {
        name
        for name, value in asdict(control).items()
        if value != asdict(candidate)[name]
    }
    assert differences == {
        "same_direction_reentry_policy",
        "target_continuation_limit_per_episode",
        "target_continuation_minimum_episode_seconds",
    }
    assert control.reentry_cooldown_seconds == 60.0
    assert candidate.target_continuation_limit_per_episode == 6
    assert candidate.target_continuation_minimum_episode_seconds == 1_800.0


def test_source_compatibility_retains_reset_and_censored_windows() -> None:
    module = _module()

    result = module.source_pullback_compatibility(_positions(), _decisions())

    assert result["target_like_same_side_windows"] == 3
    assert result["observable_windows"] == 2
    assert result["censored_missing_close"] == 1
    assert result["pullback_transition_windows"] == 2
    assert result["pullback_without_structural_reset"] == 1
    assert result["structural_reset_windows"] == 1
    assert len(result["windows"]) == 3
    assert result["windows"][2]["anchor_close_time_utc"] is None
    assert result["windows"][2]["pullback_transition_observed"] is None


def test_script_contract_is_report_only_observe_and_immutable(tmp_path: Path) -> None:
    module = _script()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--supplemental-positions",
            "supplemental.csv",
            "--config",
            "configs/hypervelocity_faithful.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--out",
            str(tmp_path / "report.json"),
        ]
    )

    contract = module._experiment_contract(args)
    assert contract["report_only"] is True
    assert contract["runtime_strategy_changed"] is False
    assert contract["decision_profile"] == "canonical_faithful"
    assert module._metalabel_policy(args.config) == {
        "mode": "observe",
        "may_filter": False,
        "may_scale": False,
    }
    module._write_immutable_report(args.out, {"ok": True})
    try:
        module._write_immutable_report(args.out, {"ok": False})
    except FileExistsError:
        pass
    else:
        raise AssertionError("immutable report overwrite was accepted")
