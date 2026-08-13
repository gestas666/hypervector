"""CLI contracts for immutable Hulk Smash AutoTune research."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/hulk_smash_autotune.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("hulk_smash_autotune_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Hulk AutoTune script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _argv(output: Path) -> list[str]:
    return [
        "--database",
        "data/research/market.duckdb",
        "--journal",
        "data/research/strategy_trials.duckdb",
        "--backtest-lab-root",
        "/tmp/backtest-lab",
        "--mc-scalper-root",
        "/tmp/mc-scalper",
        "--market-cipher-cli-root",
        "/tmp/market-cipher-cli",
        "--symbol",
        "BTC",
        "--funding",
        "BTC=/tmp/btc.parquet",
        "--symbol",
        "SOL",
        "--funding",
        "SOL=/tmp/sol.parquet",
        "--start",
        "2025-08-23T09:00:00Z",
        "--end",
        "2026-02-01T00:00:00Z",
        "--run-id",
        "hulk-local-signal-v1",
        "--surface",
        "local_signal_v1",
        "--out",
        str(output),
    ]


def test_parser_requires_explicit_sources_and_research_identity() -> None:
    """AutoTune cannot inherit ambiguous data, source, or output identities."""
    module = _module()

    with pytest.raises(SystemExit):
        module._parser().parse_args([])

    args = module._parser().parse_args(_argv(Path("report.json")))
    assert args.symbol == ["BTC", "SOL"]
    assert args.surface == "local_signal_v1"
    assert args.run_id == "hulk-local-signal-v1"


def test_parser_and_funding_map_support_full_configured_crypto_cohort() -> None:
    """The report-only tuner must audit every configured Hulk crypto mapping."""
    module = _module()
    argv = _argv(Path("report.json"))
    argv[argv.index("--start") : argv.index("--start")] = [
        "--symbol",
        "ETH",
        "--funding",
        "ETH=/tmp/eth.parquet",
        "--symbol",
        "HYPE",
        "--funding",
        "HYPE=/tmp/hype.parquet",
    ]

    args = module._parser().parse_args(argv)
    funding = module._funding_map(args.funding)

    assert args.symbol == ["BTC", "SOL", "ETH", "HYPE"]
    assert set(funding) == {"BTC", "ETH", "SOL", "HYPE"}


def test_existing_report_is_rejected_before_data_access(tmp_path: Path) -> None:
    """Immutable tuner output may not be overwritten by a later experiment."""
    output = tmp_path / "report.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        _module().main(_argv(output))


def test_command_has_no_live_execution_surface() -> None:
    """The development tuner must remain structurally unable to place orders."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
