"""Command-contract tests for the canonical recovery-long replay."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_selective_recovery_replay.py")
    spec = importlib.util.spec_from_file_location("selective_recovery_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load selective recovery replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selective_recovery_replay_command_exists() -> None:
    """The missing long-arm experiment must have a durable command."""
    assert Path("scripts/hypervelocity_selective_recovery_replay.py").is_file()


def test_parser_requires_explicit_evidence_and_fill_rule() -> None:
    """Every economic result must identify its immutable market evidence."""
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--bars",
            "history.parquet",
            "--bars",
            "forward.parquet",
            "--config",
            "config.toml",
            "--data-root",
            "data",
            "--research-database",
            "market.duckdb",
            "--start",
            "2026-07-27T00:00:00Z",
            "--end",
            "2026-07-28T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--fill-rule",
            "trade-through",
            "--out",
            "result.json",
        ]
    )

    assert args.bars == [Path("history.parquet"), Path("forward.parquet")]
    assert args.fill_rule == "trade-through"
    assert args.initial_equity == 10_000.0


def test_recovery_inputs_select_only_fresh_1m_up_inside_5m_down() -> None:
    """The long arm must be the predeclared causal recovery event only."""
    module = _load_script()
    index = pd.date_range("2026-07-27T07:00:00Z", periods=2, freq="1min")
    decisions = pd.DataFrame(
        {
            "primary_regime": ["TREND_DOWN", "TREND_DOWN"],
            "breakout_direction": [None, None],
            "state_1m": ["TREND_DOWN", "TREND_UP"],
            "state_5m": ["TREND_DOWN", "TREND_DOWN"],
            "structural_direction": ["short", "short"],
            "confidence": [0.5, 0.7],
        },
        index=index,
    )
    raw_1m = decisions.loc[:, ["primary_regime", "breakout_direction"]]

    selected, config, event_count = module._recovery_inputs(
        decisions,
        raw_1m,
        initial_equity=10_000.0,
        fill_rule="through",
    )

    signals = selected.loc[selected["entry_direction"].notna()]
    assert signals.index.tolist() == [index[1]]
    assert signals["entry_direction"].tolist() == ["long"]
    assert signals["maximum_hold_seconds"].tolist() == [86_400.0]
    assert config.fill_rule == "through"
    assert event_count == 1


def test_replay_contract_preserves_faithful_risk_and_observe_authority() -> None:
    """The experiment must not smuggle a runtime or model-policy change."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--bars",
            "history.parquet",
            "--config",
            "config.toml",
            "--start",
            "2026-07-27T00:00:00Z",
            "--end",
            "2026-07-28T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--fill-rule",
            "trade-through",
            "--out",
            "result.json",
        ]
    )

    contract = module._replay_contract(args)

    assert contract == {
        "candidate": "c_1m_recovery_in_5m_down",
        "initial_equity": 10_000.0,
        "allocation_fraction": 0.70,
        "leverage": 40.0,
        "gross_margin_target_pct": 8.0,
        "maximum_hold_seconds": 86_400.0,
        "entry_ttl_seconds": 300.0,
        "reentry_cooldown_seconds": 60.0,
        "same_direction_reentry_policy": "regime_reset",
        "fill_rule": "trade-through",
        "stop_policy": "none",
    }


def test_main_writes_report_without_overwriting_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Research evidence must be immutable once published."""
    module = _load_script()
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        module,
        "_report",
        lambda _args: {"ok": True, "report_only": True},
        raising=False,
    )
    argv = [
        "--bars",
        "history.parquet",
        "--config",
        "config.toml",
        "--start",
        "2026-07-27T00:00:00Z",
        "--end",
        "2026-07-28T00:00:00Z",
        "--price-context",
        "prices.parquet",
        "--funding-context",
        "funding.parquet",
        "--fill-rule",
        "touch",
        "--out",
        str(output),
    ]

    assert module.main(argv) == 0
    assert output.is_file()
    assert module.main(argv) == 1


def test_report_is_observe_only_and_exposes_replay_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The durable report must disclose authority and evidence boundaries."""
    module = _load_script()
    index = pd.date_range("2026-07-27T07:00:00Z", periods=2, freq="1min")
    decisions = pd.DataFrame(
        {
            "primary_regime": ["TREND_DOWN", "TREND_DOWN"],
            "breakout_direction": [None, None],
            "state_1m": ["TREND_DOWN", "TREND_UP"],
            "state_5m": ["TREND_DOWN", "TREND_DOWN"],
            "structural_direction": ["short", "short"],
            "confidence": [0.5, 0.7],
        },
        index=index,
    )
    raw = decisions.loc[:, ["primary_regime", "breakout_direction"]]
    monkeypatch.setattr(module, "_classified_inputs", lambda _args: (decisions, raw))
    monkeypatch.setattr(
        module,
        "_execute_replay",
        lambda _args, _decisions, _config: (
            {"completed_trades": 1},
            {"checksums_verified": True},
        ),
    )
    monkeypatch.setattr(module, "_source_evidence", lambda _args: {"bars": []})
    monkeypatch.setattr(
        module,
        "runtime_observe_contract",
        lambda _path: {"mode": "observe", "may_filter": False},
    )
    args = module._parser().parse_args(
        [
            "--bars",
            "history.parquet",
            "--config",
            "config.toml",
            "--start",
            "2026-07-27T00:00:00Z",
            "--end",
            "2026-07-28T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--fill-rule",
            "trade-through",
            "--out",
            "result.json",
        ]
    )

    report = module._report(args)

    assert report["candidate_events"] == 1
    assert report["event_replay"] == {"completed_trades": 1}
    assert report["archive"] == {"checksums_verified": True}
    assert report["metalabel_policy"]["mode"] == "observe"
    assert report["report_only"] is True
    assert report["runtime_strategy_changed"] is False
