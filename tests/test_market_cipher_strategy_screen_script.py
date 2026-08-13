"""Contracts for the immutable Hulk/Market Cipher research command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/market_cipher_strategy_screen.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("market_cipher_strategy_screen", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Market Cipher screen: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _argv(output: Path) -> list[str]:
    return [
        "--database",
        "data/research/market.duckdb",
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
        "--start",
        "2025-08-23T09:00:00Z",
        "--end",
        "2026-02-01T00:00:00Z",
        "--segment",
        "development",
        "--profile",
        "hulk_expansion_short_tuned_v2",
        "--robustness",
        "cost_stress",
        "--out",
        str(output),
    ]


def test_parser_requires_sources_window_segment_and_output() -> None:
    """A run cannot inherit ambiguous source or chronological identities."""
    module = _module()

    with pytest.raises(SystemExit):
        module._parser().parse_args([])

    args = module._parser().parse_args(_argv(Path("report.json")))
    assert args.symbol == ["BTC"]
    assert args.segment == "development"
    assert args.robustness == "cost_stress"
    assert args.bar_minutes == 30

    fifteen = _argv(Path("fifteen.json"))
    fifteen.extend(["--bar-minutes", "15"])
    assert module._parser().parse_args(fifteen).bar_minutes == 15

    robustness = _argv(Path("robustness.json"))
    robustness[robustness.index("development")] = "robustness"
    assert module._parser().parse_args(robustness).segment == "robustness"


def test_parser_binds_hype_to_an_explicit_candle_bundle() -> None:
    """Cross-asset Hulk research cannot infer a venue candle source."""
    module = _module()
    argv = _argv(Path("hype.json"))
    argv[argv.index("BTC")] = "HYPE"
    argv[argv.index("BTC=/tmp/btc.parquet")] = "HYPE=/tmp/hype.parquet"
    argv[argv.index("--start") : argv.index("--start")] = [
        "--candle-bundle",
        "HYPE=/tmp/hype-candles",
    ]

    args = module._parser().parse_args(argv)

    assert args.symbol == ["HYPE"]
    assert module._bundle_map(args.candle_bundle) == {"HYPE": Path("/tmp/hype-candles")}


def test_existing_report_or_sidecar_is_rejected_before_data_access(
    tmp_path: Path,
) -> None:
    """Immutable evidence may not be overwritten by a later run."""
    output = tmp_path / "report.json"
    output.with_suffix(".trades.parquet").write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="output exists"):
        _module().main(_argv(output))


def test_command_has_no_live_execution_surface() -> None:
    """The research command must remain structurally unable to place orders."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
