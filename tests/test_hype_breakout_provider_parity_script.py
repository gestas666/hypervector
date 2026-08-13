"""Tests for the immutable HT-Breakout provider parity command."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).parents[1] / "scripts" / "hype_breakout_provider_parity.py"


def _load() -> ModuleType:
    """Load the command without invoking its entry point."""
    spec = spec_from_file_location("hype_breakout_provider_parity_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HT-Breakout parity script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(exact: bool) -> dict[str, object]:
    """Return one minimal window report."""
    return {
        "exact_parity": exact,
        "historical_entries": 2,
        "live_entries": 2,
        "missing_from_live": [] if exact else [{"decision_time_ms": 1}],
        "extra_in_live": [],
        "reference_price_mismatches": [],
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }


def test_parser_binds_exact_sol_sources_and_three_windows() -> None:
    """The runner must use venue-matched SOL inputs and fixed parity windows."""
    module = _load()

    args = module.build_parser().parse_args(["--out", "result.json"])

    assert args.sol_bars.name == "SOL_1m_365d.parquet"
    assert args.sol_funding.name == "funding.parquet"
    assert len(module.parity_windows()) == 3
    assert {window.phase for window in module.parity_windows()} == {
        "development_early",
        "development_late",
        "opened_final_descriptive",
    }


def test_artifact_requires_every_window_to_confirm_parity() -> None:
    """One mismatch must prevent a success-shaped aggregate conclusion."""
    module = _load()
    reports = {
        "development_early": _report(True),
        "development_late": _report(False),
        "opened_final_descriptive": _report(True),
    }

    artifact = module.build_artifact(
        reports,
        source_evidence={"fixture": {"sha256": "0" * 64, "bytes": 1}},
    )

    assert artifact["all_windows_exact_parity"] is False
    assert artifact["decision"] == "historical_live_provider_mismatch_requires_fix"
    assert artifact["execution_authority"] == "none"
    assert artifact["automatic_promotion"] is False
    assert artifact["runtime_strategy_changed"] is False


def test_run_rejects_existing_output_before_loading_sources(tmp_path: Path) -> None:
    """The parity artifact must never overwrite prior evidence."""
    module = _load()
    output = tmp_path / "existing.json"
    output.touch()

    try:
        module.run(
            argparse.Namespace(
                out=output,
                sol_bars=tmp_path / "missing.parquet",
                sol_funding=tmp_path / "missing-funding.parquet",
            )
        )
    except FileExistsError as exc:
        assert "immutable HT-Breakout parity output exists" in str(exc)
    else:
        raise AssertionError("existing immutable parity output was accepted")
