use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;
use hypervector_tui::cohort_setup_deadline::summary_lines;
use serde_json::{Value, json};

#[path = "support/cohort_entry_deadline_fixtures.rs"]
mod entry_deadline_fixtures;
use entry_deadline_fixtures::fixture;

#[test]
fn sdk_evidence_reaches_the_exact_selected_route() {
    let parsed = parse_cohort_checkpoint(&fixture().to_string()).unwrap();
    let route = &parsed.entry_deadlines.as_ref().unwrap().by_provider_symbol["provider_v1|BTC"];
    assert_eq!(route.sdk_dispatch_checks, Some(1));
    let lines = summary_lines(&parsed, "provider_v1", "BTC").join("\n");
    assert!(lines.contains("SDK DISPATCH CONTRACT OBSERVED"));
    assert!(lines.contains("29000 ms"));
    assert!(lines.contains("RUN AGGREGATE"));
    assert!(
        summary_lines(&parsed, "provider_v1", "ETH")
            .join(" ")
            .contains("UNAVAILABLE")
    );
}

#[test]
fn namespaced_deadline_evidence_keeps_its_exact_venue_symbol() {
    let mut value = fixture();
    let routes = value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]
        .as_object_mut()
        .unwrap();
    let route = routes.remove("provider_v1|BTC").unwrap();
    routes.insert("provider_v1|xyz:SNDK".into(), route);
    let parsed = parse_cohort_checkpoint(&value.to_string()).unwrap();
    assert!(
        summary_lines(&parsed, "provider_v1", "xyz:SNDK")
            .join(" ")
            .contains("SDK DISPATCH CONTRACT OBSERVED")
    );
    assert!(
        summary_lines(&parsed, "provider_v1", "SNDK")
            .join(" ")
            .contains("UNAVAILABLE")
    );
}

#[test]
fn absent_evidence_stays_unavailable() {
    let mut value = fixture();
    value["audit"]["routing"]
        .as_object_mut()
        .unwrap()
        .remove("entry_age_diagnostics");
    let parsed = parse_cohort_checkpoint(&value.to_string()).unwrap();
    assert!(parsed.entry_deadlines.is_none());
    assert!(
        summary_lines(&parsed, "provider_v1", "BTC")
            .join(" ")
            .contains("UNAVAILABLE")
    );
}

fn legacy_fixture() -> Value {
    let mut value = fixture();
    let audit = &mut value["audit"]["routing"]["entry_age_diagnostics"];
    audit.as_object_mut().unwrap().remove("sdk_dispatch_checks");
    let route = audit["by_provider_symbol"]["provider_v1|BTC"]
        .as_object_mut()
        .unwrap();
    for key in [
        "sdk_dispatch_checks",
        "sdk_dispatches_over_limit",
        "adapter_dispatch_checks",
        "admission_or_legacy_checks",
    ] {
        route.remove(key);
    }
    route.insert("status".into(), json!("submission_contract_enforced"));
    value
}

#[test]
fn legacy_enforcement_claim_does_not_become_sdk_proof() {
    let parsed = parse_cohort_checkpoint(&legacy_fixture().to_string()).unwrap();
    let lines = summary_lines(&parsed, "provider_v1", "BTC").join(" ");
    assert!(lines.contains("LEGACY CHECKPOINT"));
    assert!(lines.contains("SDK N/A"));
    assert!(!lines.contains("SDK DISPATCH CONTRACT OBSERVED"));
}

#[test]
fn malformed_and_contradictory_deadline_evidence_is_rejected() {
    for (pointer, replacement) in [
        ("/contract/execution_authority", json!("live")),
        ("/contract/automatic_pause", json!(true)),
        ("/submitted_entries", json!(2)),
        ("/sdk_dispatch_checks", json!(0)),
        (
            "/by_provider_symbol/provider_v1|BTC/sdk_dispatch_checks",
            json!(-1),
        ),
        (
            "/by_provider_symbol/provider_v1|BTC/sdk_dispatches_over_limit",
            json!(2),
        ),
        (
            "/by_provider_symbol/provider_v1|BTC/minimum_submission_headroom_ms",
            json!(900),
        ),
        (
            "/by_provider_symbol/provider_v1|BTC/maximum_submission_age_ms",
            Value::Null,
        ),
        (
            "/by_provider_symbol/provider_v1|BTC/status",
            json!("unknown_stage"),
        ),
    ] {
        let mut value = fixture();
        *value["audit"]["routing"]["entry_age_diagnostics"]
            .pointer_mut(pointer)
            .unwrap() = replacement;
        assert!(
            parse_cohort_checkpoint(&value.to_string()).is_err(),
            "accepted {pointer}"
        );
    }
}

