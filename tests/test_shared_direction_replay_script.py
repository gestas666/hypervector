"""CLI contracts for exact shared-direction portfolio replay."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_shared_direction_replay.py")
    assert path.is_file()
    spec = importlib.util.spec_from_file_location("shared_direction_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load shared replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _argv(output: Path) -> list[str]:
    return [
        "--bars",
        "bars.parquet",
        "--labels",
        "labels.parquet",
        "--labels-metadata",
        "labels.json",
        "--data-root",
        "data",
        "--research-database",
        "market.duckdb",
        "--start",
        "2026-04-28T00:00:00Z",
        "--end",
        "2026-07-28T00:00:00Z",
        "--price-context",
        "prices.parquet",
        "--funding-context",
        "funding.parquet",
        "--fill-rule",
        "trade-through",
        "--out",
        str(output),
    ]


def test_shared_configs_preserve_risk_and_require_fresh_post_flat_signal(
    tmp_path: Path,
) -> None:
    module = _load_script()
    args = module._parser().parse_args(_argv(tmp_path / "report.json"))

    configs = module._configs(args)

    assert set(configs) == {"short_control", "long_control", "combined"}
    for config in configs.values():
        assert config.initial_equity == pytest.approx(15_000.0)
        assert config.margin_fraction == pytest.approx(0.35)
        assert config.leverage == pytest.approx(30.0)
        assert config.target_margin_pct == pytest.approx(8.0)
        assert config.fixed_margin_stop_pct is None
        assert config.maximum_hold_seconds == pytest.approx(86_400.0)
        assert config.entry_ttl_seconds == pytest.approx(60.0)
        assert config.occupied_signal_policy == "ignore"


def test_shared_contract_is_report_only_and_short_priority(tmp_path: Path) -> None:
    module = _load_script()
    args = module._parser().parse_args(_argv(tmp_path / "report.json"))

    contract = module._contract(args)

    assert contract["execution_authority"] == "none"
    assert contract["runtime_strategy_changed"] is False
    assert contract["model_authority"] == "observe"
    assert contract["shared_position_limit"] == 1
    assert contract["simultaneous_signal_priority"] == "source_follow_short"
    assert contract["occupied_signal_policy"] == "ignore_and_require_fresh_after_flat"


def test_shared_session_contract_filters_on_decision_clock(tmp_path: Path) -> None:
    """The session challenger must retain only half-open decision timestamps."""
    module = _load_script()
    argv = [
        *_argv(tmp_path / "report.json"),
        "--short-entry-session",
        "[06:00,15:00)",
    ]
    args = module._parser().parse_args(argv)
    signals = tuple(
        SimpleNamespace(decision_time_utc=value)
        for value in (
            "2026-05-01T05:59:00+00:00",
            "2026-05-01T06:00:00+00:00",
            "2026-05-01T14:59:00+00:00",
            "2026-05-01T15:00:00+00:00",
        )
    )

    selected = module._filter_short_signals(signals, args.short_entry_session)
    contract = module._contract(args)

    assert [signal.decision_time_utc for signal in selected] == [
        "2026-05-01T06:00:00+00:00",
        "2026-05-01T14:59:00+00:00",
    ]
    assert contract["short_entry_session_utc"] == "[06:00,15:00)"
    assert contract["short_entry_session_clock"] == "decision_time_utc"


def test_main_writes_one_immutable_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    output = tmp_path / "report.json"
    monkeypatch.setattr(module, "_report", lambda _args: {"report_only": True})
    argv = _argv(output)

    assert module.main(argv) == 0
    assert output.is_file()
    assert module.main(argv) == 1


def test_comparison_does_not_claim_queue_nonfill_was_position_displacement() -> None:
    """A missing combined fill may result from equity-sized queue volume."""
    module = _load_script()
    filled = SimpleNamespace(
        direction="short",
        signal_time_utc="2026-05-27T13:35:00+00:00",
        entry_time_utc="2026-05-27T13:35:07+00:00",
    )
    expired = SimpleNamespace(
        direction="short",
        signal_time_utc=filled.signal_time_utc,
        entry_time_utc=None,
    )
    short = SimpleNamespace(
        final_equity=10_000.0,
        maximum_drawdown_pct=-10.0,
        lifecycles=(filled,),
    )
    combined = SimpleNamespace(
        final_equity=10_100.0,
        maximum_drawdown_pct=-9.0,
        lifecycles=(expired,),
    )

    result = module._comparison(
        {"short_control": short, "long_control": short, "combined": combined}
    )

    assert result["short_control_fills_not_reproduced_in_combined"] == [
        filled.signal_time_utc
    ]
    assert "short_fills_displaced_by_shared_portfolio" not in result


def test_shared_replay_uses_five_minute_bars_for_short_range() -> None:
    """Short selection must resample while the long retains minute evidence."""
    module = _load_script()
    index = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    minute_bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": [101, 102, 103, 104, 105],
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
        },
        index=index,
    )

    signal_bars = module._short_signal_bars(minute_bars)

    assert list(signal_bars.index) == [index[0]]
    assert signal_bars.iloc[0]["high"] == 105.0
