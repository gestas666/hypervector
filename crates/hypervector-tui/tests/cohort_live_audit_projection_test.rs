use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;

#[test]
fn live_checkpoint_preserves_routing_and_audit_health_separately() {
    let checkpoint = serde_json::json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-07T01:58:52+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"SOL": "OPEN"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 4342},
            "routing": {"actions": 1, "strategy_intents": 4},
            "runtime": {
                "poll_cycles": 2520,
                "poll_interval_seconds": {
                    "count": 2519,
                    "minimum": 14.426317,
                    "maximum": 23.155777,
                    "mean": 15.433350780468439,
                    "median": 15.367621
                }
            },
            "health": {"faults": 0},
            "run": {
                "row_count": 8218,
                "run_id": "bidirectional-live-current",
                "profile_id": "candidate-v14",
                "profile_fingerprint": "a".repeat(64)
            },
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "learning": {"evidence_state": "no_closed_trade_evidence"}
        }
    });

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("live checkpoint");
    let audit = parsed.live_audit_status.expect("live audit status");

    assert_eq!(parsed.strategy_intents, Some(4));
    assert_eq!(parsed.routing_actions, Some(1));
    assert_eq!(parsed.run_id.as_deref(), Some("bidirectional-live-current"));
    assert_eq!(parsed.profile_id.as_deref(), Some("candidate-v14"));
    assert_eq!(
        parsed.profile_fingerprint.as_deref().map(str::len),
        Some(64)
    );
    assert_eq!(audit.row_count, 8218);
    assert_eq!(audit.faults, 0);
    assert_eq!(audit.poll_cycles, 2520);
    assert_eq!(audit.poll_interval_count, 2519);
    assert!(
        (audit.poll_interval_mean_seconds.expect("mean cadence") - 15.433350780468439).abs()
            < 1e-12
    );
    assert_eq!(audit.poll_interval_median_seconds, Some(15.367621));
    assert_eq!(audit.poll_interval_minimum_seconds, Some(14.426317));
    assert_eq!(audit.poll_interval_maximum_seconds, Some(23.155777));
}
