//! Regression checks for timer provenance discarded by the original projection.

use super::*;
use serde_json::{Value, json};

fn clock_plan() -> Value {
    json!({
        "maximum_hold_seconds":86400,"maximum_hold_policy":"fixed",
        "opened_at_ms":1789135200000_u64,"timer_origin":"persisted_runtime_opened_at",
        "soft_deadline_timestamp_ms":1789221600000_u64,
        "deadline_timestamp_ms":1789221600000_u64,"remaining_time_ms":80565077,
        "expired":false,"source":"bound_execution_plan","controller":"cohort_maximum_hold"
    })
}

fn parse(value: Value) -> Result<CohortOpenExitPlan, String> {
    let raw = serde_json::from_value(value).expect("typed timer fixture");
    project_open_exit_plan("hourly_donchian_20_10_atr20_bidirectional_v1", raw)
}

#[test]
fn open_hold_clock_preserves_runtime_origin() {
    let projected = parse(clock_plan()).expect("valid runtime timer");
    let shown = format!("{projected:?}");
    assert!(
        shown.contains("opened_at_ms: Some(1789135200000)"),
        "{shown}"
    );
    assert!(shown.contains("persisted_runtime_opened_at"), "{shown}");
}

#[test]
fn open_hold_clock_rejects_unsupported_origin() {
    let mut value = clock_plan();
    value["timer_origin"] = json!("current_wall_clock_guess");
    assert!(parse(value).is_err());
}

#[test]
fn open_hold_clock_rejects_conflicting_bound_deadline() {
    let mut value = clock_plan();
    value["opened_at_ms"] = json!(1789135222977_u64);
    assert!(parse(value).is_err());
}

#[test]
fn open_hold_clock_rejects_incomplete_origin_pair() {
    for field in ["opened_at_ms", "timer_origin"] {
        let mut value = clock_plan();
        value.as_object_mut().unwrap().remove(field);
        assert!(parse(value).is_err(), "missing {field}");
    }
}

#[test]
fn open_hold_clock_rejects_unknown_extension_policy() {
    let mut value = clock_plan();
    value["maximum_hold_policy"] = json!("arbitrary_extension");
    value["hard_maximum_hold_seconds"] = json!(172800);
    value["hard_deadline_timestamp_ms"] = json!(1789308000000_u64);
    assert!(parse(value).is_err());
}

#[test]
fn open_hold_clock_binds_observation_without_using_fill_clock() {
    let mut plan = parse(clock_plan()).expect("valid timer");
    plan.bind_observation(Some(1_789_141_034_923))
        .expect("exact remaining clock");
    assert_eq!(plan.as_of_timestamp_ms, Some(1_789_141_034_923));
    assert_eq!(plan.opened_at_ms, Some(1_789_135_200_000));
    assert_eq!(plan.remaining_time_ms, 80_565_077);
}

#[test]
fn open_hold_clock_rejects_wrong_remaining_and_future_origin() {
    for observed in [0, 1_789_135_199_999, 1_789_141_034_922, 1_789_221_600_000] {
        let mut plan = parse(clock_plan()).expect("valid timer");
        assert!(plan.bind_observation(Some(observed)).is_err(), "{observed}");
    }
}

#[test]
fn open_hold_clock_keeps_legacy_unknown_and_labeled_fill_fallback_distinct() {
    let mut legacy = clock_plan();
    legacy.as_object_mut().unwrap().remove("opened_at_ms");
    legacy.as_object_mut().unwrap().remove("timer_origin");
    let mut old = parse(legacy).expect("legacy timer");
    old.bind_observation(None).expect("unknown observation");
    assert_eq!(old.opened_at_ms, None);
    assert_eq!(old.timer_origin, None);
    assert_eq!(old.as_of_timestamp_ms, None);
    let mut fallback = clock_plan();
    fallback["timer_origin"] = json!("venue_entry_fill_fallback_legacy");
    assert_eq!(
        parse(fallback).unwrap().timer_origin.as_deref(),
        Some("venue_entry_fill_fallback_legacy")
    );
}

#[test]
fn open_hold_clock_requires_consistent_hard_deadlines_and_extension_interval() {
    let mut value = clock_plan();
    value["maximum_hold_policy"] = json!("extend_while_regime_supported");
    value["hard_maximum_hold_seconds"] = json!(172800);
    value["hard_deadline_timestamp_ms"] = json!(1789308000000_u64);
    assert!(parse(value.clone()).is_ok());
    value["hard_deadline_timestamp_ms"] = json!(1789308000001_u64);
    assert!(parse(value.clone()).is_err());
    value["hard_deadline_timestamp_ms"] = json!(1789308000000_u64);
    value["extension_active"] = json!(true);
    value["deadline_timestamp_ms"] = json!(1789308000000_u64);
    assert!(parse(value.clone()).is_err());
    value["regime_context"] = json!("still_directionally_supported");
    value["remaining_time_ms"] = json!(86400000);
    let mut plan = parse(value).expect("supported extension");
    plan.bind_observation(Some(1789221600000))
        .expect("at soft boundary");
    assert!(plan.bind_observation(Some(1789221599999)).is_err());
    assert!(plan.bind_observation(Some(1789308000000)).is_err());
}

#[test]
fn open_hold_clock_rejects_millisecond_overflow() {
    let mut value = clock_plan();
    value["opened_at_ms"] = json!(u64::MAX);
    assert!(parse(value).is_err());
}

#[test]
fn open_hold_clock_rejects_hold_duration_overflow_and_incomplete_extension() {
    let mut value = clock_plan();
    value["maximum_hold_seconds"] = json!(u64::MAX);
    assert!(parse(value).unwrap_err().contains("overflows milliseconds"));
    let mut value = clock_plan();
    value["maximum_hold_policy"] = json!("extend_while_regime_supported");
    assert!(parse(value).is_err());
}

#[test]
fn open_hold_clock_rejects_extension_outside_interval_with_consistent_remaining() {
    let mut plan = parse(clock_plan()).unwrap();
    plan.extension_active = true;
    plan.deadline_timestamp_ms = 1_789_308_000_000;
    plan.hard_deadline_timestamp_ms = Some(plan.deadline_timestamp_ms);
    for observed in [1_789_221_599_999, 1_789_308_000_000] {
        plan.remaining_time_ms = plan.deadline_timestamp_ms.saturating_sub(observed);
        plan.expired = plan.remaining_time_ms == 0;
        assert!(
            plan.bind_observation(Some(observed))
                .unwrap_err()
                .contains("outside")
        );
    }
    plan.remaining_time_ms = 86_400_000;
    plan.expired = false;
    plan.hard_deadline_timestamp_ms = None;
    assert!(
        plan.bind_observation(Some(1_789_221_600_000))
            .unwrap_err()
            .contains("outside")
    );
}

#[test]
fn open_hold_clock_origin_validator_rejects_negative_hard_interval() {
    let mut value = clock_plan();
    value["hard_maximum_hold_seconds"] = json!(1);
    value["hard_deadline_timestamp_ms"] = json!(1_789_308_000_000_u64);
    let raw: RawOpenExitPlan = serde_json::from_value(value).unwrap();
    assert!(
        clocks::validate_origin(&raw, 1_789_221_600_000)
            .unwrap_err()
            .contains("precedes")
    );
}
