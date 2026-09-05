"""CLI contract tests for HYPE exit parity research evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

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


def test_parser_supports_complete_v54_exit_contract() -> None:
    """The runner exposes opposite-native-onset fixed versus extension replay."""
    module = _load()
    args = module.build_parser().parse_args(
        ["--out", "result.json", "--compare-v54-exit-contract"]
    )

    assert args.compare_v54_exit_contract is True


def test_parser_supports_v54_directional_authority_comparison() -> None:
    """The runner exposes the post-observation HYPE side-authority audit."""
    module = _load()
    args = module.build_parser().parse_args(
        ["--out", "result.json", "--compare-v54-entry-sides"]
    )

    assert args.compare_v54_entry_sides is True


def test_parser_supports_v54_adverse_context_comparison() -> None:
    """The runner exposes the single predeclared 15-minute context challenger."""
    module = _load()
    args = module.build_parser().parse_args(
        ["--out", "result.json", "--compare-v54-adverse-15m-context"]
    )

    assert args.compare_v54_adverse_15m_context is True


def test_runner_dispatches_v54_adverse_context_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flag selects only the predeclared report-only context builder."""
    module = _load()
    args = module.build_parser().parse_args(
        ["--out", "result.json", "--compare-v54-adverse-15m-context"]
    )
    seen: dict[str, object] = {}

    def build(
        market: object,
        *,
        holdout_days: int,
        fold_count: int,
    ) -> dict[str, object]:
        seen.update(
            market=market,
            holdout_days=holdout_days,
            fold_count=fold_count,
        )
        return {"execution_authority": "none", "development_comparison": {}}

    monkeypatch.setattr(module, "build_hype_native_adverse_context_comparison", build)
    market = object()

    report, evidence = module._build_report(args, market, object(), object())

    assert report["execution_authority"] == "none"
    assert seen == {"market": market, "holdout_days": 60, "fold_count": 5}
    assert evidence is None


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
