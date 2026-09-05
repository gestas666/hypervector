"""Fail-closed startup coverage for required v51 index observers."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live import cohort_tui_commands
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)

_ROOT = Path(__file__).parents[1]
_SCRIPT = _ROOT / "scripts" / "multi_asset_bidirectional_canary_tui.py"
_V51 = (
    _ROOT
    / "configs"
    / "multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)


def _load_script() -> ModuleType:
    spec = spec_from_file_location("v51_observer_guard_launcher", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v51_dependency_guard_checks_exact_index_observers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A profile containing fresh15 v3 must prove both observers are fresh."""
    guard = getattr(cohort_tui_commands, "require_live_provider_dependencies", None)
    assert callable(guard), "required live dependency guard is missing"
    config = load_multi_asset_live_config(_V51, mode="observe")
    calls: list[object] = []
    monkeypatch.setattr(
        cohort_tui_commands,
        "require_fresh_index_observers",
        lambda observed_at: calls.append(observed_at),
    )

    guard(config)

    assert len(calls) == 1


def test_live_supervisor_refuses_backend_before_dependency_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No backend process may start after the dependency guard rejects."""
    module = _load_script()
    started: list[tuple[object, ...]] = []

    def reject(_config: object) -> None:
        raise MultiAssetLiveConfigError("required index observer is stale")

    monkeypatch.setattr(
        cohort_tui_commands, "require_live_provider_dependencies", reject, raising=False
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *args, **_kwargs: started.append(args) or object(),
    )

    with pytest.raises(MultiAssetLiveConfigError, match="observer is stale"):
        module.resolve_launch(
            module.build_parser().parse_args(
                ["--mode", "live", "--enabled", "--i-accept-live-risk"]
            ),
            credentials_present=True,
        )

    assert started == []
