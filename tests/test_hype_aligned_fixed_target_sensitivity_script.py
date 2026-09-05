"""Command-boundary tests for the HYPE aligned fixed-target experiment."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_storage import file_evidence

_SCRIPT = Path(__file__).parents[1] / "scripts/hype_aligned_fixed_target_sensitivity.py"
_SPEC = spec_from_file_location("hype_aligned_fixed_target_script", _SCRIPT)
assert _SPEC and _SPEC.loader
script = module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


def _report() -> dict[str, object]:
    return {
        "mode": "hype_compression_breakout_challenger_report_only",
        "compression_alignment_replay": {
            "execution_authority": "none",
            "contract": {
                "frozen_compression_policy_id": "compression_5m50_1m40_pullback",
            },
            "development": {"aligned_only": {"completed_trades": 1}},
            "later_confirmation": {"aligned_only": {"completed_trades": 1}},
        },
    }


def _baseline(tmp_path: Path) -> Path:
    root = tmp_path / "baseline"
    root.mkdir()
    (root / "report.json").write_text(json.dumps(_report()), encoding="utf-8")
    (root / "alignment_development_trades.parquet").write_bytes(b"development")
    (root / "alignment_confirmation_trades.parquet").write_bytes(b"confirmation")
    files = {
        name: file_evidence(root / name)
        for name in (
            "report.json",
            "alignment_development_trades.parquet",
            "alignment_confirmation_trades.parquet",
        )
    }
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "complete": True, "files": files}),
        encoding="utf-8",
    )
    return root


def _sidecar() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cohort": "control",
                "side": "short",
                "entry_time_utc": "2026-01-01T00:00:00Z",
                "exit_time_utc": "2026-01-01T01:00:00Z",
                "entry_price": 100.0,
                "net_return_bps": -50.0,
                "exit_reason": "maximum_hold",
            },
            {
                "cohort": "aligned_only",
                "side": "long",
                "entry_time_utc": "2026-01-02T00:00:00Z",
                "exit_time_utc": "2026-01-02T01:00:00Z",
                "entry_price": 100.0,
                "net_return_bps": 25.0,
                "exit_reason": "maximum_hold",
            },
        ]
    )


def test_verified_baseline_rejects_changed_alignment_sidecar(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    report = script.verified_baseline(baseline)
    assert report["compression_alignment_replay"]["execution_authority"] == "none"

    (baseline / "alignment_development_trades.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError, match="evidence"):
        script.verified_baseline(baseline)


def test_selected_trades_retains_only_exact_aligned_cohort() -> None:
    selected = script.selected_trades(_sidecar(), expected=1, confirmation=False)

    assert len(selected) == 1
    assert selected.iloc[0]["cohort"] == "aligned_only"
    assert selected.iloc[0]["side"] == "long"


def test_confirmation_rejects_censored_aligned_lifecycle() -> None:
    frame = _sidecar().assign(segment=1, censored=False)
    frame.loc[frame["cohort"].eq("aligned_only"), "censored"] = True

    with pytest.raises(ValueError, match="censored"):
        script.selected_trades(frame, expected=1, confirmation=True)


def test_execution_config_matches_live_v52_hype_contract() -> None:
    config = script.execution_config()
    assert config.stop_bps == 80.0
    assert config.maximum_hold_minutes == 480
    assert config.maximum_hold_policy == "extend_while_regime_supported"
    assert config.hard_maximum_hold_minutes == 1_440
    assert config.exit_on_opposite_signal is True


def test_script_has_no_live_execution_import() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "hypervector.live" not in source
    assert "execution_authority" in source
