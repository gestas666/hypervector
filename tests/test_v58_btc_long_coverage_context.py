"""Continuous-ledger attachment tests for the rejected BTC coverage change."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.v58_btc_long_coverage_context import (
    attach_v58_btc_long_coverage_result,
)
from hypervector.research.v58_continuous_cli import build_v58_continuous_parser
from hypervector.research.v58_continuous_generator_paths import (
    v58_continuous_generator_paths,
)

_ROUTE = "liquidity_sweep_long_1h_stop60_target60_v2|BTC"
_CURRENT_HYPOTHESIS = "V58_BTC_15M_TREND_PULLBACK_REACCELERATION_LONG_V1"
_PREVIOUS_HYPOTHESIS = "V58_BTC_SWEEP_PRIMARY_RELAXATION_CAUSAL_REPLAY_V1"


def test_rejected_coverage_change_is_attached_to_active_btc_route(
    tmp_path: Path,
) -> None:
    """A failed challenger must remain visible without changing active authority."""
    source = _result_source(tmp_path)
    report = _report()
    attach_v58_btc_long_coverage_result(report, source, project_root=tmp_path)
    context = report["btc_long_coverage_context"]
    assert context["status"] == "rejected"
    assert context["hypothesis_id"] == _CURRENT_HYPOTHESIS
    assert context["active_route"] == _ROUTE
    assert context["rejected_change"] == "add_trend_pullback_reacceleration_long"
    assert context["live_control_action"] == "retain_unchanged"
    assert context["execution_authority"] == "none"
    assert context["live_change_supported"] is False
    assert context["validation_nominal_candidate_net_pnl_usd"] == -689.25
    btc = report["hypothesis_ledger"][0]
    assert btc["long_coverage_challenger"] == context
    assert btc["rejected_challenger_ids"] == [
        _PREVIOUS_HYPOTHESIS,
        _CURRENT_HYPOTHESIS,
    ]
    assert report["evidence"]["btc_long_coverage_context"]["sha256"]


def test_missing_coverage_result_is_explicitly_unavailable(tmp_path: Path) -> None:
    """Missing evidence cannot look like a passing or absent hypothesis."""
    report = _report()
    attach_v58_btc_long_coverage_result(
        report,
        tmp_path / "missing.json",
        project_root=tmp_path,
    )
    assert report["btc_long_coverage_context"]["status"] == "not_available"
    assert "long_coverage_challenger" not in report["hypothesis_ledger"][0]


def test_live_authority_in_result_is_rejected(tmp_path: Path) -> None:
    """A historical attachment cannot smuggle execution authority."""
    source = _result_source(tmp_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["authority"]["execution_authority"] = "live"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="authority"):
        attach_v58_btc_long_coverage_result(
            _report(),
            source,
            project_root=tmp_path,
        )


def test_continuous_contract_loads_and_hashes_btc_coverage_context() -> None:
    """The recurring consolidator must bind the completed BTC result."""
    args = build_v58_continuous_parser("test").parse_args([])
    assert args.btc_long_coverage_result == Path(
        "docs/research-journal/"
        "v58-btc-trend-pullback-reacceleration-result-20260821-v1.json"
    )
    paths = v58_continuous_generator_paths("scripts/v58_continuous_improvement.py")
    assert Path("src/hypervector/research/v58_btc_long_coverage_context.py") in paths


def _result_source(root: Path) -> Path:
    report = root / "report.json"
    trades = root / "trades.parquet"
    prereg = root / "prereg.json"
    previous = root / "previous-result.json"
    report.write_text("{}", encoding="utf-8")
    trades.write_bytes(b"parquet-evidence")
    prereg.write_text("{}", encoding="utf-8")
    previous.write_text("{}", encoding="utf-8")
    source = root / "result.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "cohort_strategy_result_v1",
                "hypothesis_id": _CURRENT_HYPOTHESIS,
                "status": "rejected",
                "supersedes": [_PREVIOUS_HYPOTHESIS],
                "authority": {
                    "report_only": True,
                    "execution_authority": "none",
                    "live_configuration_changed": False,
                    "live_process_changed": False,
                    "automatic_promotion": False,
                    "retuning_authorized": False,
                },
                "decision": {
                    "accepted_for_next_validation_stage": False,
                    "disposition": "reject_frozen_candidate",
                    "retain_live_control_unchanged": True,
                    "nearby_retuning_allowed": False,
                    "live_change_recommended": False,
                },
                "chronological_results": {
                    "validation": {
                        "nominal_candidate": {"net_pnl_usd": -689.25},
                        "nominal_control": {"net_pnl_usd": 36.15},
                        "shared_current_v58_nominal_incremental_net_pnl_usd": -188.65,
                    },
                    "pseudo_holdout": {
                        "nominal_candidate": {"net_pnl_usd": -549.21},
                        "nominal_control": {"net_pnl_usd": 99.02},
                        "shared_current_v58_nominal_incremental_net_pnl_usd": -311.17,
                    },
                },
                "evidence": {
                    "report": {"path": str(report), **file_evidence(report)},
                    "trade_sidecar": {"path": str(trades), **file_evidence(trades)},
                    "preregistration": {"path": str(prereg), **file_evidence(prereg)},
                    "previous_result": {
                        "path": str(previous),
                        **file_evidence(previous),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return source


def _report() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
        },
        "hypothesis_ledger": [{"route": _ROUTE, "symbol": "BTC"}],
        "evidence": {},
    }
