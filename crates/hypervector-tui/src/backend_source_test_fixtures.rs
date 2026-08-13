//! Focused fixtures for file-backed telemetry source tests.

use std::fs;
use std::path::Path;

use crate::backend_cohort::CohortFill;
use crate::backend_telemetry::BackendTelemetrySnapshot;

pub(super) fn backend_snapshot(run_id: &str) -> BackendTelemetrySnapshot {
    let mut snapshot = BackendTelemetrySnapshot::disconnected("fixture");
    snapshot.run_id = Some(run_id.into());
    snapshot.profile_id = Some("profile-a".into());
    snapshot.profile_fingerprint = Some("fingerprint-a".into());
    snapshot
}

pub(super) fn write_live_checkpoint(path: &Path, corrected: serde_json::Value, run_id: &str) {
    fs::write(
        path,
        serde_json::json!({
            "schema_version": 1,
            "mode": "multi_asset_bidirectional_live_checkpoint",
            "generated_at_utc": "2026-08-04T03:36:58+00:00",
            "lifecycle": {
                "state": "running_consistent",
                "cohort_heartbeat_status": "running",
                "asset_states": {"BTC":"FLAT","ETH":"FLAT","SOL":"FLAT","HYPE":"OPEN"}
            },
            "audit": {
                "run": {"row_count":1,"run_id":run_id,"profile_id":"profile-a","profile_fingerprint":"fingerprint-a"},
                "runtime": {"poll_cycles":1,"poll_interval_seconds":{"count":0,"mean":null,"median":null,"minimum":null,"maximum":null}}, "health": {"faults":0},
                "coverage": {"complete": true, "technical_gaps": []},
                "readiness": {"evaluations": 1},
                "execution": {
                    "closed_trades": 0,
                    "net_pnl_usd": 0.0,
                    "fill_details": [corrected]
                },
                "learning": {"evidence_state": "descriptive_trade_evidence"}
            }
        })
        .to_string(),
    )
    .expect("checkpoint fixture");
}

pub(super) fn cohort_fill(
    slippage_bps: Option<f64>,
    acknowledgement_latency_ms: Option<u64>,
    strategy_id: &str,
) -> CohortFill {
    serde_json::from_value(cohort_fill_value(
        slippage_bps,
        acknowledgement_latency_ms,
        strategy_id,
    ))
    .expect("cohort fill fixture")
}

pub(super) fn cohort_fill_value(
    slippage_bps: Option<f64>,
    acknowledgement_latency_ms: Option<u64>,
    strategy_id: &str,
) -> serde_json::Value {
    serde_json::json!({
        "symbol": "BTC",
        "strategy_id": strategy_id,
        "exit_controller_id": strategy_id,
        "origin_run_id": "bidirectional-live-a",
        "operation": "target",
        "trade_id": 102,
        "oid": 12,
        "venue_timestamp_ms": 1_785_600_030_000_u64,
        "price": 103.0,
        "size": 0.25,
        "side": "A",
        "direction": "Close Long",
        "fee_usd": 0.01,
        "closed_pnl_usd": 0.3,
        "expected_price": 103.0,
        "slippage_bps": slippage_bps,
        "acknowledgement_latency_ms": acknowledgement_latency_ms,
        "markout_bps": null,
        "markout_horizon_ms": null,
        "exit_reason": "target"
    })
}
