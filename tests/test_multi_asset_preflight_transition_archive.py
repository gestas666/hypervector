"""Transition-archive truth for the execution-incapable cohort preflight."""

from __future__ import annotations

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)

_SCRIPT = Path("scripts/multi_asset_bidirectional_preflight.py")
_V77 = Path(
    "configs/multi_asset_growth_first_5000_"
    "seven_asset_btc_component_exit_repair_v77.toml"
)
_V78 = Path(
    "configs/multi_asset_growth_first_5000_"
    "seven_asset_sndk_canary_sizing_repair_v78.toml"
)


def test_missing_archive_cannot_report_transition_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flat venue truth cannot hide a missing prior-run transition archive."""
    module = _load_module()
    active, candidate = _configs(tmp_path)
    _approve(module, monkeypatch)

    report = module._attach_profile_change_evidence(
        _ready_report(), candidate, active, "prior-run"
    )

    assert report["profile_transition_archive"]["state"] == (
        "blocked_profile_transition_archive"
    )
    portfolio = report["portfolio"]
    assert portfolio["technically_ready_for_profile_transition"] is False
    assert "completed drain archive" in portfolio["readiness_reasons"][-1]


def test_exact_legacy_archive_satisfies_preflight_transition_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preflight and live startup must accept the same exact flat boundary."""
    module = _load_module()
    active, candidate = _configs(tmp_path)
    archive = _archive_path(tmp_path)
    archive.parent.mkdir(parents=True)
    archive.write_text(
        json.dumps(_archive_payload(active)),
        encoding="utf-8",
    )
    _approve(module, monkeypatch)

    report = module._attach_profile_change_evidence(
        _ready_report(), candidate, active, "prior-run"
    )

    evidence = report["profile_transition_archive"]
    assert evidence["state"] == "validated_legacy_flat_stop_archive"
    assert evidence["archive_path"] == str(archive)
    assert report["portfolio"]["technically_ready_for_profile_transition"] is True


def _load_module() -> ModuleType:
    spec = spec_from_file_location("preflight_transition_archive", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _configs(tmp_path: Path) -> tuple[MultiAssetLiveConfig, MultiAssetLiveConfig]:
    active = load_multi_asset_live_config(_V77, mode="observe")
    loaded = load_multi_asset_live_config(_V78, mode="observe")
    candidate = replace(
        loaded,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    return active, candidate


def _approve(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "_profile_change_approval_evidence",
        lambda *_args: {
            "state": "approved_profile_change",
            "approval_status": "approved_for_live_transition",
            "execution_authority": "none",
        },
    )


def _ready_report() -> dict[str, object]:
    return {
        "portfolio": {
            "technically_ready_for_profile_transition": True,
            "readiness_reasons": (),
        }
    }


def _archive_path(root: Path) -> Path:
    return root / "data/backups/bidirectional_cohort/legacy_STOP_v77_prior-run.json"


def _archive_payload(config: MultiAssetLiveConfig) -> dict[str, object]:
    return {
        "schema_version": 1,
        "reason": "legacy_flat_transition",
        "run_id": "prior-run",
        "profile_fingerprint": config.profile_fingerprint,
        "observed_at_utc": "2026-09-02T00:51:57+00:00",
        "symbols": list(config.symbols),
        "source_sequence": 516204,
    }
