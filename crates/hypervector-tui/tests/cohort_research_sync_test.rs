use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;
use serde_json::{Value, json};

fn checkpoint(status: Option<Value>) -> String {
    let mut value = json!({
        "schema_version":1,"mode":"multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc":"2026-09-07T22:00:00Z",
        "lifecycle":{"state":"running_consistent","cohort_heartbeat_status":"running","asset_states":{"BTC":"FLAT"}},
        "audit":{"coverage":{"complete":true,"technical_gaps":[]},
                 "readiness":{"evaluations":1},"execution":{"closed_trades":0,"net_pnl_usd":0},
                 "learning":{"evidence_state":"no_closed_trade_evidence"}}
    });
    if let Some(status) = status {
        value["research_sync"] = status;
    }
    value.to_string()
}

fn status(state: &str) -> Value {
    json!({
        "schema_version":1,"execution_authority":"none","state":state,
        "in_progress":state == "running",
        "last_attempt_at_utc":"2026-09-07T21:59:00Z",
        "last_success_at_utc":"2026-09-07T21:58:00Z",
        "last_success_age_seconds":120.0,"last_imported_events":0,
        "error":if matches!(state, "failed" | "deferred") { Some("database locked") } else { None }
    })
}

#[test]
fn parses_import_failure_independently_of_live_backend_health() {
    let parsed = parse_cohort_checkpoint(&checkpoint(Some(status("failed")))).expect("checkpoint");
    assert!(parsed.available);
    assert_eq!(
        parsed.lifecycle_state.as_deref(),
        Some("running_consistent")
    );
    let sync = parsed.research_sync.expect("import telemetry");
    assert_eq!(sync.error.as_deref(), Some("database locked"));
    assert_eq!(sync.last_imported_events, Some(0));
    assert_eq!(sync.last_success_age_seconds, Some(120.0));
}

#[test]
fn legacy_status_is_unreported_instead_of_successful() {
    let parsed = parse_cohort_checkpoint(&checkpoint(None)).expect("legacy checkpoint");
    assert!(parsed.research_sync.is_none());
}

#[test]
fn retry_can_retain_an_unresolved_error() {
    let mut value = status("running");
    value["error"] = json!("database locked");
    let parsed = parse_cohort_checkpoint(&checkpoint(Some(value))).expect("retry checkpoint");
    assert!(parsed.research_sync.expect("sync").in_progress);
}

#[test]
fn malformed_explicit_import_status_is_rejected() {
    for (key, value) in [
        ("schema_version", json!(2)),
        ("execution_authority", json!("hyperliquid_mainnet")),
        ("state", json!("invented")),
        ("in_progress", json!(true)),
        ("last_success_at_utc", json!(null)),
        ("last_success_age_seconds", json!(-1)),
        ("last_imported_events", json!(-1)),
        ("last_attempt_at_utc", json!("not-a-time")),
        ("error", json!(null)),
    ] {
        let mut invalid = status("failed");
        invalid[key] = value;
        assert!(
            parse_cohort_checkpoint(&checkpoint(Some(invalid))).is_err(),
            "accepted {key}"
        );
    }
}

#[test]
fn ready_state_cannot_retain_an_error() {
    let mut invalid = status("ready");
    invalid["error"] = json!("database locked");
    assert!(parse_cohort_checkpoint(&checkpoint(Some(invalid))).is_err());
}

#[test]
fn disabled_state_has_no_fabricated_success_or_attempt() {
    let mut value = status("disabled");
    for key in [
        "last_attempt_at_utc",
        "last_success_at_utc",
        "last_success_age_seconds",
        "last_imported_events",
    ] {
        value[key] = Value::Null;
    }
    assert!(parse_cohort_checkpoint(&checkpoint(Some(value))).is_ok());
    assert!(parse_cohort_checkpoint(&checkpoint(Some(status("disabled")))).is_err());
}