#[test]
fn partial_stage_counters_are_not_a_legacy_fallback() {
    let mut value = fixture();
    value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|BTC"]
        .as_object_mut()
        .unwrap()
        .remove("adapter_dispatch_checks");
    assert!(parse_cohort_checkpoint(&value.to_string()).is_err());
}

#[test]
fn deadline_scope_cannot_exceed_the_parent_routing_count() {
    let mut value = fixture();
    value["audit"]["routing"]["actions"] = json!(0);
    assert!(parse_cohort_checkpoint(&value.to_string()).is_err());
}

#[test]
fn deadline_age_cannot_hide_a_recorded_over_limit_check() {
    let mut value = fixture();
    let route = &mut value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|BTC"];
    route["maximum_submission_age_ms"] = json!(31000);
    route["minimum_submission_headroom_ms"] = json!(-1000);
    assert!(parse_cohort_checkpoint(&value.to_string()).is_err());
}

#[test]
fn deadline_status_cannot_claim_an_unobserved_adapter_check() {
    let mut value = fixture();
    value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|BTC"]["status"] =
        json!("adapter_dispatch_check_observed");
    assert!(parse_cohort_checkpoint(&value.to_string()).is_err());
}

#[test]
fn actual_python_backend_scenarios_keep_their_stage_and_clock_evidence() {
    let examples: Value =
        serde_json::from_str(include_str!("fixtures/cohort_entry_deadline_2030.json")).unwrap();
    for (name, evidence) in examples.as_object().unwrap() {
        let mut value = fixture();
        value["audit"]["routing"]["actions"] = evidence["enter_actions"].clone();
        value["audit"]["routing"]["entry_age_diagnostics"] = evidence.clone();
        let parsed = parse_cohort_checkpoint(&value.to_string())
            .unwrap_or_else(|error| panic!("{name}: {error}"));
        let actual =
            &parsed.entry_deadlines.as_ref().unwrap().by_provider_symbol["provider_v1|BTC"];
        assert_eq!(
            actual.status,
            evidence["by_provider_symbol"]["provider_v1|BTC"]["status"]
                .as_str()
                .unwrap(),
            "{name}"
        );
        assert_eq!(
            actual.sdk_dispatch_checks.unwrap() as u64,
            evidence["sdk_dispatch_checks"].as_u64().unwrap(),
            "{name}"
        );
        let lines = summary_lines(&parsed, "provider_v1", "BTC").join(" ");
        for (field, label) in [
            ("maximum_submission_age_ms", "MAX RECORDED CHECK AGE"),
            ("minimum_submission_headroom_ms", "MIN HEADROOM"),
        ] {
            let value = &evidence["by_provider_symbol"]["provider_v1|BTC"][field];
            let expected = value
                .as_i64()
                .map_or_else(|| "N/A".into(), |v| format!("{v} ms"));
            assert!(
                lines.contains(&format!("{label} {expected}")),
                "{name}: {lines}"
            );
        }
    }
}

#[test]
fn malformed_route_identities_are_rejected_before_display() {
    for identity in [
        "missing_pair",
        "|BTC",
        "provider_v1|",
        "provider_v1|BTC|ETH",
        "provider_v1|\u{001b}BTC",
    ] {
        let mut value = fixture();
        let routes = value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]
            .as_object_mut()
            .unwrap();
        let route = routes.remove("provider_v1|BTC").unwrap();
        routes.insert(identity.into(), route);
        let error = parse_cohort_checkpoint(&value.to_string()).unwrap_err();
        assert!(error.contains("identity"), "{error}");
    }
}

#[test]
fn aggregate_and_route_stage_schemas_must_agree() {
    let mut value = fixture();
    value["audit"]["routing"]["entry_age_diagnostics"]
        .as_object_mut()
        .unwrap()
        .remove("sdk_dispatch_checks");
    let error = parse_cohort_checkpoint(&value.to_string()).unwrap_err();
    assert!(error.contains("stage schema"), "{error}");
}

fn maximum_count_fixture() -> Value {
    let mut value = fixture();
    value["audit"]["routing"]["actions"] = json!(usize::MAX);
    let evidence = &mut value["audit"]["routing"]["entry_age_diagnostics"];
    for field in ["enter_actions", "submitted_entries", "sdk_dispatch_checks"] {
        evidence[field] = json!(usize::MAX);
        evidence["by_provider_symbol"]["provider_v1|BTC"][field] = json!(usize::MAX);
    }
    value
}

