"""Contract tests for the immutable Cipher suite research command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/cipher_suite_directional_screen.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("cipher_suite_directional_screen", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Cipher suite script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _argv(output: Path) -> list[str]:
    return [
        "--symbol",
        "BTC",
        "--database",
        "market.duckdb",
        "--backtest-lab-root",
        "../backtest-lab/backtest_lab",
        "--start",
        "2025-04-26T00:00:00Z",
        "--end",
        "2026-01-25T23:20:00Z",
        "--segment",
        "development",
        "--out",
        str(output),
    ]


def test_parser_requires_source_data_window_and_output() -> None:
    """The exact source tree and market window must be explicit inputs."""
    module = _module()

    with pytest.raises(SystemExit):
        module._parser().parse_args([])

    args = module._parser().parse_args(_argv(Path("report.json")))
    assert args.symbol == "BTC"
    assert args.segment == "development"


def test_parser_accepts_one_frozen_directional_validation_cell() -> None:
    """A validation run must be able to expose exactly one preselected cell."""
    module = _module()
    argv = _argv(Path("report.json")) + [
        "--candidate",
        "cipher_b",
        "--side",
        "short",
        "--target-bps",
        "80",
        "--stop-bps",
        "40",
        "--horizon-bars",
        "32",
    ]

    args = module._parser().parse_args(argv)
    config, candidate, side = module._screen_selection(args, 15)

    assert config.candidates == ("cipher_b",)
    assert config.exit_specs[0].identity == "tp80_sl40_h32"
    assert candidate == "cipher_b"
    assert side == "short"


def test_parser_accepts_documented_a_b_bundle_workflow() -> None:
    """The corrected workflow must expose only A+B and A+B+DBSI candidates."""
    module = _module()
    argv = _argv(Path("report.json")) + [
        "--workflow",
        "documented_bundle",
        "--timeframe",
        "5m",
        "--candidate",
        "cipher_a_b_trigger",
        "--side",
        "long",
        "--target-bps",
        "40",
        "--stop-bps",
        "25",
        "--horizon-bars",
        "24",
    ]

    args = module._parser().parse_args(argv)
    config, candidate, side = module._screen_selection(args, 5)

    assert config.candidates == ("cipher_a_b_trigger",)
    assert candidate == "cipher_a_b_trigger"
    assert side == "long"


def test_documented_bundle_rejects_non_five_minute_execution() -> None:
    """The first bounded A15/B5 experiment must not silently change timeframes."""
    module = _module()
    argv = _argv(Path("report.json")) + [
        "--workflow",
        "documented_bundle",
        "--timeframe",
        "15m",
    ]
    args = module._parser().parse_args(argv)

    with pytest.raises(ValueError, match="requires 5m execution"):
        module._screen_selection(args, 15)


def test_command_refuses_to_overwrite_any_immutable_output(tmp_path: Path) -> None:
    """Existing reports or sidecars must stop the command before data access."""
    output = tmp_path / "report.json"
    output.with_suffix(".signals.parquet").write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Cipher output exists"):
        _module().main(_argv(output))


def test_command_surface_has_no_live_execution_authority() -> None:
    """Cipher research must not expose wallet, arming, or order submission paths."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
