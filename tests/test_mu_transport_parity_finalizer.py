"""Tests for the fixed-window MU transport-parity finalizer."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hypervector.research.mu_transport_parity_finalizer import (
    assess_decision_parity,
    load_window_spec,
    read_observer_progress,
    validate_frozen_generators,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def test_load_window_spec_binds_exact_predeclared_window(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    _write_json(source, {"contract": "report-only"})
    source_hash = sha256(source.read_bytes()).hexdigest()
    prereg = tmp_path / "window.json"
    _write_json(
        prereg,
        {
            "schema_version": "v52_mu_transport_parity_forward_window_v1",
            "hypothesis_id": "MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V1",
            "scope": {
                "symbol": "xyz:MU",
                "provider_id": "provider",
                "profile_id": "profile",
                "timeframe": "15m",
                "first_decision_ms": 900_000,
                "last_decision_ms": 1_800_000,
                "end_exclusive_ms": 2_700_000,
                "expected_decisions": 2,
            },
            "frozen_sources": {
                "source_journal": {"path": "source.json", "sha256": source_hash},
                "bounded_report_module_sha256": "a" * 64,
                "bounded_report_script_sha256": "b" * 64,
            },
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "promotion_authority": "none",
                "automatic_live_change": False,
                "runtime_strategy_changed": False,
                "no_window_shrinkage": True,
                "no_replacement_window_after_failure": True,
                "no_parameter_retuning_during_window": True,
            },
        },
    )

    spec = load_window_spec(prereg)

    assert spec.symbol == "xyz:MU"
    assert spec.start_ms == 900_000
    assert spec.last_ms == 1_800_000
    assert spec.end_exclusive_ms == 2_700_000
    assert spec.expected_decisions == 2
    assert spec.source_journal == source


def _decision(
    spec: object, decision_time_ms: int, *, eligible: bool
) -> dict[str, object]:
    return {
        "event_type": "mu_hip3_breakout_shadow_decision",
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
        "intents": [],
        "decision": {
            "symbol": spec.symbol,
            "provider_id": spec.provider_id,
            "profile_id": spec.profile_id,
            "decision_time_ms": decision_time_ms,
            "eligible": eligible,
            "side": "short" if eligible else None,
            "prospective": True,
            "execution_authority": "none",
            "pressure_source": "hyperliquid_mainnet_l2_rest",
            "pressure_state_history_complete": True,
            "pressure_fresh": True,
            "pressure_scan_complete": True,
        },
    }


def test_observer_progress_requires_every_exact_decision(tmp_path: Path) -> None:
    prereg = tmp_path / "window.json"
    source = tmp_path / "source.json"
    _write_json(source, {"contract": "report-only"})
    _write_prereg(prereg, source)
    spec = load_window_spec(prereg)
    journal = tmp_path / "observer.jsonl"
    rows = [_decision(spec, spec.start_ms, eligible=False)]
    journal.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    progress = read_observer_progress(journal, spec)

    assert progress.observed_decisions == 1
    assert progress.resolved_decisions == 1
    assert progress.missing_decisions == (spec.last_ms,)
    assert progress.eligible_decisions == 0
    assert progress.complete is False
    assert len(progress.journal_snapshot_sha256) == 64
    assert progress.stable_bytes == journal.stat().st_size
    assert progress.dropped_tail_bytes == 0


def test_observer_progress_rejects_duplicate_decision(tmp_path: Path) -> None:
    prereg = tmp_path / "window.json"
    source = tmp_path / "source.json"
    _write_json(source, {"contract": "report-only"})
    _write_prereg(prereg, source)
    spec = load_window_spec(prereg)
    row = _decision(spec, spec.start_ms, eligible=False)
    journal = tmp_path / "observer.jsonl"
    journal.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")

    with pytest.raises(ValueError, match="duplicate observer decision"):
        read_observer_progress(journal, spec)


def test_frozen_generators_reject_post_start_source_change(tmp_path: Path) -> None:
    root = tmp_path / "root"
    generator = root / "scripts" / "generator.py"
    generator.parent.mkdir(parents=True)
    generator.write_text("frozen\n")
    comparator_script = root / "scripts/hip3_shadow_observer_decision_parity.py"
    comparator_module = (
        root / "src/hypervector/research/hip3_shadow_observer_decision_parity.py"
    )
    comparator_script.write_text("script\n")
    comparator_module.parent.mkdir(parents=True)
    comparator_module.write_text("module\n")
    artifact = tmp_path / "artifact.json"
    _write_json(
        artifact,
        {
            "generator_identity": {
                "scripts/generator.py": {
                    "sha256": sha256(generator.read_bytes()).hexdigest(),
                    "bytes": generator.stat().st_size,
                }
            }
        },
    )
    source = tmp_path / "source.json"
    artifact_evidence = _file_evidence(artifact)
    _write_json(
        source,
        {
            "refreshed_evidence": {
                name: {"path": "artifact.json", **artifact_evidence}
                for name in ("venue_path", "candle_source", "strategy_signal_source")
            }
        },
    )
    prereg = tmp_path / "window.json"
    _write_prereg(
        prereg,
        source,
        report_module_sha256=sha256(comparator_module.read_bytes()).hexdigest(),
        report_script_sha256=sha256(comparator_script.read_bytes()).hexdigest(),
    )
    spec = load_window_spec(prereg)
    validate_frozen_generators(spec, root)

    generator.write_text("changed\n")

    with pytest.raises(ValueError, match="generator changed"):
        validate_frozen_generators(spec, root)


def test_v53_window_freezes_prospective_observer_generator(tmp_path: Path) -> None:
    """A new window must reject changed live observer bytes after its start."""
    root, artifact = _generator_artifact(tmp_path)
    source = tmp_path / "source.json"
    evidence = {"path": "artifact.json", **_file_evidence(artifact)}
    _write_json(
        source,
        {
            "refreshed_evidence": {
                key: evidence
                for key in ("venue_path", "candle_source", "strategy_signal_source")
            }
        },
    )
    observer = root / "src/hypervector/live/mu_hip3_breakout_shadow_runner.py"
    observer.parent.mkdir(parents=True)
    observer.write_text("frozen observer\n")
    prereg = tmp_path / "window.json"
    module = root / "src/hypervector/research/hip3_shadow_observer_decision_parity.py"
    script = root / "scripts/hip3_shadow_observer_decision_parity.py"
    _write_prereg(
        prereg,
        source,
        report_module_sha256=sha256(module.read_bytes()).hexdigest(),
        report_script_sha256=sha256(script.read_bytes()).hexdigest(),
    )
    payload = json.loads(prereg.read_text())
    payload["schema_version"] = "v53_mu_transport_parity_forward_window_v1"
    payload["frozen_sources"]["observer_generator_identity"] = [
        {"path": str(observer.relative_to(root)), **_file_evidence(observer)}
    ]
    _write_json(prereg, payload)
    spec = load_window_spec(prereg)

    validate_frozen_generators(spec, root)
    observer.write_text("changed observer\n")

    with pytest.raises(ValueError, match="observer generator changed"):
        validate_frozen_generators(spec, root)


def test_signal_hash_typo_requires_cross_bound_correction(tmp_path: Path) -> None:
    root, artifact = _generator_artifact(tmp_path)
    observer = tmp_path / "observer_parity.json"
    _write_json(
        observer,
        {
            "input_evidence": {
                "signal_parity": {
                    "path": str(artifact.resolve()),
                    **_file_evidence(artifact),
                }
            }
        },
    )
    source = tmp_path / "source.json"
    direct = {"path": "artifact.json", **_file_evidence(artifact)}
    direct["sha256"] = str(direct["sha256"])[2:]
    _write_json(
        source,
        {
            "refreshed_evidence": {
                "venue_path": {"path": "artifact.json", **_file_evidence(artifact)},
                "candle_source": {"path": "artifact.json", **_file_evidence(artifact)},
                "strategy_signal_source": direct,
                "observer_transport": {
                    "path": "observer_parity.json",
                    **_file_evidence(observer),
                },
            }
        },
    )
    prereg = tmp_path / "window.json"
    module = root / "src/hypervector/research/hip3_shadow_observer_decision_parity.py"
    script = root / "scripts/hip3_shadow_observer_decision_parity.py"
    _write_prereg(
        prereg,
        source,
        report_module_sha256=sha256(module.read_bytes()).hexdigest(),
        report_script_sha256=sha256(script.read_bytes()).hexdigest(),
    )
    correction = tmp_path / "correction.json"
    _write_json(correction, _correction_payload(source, artifact, observer, direct))
    spec = load_window_spec(prereg)

    validate_frozen_generators(spec, root, correction_path=correction)

    correction.unlink()
    with pytest.raises(ValueError, match="artifact generator changed"):
        validate_frozen_generators(spec, root)


def _generator_artifact(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "root"
    generator = root / "scripts/generator.py"
    generator.parent.mkdir(parents=True)
    generator.write_text("frozen\n")
    script = root / "scripts/hip3_shadow_observer_decision_parity.py"
    module = root / "src/hypervector/research/hip3_shadow_observer_decision_parity.py"
    script.write_text("script\n")
    module.parent.mkdir(parents=True)
    module.write_text("module\n")
    artifact = tmp_path / "artifact.json"
    _write_json(
        artifact,
        {"generator_identity": {"scripts/generator.py": _file_evidence(generator)}},
    )
    return root, artifact


def _correction_payload(
    source: Path, artifact: Path, observer: Path, direct: dict[str, object]
) -> dict[str, object]:
    return {
        "schema_version": "v52_mu_source_hash_correction_v1",
        "hypothesis_id": "MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V1",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
            "corrects_hash_only": True,
        },
        "source_journal": {"path": str(source.resolve()), **_file_evidence(source)},
        "field": "refreshed_evidence.strategy_signal_source.sha256",
        "incorrect_sha256": direct["sha256"],
        "correct_artifact": {
            "path": str(artifact.resolve()),
            **_file_evidence(artifact),
        },
        "cross_binding_artifact": {
            "path": str(observer.resolve()),
            **_file_evidence(observer),
        },
        "cross_binding_field": "input_evidence.signal_parity",
    }


def test_assessment_enforces_every_predeclared_success_metric(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    _write_json(source, {"contract": "report-only"})
    prereg = tmp_path / "window.json"
    _write_prereg(prereg, source)
    spec = load_window_spec(prereg)
    report = {
        "schema_version": "hip3_shadow_observer_decision_parity_v2",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "promotion_authority": "none",
            "runtime_strategy_changed": False,
        },
        "scope": {
            "symbol": spec.symbol,
            "provider_id": spec.provider_id,
            "profile_id": spec.profile_id,
            "timeframe": "15m",
        },
        "coverage": {
            "comparison_start_ms": spec.start_ms,
            "comparison_end_ms": spec.last_ms,
            "comparison_window_policy": "explicit_requested_bounds",
        },
        "technical_assessment": {
            "comparison_decisions": spec.expected_decisions,
            "missing_observer_decisions": 0,
            "entry_decision_mismatches": 0,
            "non_vacuous_entry_comparison": True,
            "observer_archive_pressure_decision_parity_resolved": True,
        },
    }

    assert assess_decision_parity(report, spec) == ("PASS", ())
    report["technical_assessment"]["non_vacuous_entry_comparison"] = False

    assert assess_decision_parity(report, spec) == (
        "FAIL",
        ("non_vacuous_entry_comparison",),
    )


def _write_prereg(
    path: Path,
    source: Path,
    *,
    report_module_sha256: str = "a" * 64,
    report_script_sha256: str = "b" * 64,
) -> None:
    source_hash = sha256(source.read_bytes()).hexdigest()
    _write_json(
        path,
        {
            "schema_version": "v52_mu_transport_parity_forward_window_v1",
            "hypothesis_id": "MU_BREAKOUT_PRESSURE_TRANSPORT_PARITY_FORWARD_V1",
            "scope": {
                "symbol": "xyz:MU",
                "provider_id": "provider",
                "profile_id": "profile",
                "timeframe": "15m",
                "first_decision_ms": 900_000,
                "last_decision_ms": 1_800_000,
                "end_exclusive_ms": 2_700_000,
                "expected_decisions": 2,
            },
            "frozen_sources": {
                "source_journal": {"path": "source.json", "sha256": source_hash},
                "bounded_report_module_sha256": report_module_sha256,
                "bounded_report_script_sha256": report_script_sha256,
            },
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "promotion_authority": "none",
                "automatic_live_change": False,
                "runtime_strategy_changed": False,
                "no_window_shrinkage": True,
                "no_replacement_window_after_failure": True,
                "no_parameter_retuning_during_window": True,
            },
        },
    )


def _file_evidence(path: Path) -> dict[str, object]:
    return {
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }
