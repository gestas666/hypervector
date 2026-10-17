"""Integration tests for native-HYPE improvement telemetry."""

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
import math
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

import pytest

from test_cohort_hype_native_lifecycle_status import _open_status

_SCRIPT = Path("scripts/cohort_improvement_monitor.py")


def test_monitor_defaults_to_the_exact_native_hype_lifecycle_status() -> None:
    """The continuous tracker must not silently omit the active v54 evidence."""
    module = _load_script()
    args = module.build_parser().parse_args([])

    assert args.hype_native_lifecycle_status == Path(
        "data/runtime/research/hype_native_v54_prospective_lifecycle_latest.json"
    )
    assert args.maximum_hype_native_lifecycle_age_seconds == 90.0


@pytest.mark.evidence
def test_refresh_attaches_native_hype_status_and_exact_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current improvement artifact must expose the live native-HYPE path."""
    module = _load_script()
    now = datetime.now(UTC)
    checkpoint = tmp_path / "checkpoint.json"
    overrides = tmp_path / "overrides.json"
    status_path = tmp_path / "hype.json"
    output = tmp_path / "latest.json"
    history = tmp_path / "history.jsonl"
    checkpoint.write_text(json.dumps(_checkpoint(now)), encoding="utf-8")
    overrides.write_text(json.dumps(_overrides()), encoding="utf-8")
    status = _open_status()
    status["observed_at_ms"] = int(now.timestamp() * 1_000)
    status_path.write_text(json.dumps(status), encoding="utf-8")
    _install_fakes(module, monkeypatch)
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--decision-overrides",
            str(overrides),
            "--hype-native-lifecycle-status",
            str(status_path),
            "--out",
            str(output),
            "--history",
            str(history),
            "--once",
        ]
    )

    report = module.refresh(args)

    native = report["hype_native_prospective_lifecycle"]
    assert native["current_open_lifecycle"]["peak_giveback_bps"] == 35.0
    assert native["native_only_opportunities"] == 2
    assert native["baseline_comparisons"][0]["baseline_eligible"] is False
    evidence = report["evidence"]["hype_native_prospective_lifecycle"]
    assert evidence["sha256"]


def test_monitor_rejects_nonfinite_native_hype_age_limit() -> None:
    """NaN cannot make challenger freshness comparisons silently false."""
    module = _load_script()
    args = module.build_parser().parse_args([])
    args.maximum_hype_native_lifecycle_age_seconds = math.nan

    with pytest.raises(ValueError, match="maximum HYPE lifecycle age"):
        module._validate_loop_args(args)


def _checkpoint(now: datetime) -> dict[str, object]:
    return {
        "generated_at_utc": now.isoformat(),
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
        "audit": {
            "run": {
                "run_id": "run-v57",
                "profile_id": "multi_asset_growth_first_5000_spcx_short_containment_v57",
                "profile_fingerprint": "a" * 64,
                "executable_provider_symbols": [
                    "hype_breakout_compression_alignment_bidirectional_v2|HYPE"
                ],
            }
        },
    }


def _overrides() -> dict[str, object]:
    return {
        "source_profile_id": "multi_asset_growth_first_5000_spcx_short_containment_v57",
        "source_profile_fingerprint": "a" * 64,
        "routes": {},
        "evidence": [],
    }


def _install_fakes(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "_load_index_mark_capture",
        lambda *_args, **_kwargs: SimpleNamespace(status={}, evidence=None),
    )
    monkeypatch.setattr(module, "_load_index_signals", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_load_sol_observer", lambda *_args: None)
    monkeypatch.setattr(module, "_external_assets_for_profile", lambda *_args: None)
    monkeypatch.setattr(module, "append_material_report", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "_build_report",
        lambda *_args: {
            "contract": {"report_only": True, "execution_authority": "none"},
            "assessment": {"top_research_priority": "compression|HYPE"},
            "performance": {"closed_trades": 0},
            "source": {"run_id": "run-v57"},
        },
    )


def _load_script() -> ModuleType:
    spec = spec_from_file_location("cohort_improvement_monitor_hype", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
