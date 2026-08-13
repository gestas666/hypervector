"""CLI contract tests for HYPE exit parity research evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SCRIPT = Path(__file__).parents[1] / "scripts" / "hype_breakout_exit_experiment.py"


def _load() -> object:
    spec = spec_from_file_location("hype_breakout_exit_experiment_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HYPE exit experiment script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_supports_live_extension_parity_mode() -> None:
    """The immutable runner can compare fixed and deployed hold mechanics."""
    module = _load()
    args = module.build_parser().parse_args(
        ["--out", "result.json", "--compare-live-extension"]
    )

    assert args.compare_live_extension is True


def test_parser_supports_breakout_entry_direction_comparison() -> None:
    """The immutable runner exposes one non-tuned entry-direction challenger."""
    module = _load()
    args = module.build_parser().parse_args(
        ["--out", "result.json", "--compare-entry-direction"]
    )

    assert args.compare_entry_direction is True


def test_parser_supports_structural_breakout_alignment_comparison() -> None:
    """The runner exposes the post-hoc agreement diagnostic report-only."""
    module = _load()
    args = module.build_parser().parse_args(
        ["--out", "result.json", "--compare-entry-alignment"]
    )

    assert args.compare_entry_alignment is True


def test_parser_supports_five_minute_momentum_exit_comparison() -> None:
    """The runner exposes one predeclared causal momentum exit challenger."""
    module = _load()
    args = module.build_parser().parse_args(
        ["--out", "result.json", "--compare-momentum-exit"]
    )

    assert args.compare_momentum_exit is True
