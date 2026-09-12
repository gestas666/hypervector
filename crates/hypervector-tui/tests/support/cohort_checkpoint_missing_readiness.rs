#[test]
fn stopped_recovery_keeps_accounting_without_provider_evaluations() {
    let document = checkpoint_without_readiness();
    let parsed = parse_cohort_checkpoint(&document.to_string())
        .expect("explicitly missing readiness must preserve the valid checkpoint");
    assert!(parsed.available);
    assert_eq!(parsed.asset_states["HYPE"], "STOPPED");
    assert_eq!(
        parsed.lifecycle_state.as_deref(),
        Some("stale_running_heartbeat_after_asset_stop")
    );
    assert_eq!(parsed.readiness_evaluations, Some(0));
    assert_eq!(parsed.observer_provider_journal.len(), 1);
    let provider = &parsed.observer_provider_journal[0];
    assert_eq!(provider.readiness_evaluations, 0);
    assert_eq!(provider.readiness_fraction, None);
    assert_eq!(provider.latest_side, None);
    assert_eq!(
        provider
            .execution_performance
            .as_ref()
            .unwrap()
            .closed_trades,
        1
    );
}

#[test]
fn missing_readiness_declarations_must_be_exact_and_unique() {
    for missing in [
        json!([]),
        json!(["hype|HYPE", "hype|HYPE"]),
        json!(["unknown|HYPE"]),
    ] {
        let mut document = checkpoint_without_readiness();
        document["audit"]["readiness"]["missing_provider_symbols"] = missing;
        assert!(parse_cohort_checkpoint(&document.to_string()).is_err());
    }
    let mut observed = live_checkpoint();
    observed["audit"]["readiness"]["missing_provider_symbols"] = json!(["hype|HYPE"]);
    assert!(parse_cohort_checkpoint(&observed.to_string()).is_err());
}

fn checkpoint_without_readiness() -> Value {
    let mut document = live_checkpoint();
    document["lifecycle"]["state"] = json!("stale_running_heartbeat_after_asset_stop");
    document["lifecycle"]["asset_states"] = json!({"HYPE": "STOPPED"});
    document["audit"]["readiness"] = json!({
        "evaluations": 0,
        "by_provider_symbol": {},
        "missing_provider_symbols": ["hype|HYPE"]
    });
    document["audit"]["signal_outcomes"] = json!({
        "evaluations": 0,
        "eligible_evaluations": 0,
        "coverage": {"complete": false},
        "by_provider_symbol": {}
    });
    document
}
