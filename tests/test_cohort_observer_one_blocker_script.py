"""Command contract for report-only observer exact-depth replay."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest


def test_parser_defaults_to_visible_depth_without_live_arm_flags() -> None:
    """Observer evidence must use explicit depth and expose no authority flags."""
    module = _module()
    parser = module._parser()  # type: ignore[attr-defined]
    args = parser.parse_args(
        [
            "--decisions",
            "decisions.jsonl",
            "--funding",
            "funding.parquet",
            "--out",
            "report.json",
            "--strategy-id",
            "range_onset_bidirectional_v1",
            "--symbol",
            "SOL",
            "--blocker",
            "awaiting_hourly_sma_cross",
            "--horizon-minutes",
            "15",
            "--notional-usd",
            "7500",
            "--taker-fee-rate",
            "0.000432",
            "--stop-proxy-bps",
            "80",
        ]
    )

    contract = module._contract(args, "SOL")  # type: ignore[attr-defined]
    assert contract.liquidity_policy == "visible_depth"
    assert contract.notional_usd == 7_500.0
    assert not hasattr(args, "enabled")
    assert not hasattr(args, "i_accept_live_risk")


def test_cross_restart_requires_an_explicit_origin_run() -> None:
    """Compatible continuation must never silently replace latest-run scope."""
    module = _module()
    parser = module._parser()  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="origin run"):
        module._selection(  # type: ignore[attr-defined]
            [], parser.parse_args([*_required_args(), "--compatible-restarts"])
        )


def test_cross_restart_selection_returns_all_exact_compatible_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The source sidecar must preserve every selected continuation identity."""
    module = _module()
    rows = [{"run_id": "origin"}, {"run_id": "continued"}]
    identities = ({"run_id": "origin"}, {"run_id": "continued"})
    monkeypatch.setattr(
        module,
        "select_compatible_report_only_observer_runs",
        lambda records, requested: (tuple(records), identities),
    )
    args = module._parser().parse_args(  # type: ignore[attr-defined]
        [*_required_args(), "--run-id", "origin", "--compatible-restarts"]
    )

    selected, selected_identities = module._selection(rows, args)  # type: ignore[attr-defined]

    assert selected == tuple(rows)
    assert selected_identities == identities


def _required_args() -> list[str]:
    """Return the minimal report-only parser contract shared by tests."""
    return [
        "--decisions",
        "decisions.jsonl",
        "--funding",
        "funding.parquet",
        "--out",
        "report.json",
        "--strategy-id",
        "range_onset_bidirectional_v1",
        "--symbol",
        "SOL",
        "--blocker",
        "awaiting_hourly_sma_cross",
        "--horizon-minutes",
        "15",
        "--notional-usd",
        "7500",
        "--taker-fee-rate",
        "0.000432",
        "--stop-proxy-bps",
        "80",
    ]


def _module() -> ModuleType:
    path = Path("scripts/cohort_observer_one_blocker_execution_feasibility.py")
    spec = spec_from_file_location("cohort_observer_one_blocker", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
