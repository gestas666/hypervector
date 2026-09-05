"""CLI contract tests for HYPE-native funding reconciliation."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path(__file__).parents[1] / "scripts" / "hype_native_path_funding.py"


def _load() -> object:
    spec = spec_from_file_location("hype_native_path_funding_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HYPE funding reconciliation script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_requires_explicit_price_window_and_immutable_output() -> None:
    """The report command must bind every evidence path and time boundary."""
    args = (
        _load()
        .build_parser()
        .parse_args(
            [
                "--path-report",
                "path.json",
                "--funding",
                "funding.parquet",
                "--price-start",
                "2026-08-17T20:00:00Z",
                "--price-end",
                "2026-08-18T04:21:00Z",
                "--out",
                "funded.json",
            ]
        )
    )

    assert args.maximum_oracle_staleness_ms == 120_000
    assert args.price_start.isoformat() == "2026-08-17T20:00:00+00:00"
    assert args.price_end.isoformat() == "2026-08-18T04:21:00+00:00"
    assert str(args.out) == "funded.json"


def test_parser_can_reconcile_an_actual_resolved_stop_exit() -> None:
    """A resolved stop path must be selectable without a timer horizon."""
    args = (
        _load()
        .build_parser()
        .parse_args(
            [
                "--path-report",
                "path.json",
                "--funding",
                "funding.parquet",
                "--price-start",
                "2026-08-17T07:00:00Z",
                "--price-end",
                "2026-08-17T14:00:00Z",
                "--resolved-path-exit",
                "--out",
                "funded.json",
            ]
        )
    )

    assert args.resolved_path_exit is True
