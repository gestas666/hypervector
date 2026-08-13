use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;

#[test]
fn fresh_sidecar_preserves_stale_execution_backend_truth() {
    let mut checkpoint = base_checkpoint();
    checkpoint["lifecycle"]["state"] = "backend_heartbeat_stale".into();
    checkpoint["lifecycle"]["backend_process_health"] = "stale".into();
    checkpoint["lifecycle"]["cohort_heartbeat_age_seconds"] = 65.0.into();

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("live checkpoint");

    assert!(parsed.available);
    assert!(parsed.stale);
    assert_eq!(
        parsed.issue.as_deref(),
        Some("execution backend heartbeat has not advanced for more than 60s")
    );
}

#[test]
fn terminal_runtime_fault_is_never_projected_as_available_health() {
    let mut checkpoint = base_checkpoint();
    checkpoint["lifecycle"]["state"] = "backend_runtime_fault".into();

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("live checkpoint");

    assert!(parsed.stale);
    assert_eq!(
        parsed.issue.as_deref(),
        Some("execution backend reported a terminal runtime fault")
    );
}

fn base_checkpoint() -> serde_json::Value {
    serde_json::json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-08T08:36:00+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"ETH": "OPEN"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 10},
            "execution": {"closed_trades": 1, "open_lifecycles": 1, "net_pnl_usd": 0.02},
            "learning": {"evidence_state": "descriptive_trade_evidence"}
        }
    })
}