#[test]
fn route_counts_cannot_overflow_the_aggregate() {
    let mut value = maximum_count_fixture();
    let extra = fixture()["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|BTC"].clone();
    value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|ETH"] =
        extra;
    let error = parse_cohort_checkpoint(&value.to_string()).unwrap_err();
    assert!(error.contains("count overflow"), "{error}");
}

#[test]
fn stage_partition_cannot_overflow_its_recorded_total() {
    let mut value = maximum_count_fixture();
    value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|BTC"]["adapter_dispatch_checks"] =
        json!(1);
    let error = parse_cohort_checkpoint(&value.to_string()).unwrap_err();
    assert!(error.contains("count overflow"), "{error}");
}

#[test]
fn stale_withholding_counts_cannot_overflow_across_routes() {
    let mut value = fixture();
    value["audit"]["routing"]["actions"] = json!(2);
    let evidence = &mut value["audit"]["routing"]["entry_age_diagnostics"];
    for field in ["enter_actions", "submitted_entries", "sdk_dispatch_checks"] {
        evidence[field] = json!(2);
    }
    evidence["stale_entries_withheld"] = json!(usize::MAX);
    let route = &mut evidence["by_provider_symbol"]["provider_v1|BTC"];
    route["stale_entries_withheld"] = json!(usize::MAX);
    route["maximum_withheld_submission_age_ms"] = json!(31000);
    let mut extra = route.clone();
    extra["stale_entries_withheld"] = json!(1);
    evidence["by_provider_symbol"]["provider_v1|ETH"] = extra;
    let error = parse_cohort_checkpoint(&value.to_string()).unwrap_err();
    assert!(error.contains("count overflow"), "{error}");
}

#[test]
fn a_recorded_age_requires_its_matching_headroom() {
    let mut value = fixture();
    value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|BTC"]["minimum_submission_headroom_ms"] =
        Value::Null;
    let error = parse_cohort_checkpoint(&value.to_string()).unwrap_err();
    assert!(error.contains("lacks age or headroom"), "{error}");
}

#[test]
fn legacy_schema_cannot_claim_a_named_sdk_status() {
    let mut value = legacy_fixture();
    value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|BTC"]["status"] =
        json!("sdk_dispatch_contract_observed");
    let error = parse_cohort_checkpoint(&value.to_string()).unwrap_err();
    assert!(error.contains("legacy entry deadline"), "{error}");
}

#[test]
fn an_unobserved_check_cannot_claim_sdk_evidence() {
    let examples: Value =
        serde_json::from_str(include_str!("fixtures/cohort_entry_deadline_2030.json")).unwrap();
    let mut value = fixture();
    value["audit"]["routing"]["entry_age_diagnostics"] = examples["no_action"].clone();
    value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|BTC"]["status"] =
        json!("sdk_dispatch_contract_observed");
    let error = parse_cohort_checkpoint(&value.to_string()).unwrap_err();
    assert!(error.contains("lacks recorded evidence"), "{error}");
}

#[test]
fn a_late_adapter_check_is_not_labeled_as_executed_sdk_breach() {
    let mut value = fixture();
    let evidence = &mut value["audit"]["routing"]["entry_age_diagnostics"];
    evidence["sdk_dispatch_checks"] = json!(0);
    let route = &mut evidence["by_provider_symbol"]["provider_v1|BTC"];
    route["sdk_dispatch_checks"] = json!(0);
    route["adapter_dispatch_checks"] = json!(1);
    route["submitted_entries_over_limit"] = json!(1);
    route["maximum_submission_age_ms"] = json!(31000);
    route["minimum_submission_headroom_ms"] = json!(-1000);
    route["status"] = json!("recorded_check_contract_breach");
    let parsed = parse_cohort_checkpoint(&value.to_string()).unwrap();
    let lines = summary_lines(&parsed, "provider_v1", "BTC").join(" ");
    assert!(lines.contains("RECORDED CHECK CONTRACT BREACH"), "{lines}");
    assert!(!lines.contains("EXECUTED SUBMISSION"), "{lines}");
}

#[test]
fn named_stage_counts_must_partition_the_recorded_checks() {
    let mut value = fixture();
    value["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]["provider_v1|BTC"]["adapter_dispatch_checks"] =
        json!(1);
    let error = parse_cohort_checkpoint(&value.to_string()).unwrap_err();
    assert!(error.contains("stage counts"), "{error}");
}
