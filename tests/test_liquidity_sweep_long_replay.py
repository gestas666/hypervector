"""Contracts for exact maker replay of the liquidity-sweep long challenger."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.liquidity_sweep_long import (
    maker_decisions_from_hourly_signals,
)


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_liquidity_sweep_long_replay.py")
    spec = importlib.util.spec_from_file_location("liquidity_long_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load long replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hourly_signal_becomes_available_only_at_next_hour_open() -> None:
    """A completed 10:00 hour must not submit before 11:00 UTC."""
    index = pd.date_range("2026-07-01T10:00:00Z", periods=2, freq="1h")
    signals = pd.DataFrame(
        {
            "long_entry": [True, False],
            "long_exit": [False, False],
        },
        index=index,
    )

    result = maker_decisions_from_hourly_signals(signals)

    assert result.index.tolist() == list(index + pd.Timedelta(minutes=59))
    assert result["entry_direction"].tolist() == ["long", None]
    assert result["structural_direction"].tolist() == ["long", None]


def test_parser_requires_explicit_context_parts_and_trade_fill_rule() -> None:
    """Exact execution evidence must be fully identified at the CLI boundary."""
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--research-database",
            "market.duckdb",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-28T00:00:00Z",
            "--price-context",
            "prices-1.parquet",
            "--price-context",
            "prices-2.parquet",
            "--funding-context",
            "funding-1.parquet",
            "--funding-context",
            "funding-2.parquet",
            "--fill-rule",
            "trade-through",
            "--out",
            "report.json",
        ]
    )

    assert args.initial_equity == pytest.approx(15_000.0)
    assert args.fill_rule == "trade-through"
    assert len(args.price_context) == len(args.funding_context) == 2


def test_replay_contract_matches_bounded_long_screen() -> None:
    """Exact replay must preserve the fixed long risk and friction hypothesis."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-28T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--fill-rule",
            "through",
            "--out",
            "report.json",
        ]
    )

    config = module._replay_config(args)

    assert config.initial_equity == pytest.approx(15_000.0)
    assert config.margin_fraction == pytest.approx(0.35)
    assert config.leverage == pytest.approx(30.0)
    assert config.target_margin_pct == pytest.approx(8.0)
    assert config.fixed_margin_stop_pct == pytest.approx(18.0)
    assert config.maximum_hold_seconds == pytest.approx(86_400.0)
    assert config.entry_ttl_seconds == pytest.approx(60.0)
    assert config.fill_rule == "through"


def test_main_writes_immutable_report_only_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The long experiment must not overwrite prior evidence."""
    module = _load_script()
    output = tmp_path / "report.json"
    monkeypatch.setattr(module, "_report", lambda _args: {"report_only": True})
    argv = [
        "--bars",
        "bars.parquet",
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

    assert module.main(argv) == 0
    assert output.is_file()
    assert module.main(argv) == 1
