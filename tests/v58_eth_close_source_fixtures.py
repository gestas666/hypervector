"""Source-bound fixtures for the V58 ETH live-close reconciler tests."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from v58_eth_close_ledger_fixtures import ActiveCloseFixture, ClosedContextFixture


def source_files(tmp_path: Path) -> dict[str, object]:
    """Write one complete source-bound close-reconciliation fixture bundle."""
    return _source_bundle(tmp_path)


def _base_source_files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    live = tmp_path / "eth.jsonl"
    observer = tmp_path / "observer.jsonl"
    config = tmp_path / "v58.toml"
    manifest = tmp_path / "manifest.json"
    live.write_bytes(_jsonl({"event_type": "frozen_entry_prefix"}))
    observer.write_bytes(_jsonl({"event_type": "frozen_observer_prefix"}))
    config.write_text("profile = 'v58'\n", encoding="utf-8")
    manifest.write_text('{"status":"verified"}\n', encoding="utf-8")
    return live, observer, config, manifest


def _source_bundle(tmp_path: Path) -> dict[str, object]:
    live, observer, config, manifest = _base_source_files(tmp_path)
    preregistration_path = _write_preregistration(
        tmp_path, live, observer, config, manifest
    )
    with live.open("ab") as stream:
        for row in ActiveCloseFixture.rows:
            stream.write(_jsonl(row))
    continuous = _write_json(
        tmp_path / "continuous.json",
        {
            "contract": preregistration()["contract"],
            "eth_risk_normalized_lock_context": deepcopy(ClosedContextFixture.value),
        },
    )
    venue = _write_json(tmp_path / "venue.json", flat_venue())
    observer_status = _write_json(tmp_path / "observer_status.json", _status())
    observer_provenance = _write_json(
        tmp_path / "observer_provenance.json", observer_window_provenance()
    )
    return {
        "preregistration": preregistration_path,
        "preregistration_sha256": file_evidence(preregistration_path)["sha256"],
        "continuous": continuous,
        "venue": venue,
        "observer_status": observer_status,
        "observer_provenance": observer_provenance,
        "observer_provenance_sha256": file_evidence(observer_provenance)["sha256"],
    }


def _write_preregistration(
    tmp_path: Path, live: Path, observer: Path, config: Path, manifest: Path
) -> Path:
    payload = preregistration() | {
        "source_prefixes": {
            "live_eth_ledger": _prefix_evidence(live),
            "prospective_observer_ledger": _prefix_evidence(observer),
            "config": {"path": str(config), **file_evidence(config)},
            "prestart_manifest": {"path": str(manifest), **file_evidence(manifest)},
        },
        "comparison_evidence": {
            "native_exit_disposition": {"path": str(config), **file_evidence(config)},
            "component_decay_result": {"path": str(config), **file_evidence(config)},
        },
    }
    return _write_json(tmp_path / "preregistration.json", payload)


def _status() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "actual_orders_or_fills_claimed": False,
        },
        "latest_executions": [observer_resolution()],
    }


def preregistration() -> dict[str, object]:
    """Return the exact report-only frozen V58 ETH lifecycle identity."""
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "performance_gate": False,
            "runtime_strategy_changed": False,
            "approval_requested": False,
        },
        "frozen_identity": {
            "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
            "profile_fingerprint": (
                "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
            ),
            "run_id": "bidirectional-live-1787166474078",
            "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
            "route": "eth_breakout_precompression_pullback_bidirectional_v1|ETH",
            "symbol": "ETH",
            "side": "long",
            "lifecycle_id": "ETH:520161109446",
        },
    }


def flat_venue() -> dict[str, object]:
    """Return exact authority-none, flat, order-free ETH venue evidence."""
    return {
        "observed_at_utc": "2026-08-20T08:55:05+00:00",
        "authority": {
            "execution_authority": "none",
            "execution_client_constructed": False,
            "signing_key_required": False,
            "operation": "multi_asset_read_only_preflight",
        },
        "identity": {
            "active_profile_id": (
                "multi_asset_growth_first_5000_eight_asset_incremental_v58"
            ),
            "active_profile_fingerprint": (
                "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
            ),
            "network": "mainnet",
        },
        "assets": [
            {
                "symbol": "ETH",
                "position": {"size_signed": 0.0},
                "open_orders": [],
                "ledger_reconciliation": {
                    "matches": True,
                    "orders_match": True,
                    "position_matches": True,
                    "venue_owned_order_ids": [],
                },
            }
        ],
    }


def observer_resolution() -> dict[str, object]:
    """Return the exact report-only prospective observer resolution."""
    return {
        "status": "resolved",
        "source_run_id": "bidirectional-observe-1787127644202",
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "side": "long",
        "decision_time_ms": 1787172900000,
        "entry_time_ms": 1787172924861,
        "exit_time_ms": 1787216102500,
        "exit_reason": "maximum_hold",
        "entry_notional_usd": 750.0,
        "net_return_scope": "exact_depth_fee_and_funding",
        "net_return_bps": 240.0,
        "simulated_net_pnl_usd": 18.0,
    }


def observer_window_provenance() -> dict[str, object]:
    """Return the frozen observer-window technical disposition."""
    return {
        "schema_version": 1,
        "status": "aggregate_window_invalid_exact_lifecycle_separately_attributable",
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "live_configuration_changed": False,
            "runtime_strategy_changed": False,
            "automatic_promotion": False,
        },
        "observer_run": {
            "run_id": "bidirectional-observe-1787127644202",
            "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
            "profile_fingerprint": (
                "24820e4bfad8a978a7b617a29dc0326f8fc0e583389b67e0219ce4ab5789c874"
            ),
            "run_fingerprint": (
                "1812cbfd3ad4b3f9b939c21c45caa38155e48ca78ddb205e68d68c9dd9b8f1d8"
            ),
        },
        "technical_reclassification": {
            "complete": False,
            "technical_gaps": ["observer_heartbeat_gap_exceeds_entry_delay"],
            "maximum_heartbeat_gap_seconds": 4142.35276,
            "minimum_entry_delay_seconds": 30.0,
        },
        "implementation_continuity": {
            "single_implementation_window": False,
            "changed_sources": [
                "src/hypervector/operations/multi_asset_bidirectional_observe.py",
                "src/hypervector/live/multi_asset_observer_runner.py",
            ],
        },
        "claim_scope": {
            "aggregate_profitability_claim_supported": False,
            "exact_lifecycle_comparison_supported": True,
            "exact_lifecycle_requirements": [
                "separately_frozen_identity",
                "post_resume_decision",
                "exact_fills_fees_funding_and_cleanup",
            ],
        },
    }


def _prefix_evidence(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "path": str(path),
        "prefix_bytes": len(content),
        "prefix_sha256": sha256(content).hexdigest(),
    }


def _jsonl(value: dict[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def _write_json(path: Path, value: dict[str, object]) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path
