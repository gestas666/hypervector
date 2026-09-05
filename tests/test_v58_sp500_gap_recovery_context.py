"""Source-bound tests for the V58 SP500 recovered-gap context."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

_MODULE = Path("src/hypervector/research/v58_sp500_gap_recovery_context.py")


def test_loads_only_unresolved_report_only_recovery(tmp_path: Path) -> None:
    """Recovered marks must not erase the missing prospective decision."""
    module = _module()
    report_path = tmp_path / "report.json"
    journal_path = tmp_path / "journal.json"
    _write(report_path, _report())
    _write(journal_path, _journal(_digest(report_path)))

    context = module.load_v58_sp500_gap_recovery_context(report_path, journal_path)
    payload = module.sp500_gap_recovery_context_payload(context)

    assert payload["disposition"] == "OPEN_LIFECYCLE_CENSORED_DECISION_GAP"
    assert payload["mark_risk_path_resolved"] is True
    assert payload["historical_candle_path_resolved"] is True
    assert payload["prospective_decision_path_resolved"] is False
    assert payload["full_lifecycle_path_resolved"] is False
    assert payload["pnl_claimed"] is False
    assert payload["strategy_change_supported"] is False
    assert payload["execution_authority"] == "none"


def test_rejects_journal_without_exact_report_hash(tmp_path: Path) -> None:
    """A disposition cannot summarize a different recovery artifact."""
    module = _module()
    report_path = tmp_path / "report.json"
    journal_path = tmp_path / "journal.json"
    _write(report_path, _report())
    _write(journal_path, _journal("f" * 64))

    with pytest.raises(ValueError, match="not source-bound"):
        module.load_v58_sp500_gap_recovery_context(report_path, journal_path)


def test_rejects_success_shaped_full_lifecycle_resolution(tmp_path: Path) -> None:
    """The immutable decision censor cannot be silently rewritten as resolved."""
    module = _module()
    report_path = tmp_path / "report.json"
    journal_path = tmp_path / "journal.json"
    report = _report()
    technical = report["technical_assessment"]
    assert isinstance(technical, dict)
    technical["full_lifecycle_path_resolved"] = True
    _write(report_path, report)
    _write(journal_path, _journal(_digest(report_path)))

    with pytest.raises(ValueError, match="technical disposition"):
        module.load_v58_sp500_gap_recovery_context(report_path, journal_path)


def test_adds_prior_mechanism_compatible_short_without_pooling_pnl(
    tmp_path: Path,
) -> None:
    """Prior v51 return evidence must not become V58 portfolio PnL."""
    module = _module()
    report_path, journal_path = _recovery_sources(tmp_path)
    history = _source_history(tmp_path)

    context = module.load_v58_sp500_gap_recovery_context(
        report_path,
        journal_path,
        source_history_journal=history,
        expected_history_journal_sha256=_digest(history),
    )
    payload = module.sp500_gap_recovery_context_payload(context)
    summary = payload["mechanism_compatible_lifecycle_summary"]

    assert summary["observed_lifecycles"] == 2
    assert summary["resolved_lifecycles"] == 1
    assert summary["technically_censored_lifecycles"] == 1
    assert summary["short_lifecycles"] == 2
    assert summary["long_lifecycles"] == 0
    assert summary["prior_resolved_net_return_bps"] == pytest.approx(6.462534641678117)
    assert summary["prior_resolved_net_pnl_usd"] == pytest.approx(3.229665)
    assert summary["pnl_aggregation_supported"] is False
    assert summary["strategy_change_supported"] is False


def test_rejects_changed_prior_sp500_audit(tmp_path: Path) -> None:
    """Changed prior execution evidence must invalidate cumulative counts."""
    module = _module()
    report_path, journal_path = _recovery_sources(tmp_path)
    history = _source_history(tmp_path)
    payload = json.loads(history.read_text(encoding="utf-8"))
    audit = (history.parent / payload["evidence"][0]["path"]).resolve()
    audit.write_bytes(audit.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="source audit identity"):
        module.load_v58_sp500_gap_recovery_context(
            report_path,
            journal_path,
            source_history_journal=history,
            expected_history_journal_sha256=_digest(history),
        )


def _recovery_sources(tmp_path: Path) -> tuple[Path, Path]:
    report_path = tmp_path / "report.json"
    journal_path = tmp_path / "journal.json"
    _write(report_path, _report())
    _write(journal_path, _journal(_digest(report_path)))
    return report_path, journal_path


def _source_history(tmp_path: Path) -> Path:
    audit = tmp_path / "prior-audit.json"
    audit.write_text("{}", encoding="utf-8")
    lifecycle = {
        "status": "resolved",
        "side": "short",
        "entry_notional_usd": 4997.5206,
        "realized_net_return_bps": 6.462534641678117,
        "net_pnl_usd": 3.229665,
    }
    journal = tmp_path / "v51-sp500-fresh15-v3-live-lifecycle-v2.json"
    _write(journal, _history_payload(audit, lifecycle))
    return journal


def _history_payload(audit: Path, lifecycle: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "hypothesis_id": "v51-sp500-fresh15-v3-live-lifecycle-v1",
        "revision_number": 2,
        "status": "retain",
        "symbol": "xyz:SP500",
        "strategy_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "metrics": {
            "eligible_signals": 1,
            "exact_long_lifecycles": 0,
            "exact_short_lifecycles": 1,
            "resolved_lifecycles": 1,
            "wins": 1,
            "losses": 0,
            "net_pnl_usd": 3.229665,
        },
        "resolved_short_lifecycle": lifecycle,
        "scope": {"exit_venue_time_ms": 1786806907361},
        "route_contract": {
            "source_timeframe": "15m",
            "maximum_pressure_age_seconds": 15,
            "stop_bps": 80,
            "maximum_hold_seconds": 86400,
            "profit_lock": {
                "activation_bps": 100,
                "floor_bps": 40,
                "trailing_giveback_bps": 80,
            },
        },
        "evidence": [
            {
                "path": audit.name,
                "role": "immutable exact-profile audit resolving the first source-native v51 SP500 lifecycle",
                "bytes": audit.stat().st_size,
                "sha256": _digest(audit),
            }
        ],
    }


def _module() -> ModuleType:
    assert _MODULE.is_file(), "V58 SP500 recovery context module is missing"
    spec = spec_from_file_location("v58_sp500_gap_recovery_context_test", _MODULE)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _report() -> dict[str, object]:
    return {
        "schema_version": "sp500_fresh15_gap_recovery_v1",
        "symbol": "xyz:SP500",
        "lifecycle": {
            "decision_time_ms": 1787120100000,
            "entry_time_ms": 1787120101436,
            "side": "short",
        },
        "mark_recovery": {
            "complete": True,
            "observations": 260,
            "maximum_gap_ms": 3165,
            "stop_crossed": False,
        },
        "decision_recovery": {
            "expected_boundaries_ms": [1787125500000],
            "missing_boundaries_ms": [1787125500000],
            "prospective_complete": False,
        },
        "technical_assessment": {
            "mark_risk_path_resolved": True,
            "historical_candle_path_resolved": True,
            "prospective_decision_path_resolved": False,
            "full_lifecycle_path_resolved": False,
            "live_change_supported": False,
        },
        "disposition": "OPEN_LIFECYCLE_CENSORED_DECISION_GAP",
        "execution_authority": "none",
        "report_only": True,
        "orders_supported": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _journal(report_sha: str) -> dict[str, object]:
    return {
        "schema_version": (
            "hypervector.v58_sp500_outage_mark_gap_recovery_disposition.v2"
        ),
        "hypothesis_id": "v57-sp500-fresh15-v3-source-native-lifecycle-v1",
        "status": "OPEN_LIFECYCLE_CENSORED_DECISION_GAP",
        "frozen_lifecycle": {
            "symbol": "xyz:SP500",
            "provider_id": (
                "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
            ),
            "decision_time_ms": 1787120100000,
            "entry_time_ms": 1787120101436,
            "side": "short",
        },
        "remaining_censoring": {
            "missing_prospective_decision_boundaries_ms": [1787125500000],
            "mark_risk_path_resolved": True,
            "historical_candle_path_resolved": True,
            "prospective_decision_path_resolved": False,
            "full_lifecycle_path_resolved": False,
            "pnl_claimed": False,
        },
        "hypothesis_ledger_update": {
            "route": (
                "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3|xyz:SP500"
            ),
            "experiment": "first_exact_source_native_lifecycle_per_side",
            "status": "being_tested",
            "minimum_additional_evidence": "exact configured exit and both sides",
            "automatic_live_change": False,
        },
        "source_evidence": [
            {
                "path": "data/logs/research/recovery.json",
                "sha256": report_sha,
            }
        ],
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "orders_supported": False,
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "live_configuration_changed": False,
        },
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
