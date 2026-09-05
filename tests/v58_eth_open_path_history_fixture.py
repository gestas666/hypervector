"""Reusable source-history fixtures for V58 ETH open-path tests."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


def source_history(tmp_path: Path, *, prior_run: str = "prior-exact-run") -> Path:
    """Write one exact prior ETH lifecycle journal and its source artifact."""
    artifact = tmp_path / "eth_pullback_eligible_exact_depth_20260818T1108Z_v2.json"
    lifecycle = _prior_lifecycle(prior_run)
    artifact.write_text(
        json.dumps(_source_artifact_payload(lifecycle, prior_run), sort_keys=True),
        encoding="utf-8",
    )
    evidence = {"path": str(artifact), **_file_evidence(artifact)}
    journal = tmp_path / "eth-breakout-precompression-pullback-v14.json"
    journal.write_text(
        json.dumps(_journal_payload(lifecycle, evidence, prior_run), sort_keys=True),
        encoding="utf-8",
    )
    return journal


def sha256_file(path: Path) -> str:
    """Return the fixture file's lowercase SHA-256 digest."""
    return str(_file_evidence(path)["sha256"])


def _prior_lifecycle(prior_run: str) -> dict[str, object]:
    return {
        "status": "resolved",
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "candidate_strategy_id": (
            "eth_breakout_precompression_pullback_bidirectional_v1_v55_forward"
        ),
        "symbol": "ETH",
        "source_run_id": prior_run,
        "side": "long",
        "decision_time_ms": 100,
        "entry_time_ms": 200,
        "exit_time_ms": 300,
        "entry_price": 1899.9,
        "exit_price": 1888.5,
        "entry_notional_usd": 750.0,
        "position_quantity": 0.39475761882204324,
        "exit_reason": "protective_stop",
        "gross_return_bps": -60.00315806095058,
        "fee_bps": 8.972998578872573,
        "funding_bps": -0.15665900000000002,
        "net_return_bps": -69.13281563982316,
        "simulated_net_pnl_usd": -5.184961172986737,
        "net_return_scope": "exact_depth_fee_and_funding",
    }


def _source_artifact_payload(
    lifecycle: dict[str, object], prior_run: str
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_eligible_exact_visible_depth_forward_report",
        "state": "descriptive_exact_depth_evidence",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "actual_orders_or_fills_claimed": False,
            "portfolio_pnl_claimed": False,
            "source_strategy_id": lifecycle["strategy_id"],
            "candidate_strategy_id": lifecycle["candidate_strategy_id"],
            "symbol": "ETH",
            "source_run_id": prior_run,
            "profile_fingerprint": "prior-profile",
            "compatible_run_ids": [prior_run],
            "stop_bps": 60.0,
            "notional_usd": 750.0,
            "maximum_hold_minutes": 720,
            "taker_fee_rate": 0.00045,
        },
        "identity": {
            "profile_id": "multi_asset_eth_pullback_forward_observer_v1",
            "profile_fingerprint": "prior-profile",
            "source_run_id": prior_run,
            "compatible_run_ids": [prior_run],
        },
        "summary": {"pending": 0, "resolved": 1, "technical_incomplete": 0},
        "latest_attempts": [{"status": "resolved"}],
        "latest_executions": [lifecycle],
    }


def _journal_payload(
    lifecycle: dict[str, object], evidence: dict[str, object], prior_run: str
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "hypothesis_id": "eth-breakout-precompression-pullback",
        "revision_number": 14,
        "status": "first_exact_eligible_lifecycle_adverse",
        "symbol": "ETH",
        "strategy_id": lifecycle["strategy_id"],
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
            "actual_order_or_fill_claimed": False,
        },
        "frozen_identity": {
            "run_id": prior_run,
            "profile_id": "multi_asset_eth_pullback_forward_observer_v1",
            "profile_fingerprint": "prior-profile",
            "side": "long",
            "notional_usd": 750.0,
            "stop_bps": 60.0,
            "maximum_hold_seconds": 43200,
            "taker_fee_rate": 0.00045,
        },
        "exact_forward_lifecycle": lifecycle,
        "source_evidence": [evidence],
    }


def _file_evidence(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
