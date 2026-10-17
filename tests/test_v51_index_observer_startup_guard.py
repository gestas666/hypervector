"""Fail-closed startup coverage for required v51 index observers."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.live import cohort_process_commands
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)

_ROOT = Path(__file__).parents[1]
_V51 = (
    _ROOT
    / "configs"
    / "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)


def test_v51_dependency_guard_checks_exact_index_observers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A profile containing fresh15 v3 must prove both observers are fresh."""
    guard = getattr(cohort_process_commands, "require_live_provider_dependencies", None)
    assert callable(guard), "required live dependency guard is missing"
    config = load_multi_asset_live_config(_V51, mode="observe")
    calls: list[object] = []
    monkeypatch.setattr(
        cohort_process_commands,
        "require_fresh_index_observers",
        lambda observed_at: calls.append(observed_at),
    )

    guard(config)

    assert len(calls) == 1


def test_live_command_refuses_backend_before_dependency_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No backend process may start after the selected profile's dependencies fail."""
    from hypervector.cli import build_parser
    from hypervector import cli_cohort

    def reject(_config: object) -> None:
        raise MultiAssetLiveConfigError("required index observer is stale")

    monkeypatch.setattr(cli_cohort, "require_live_provider_dependencies", reject)
    monkeypatch.setattr(
        cli_cohort.subprocess,
        "run",
        lambda *_a, **_k: pytest.fail("spawn after failed dependency"),
    )
    args = build_parser().parse_args(
        ["cohort", "live", "--config", str(_V51), "--enabled", "--i-accept-live-risk"]
    )
    assert cli_cohort.run_cohort_command(args) == 2
