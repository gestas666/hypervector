//! Deterministic checks for conditional expiry and source-age labels.

use super::*;

fn fixed(as_of: Option<u64>) -> CohortOpenExitPlan {
    CohortOpenExitPlan {
        opened_at_ms: Some(1_000),
        timer_origin: Some("persisted_runtime_opened_at".into()),
        as_of_timestamp_ms: as_of,
        maximum_hold_seconds: 100,
        maximum_hold_policy: "fixed".into(),
        soft_deadline_timestamp_ms: 101_000,
        deadline_timestamp_ms: 101_000,
        remaining_time_ms: 1_000,
        ..Default::default()
    }
}

#[test]
fn open_hold_notice_distinguishes_snapshot_expiry_from_conditional_expiry() {
    let before = clock_labels(&fixed(Some(100_000)), Some(100_500));
    assert_eq!(before.timer, "FIXED IN 1s IF STILL OPEN");
    assert!(!before.attention);
    let overdue = clock_labels(&fixed(Some(100_000)), Some(131_000));
    assert_eq!(overdue.timer, "FIXED +30s IF STILL OPEN");
    assert!(overdue.attention);
    let known = clock_labels(&fixed(Some(131_000)), Some(141_000));
    assert_eq!(known.timer, "FIXED +30s AT SNAPSHOT");
}

#[test]
fn open_hold_notice_exact_deadline_is_due_without_rounding_early() {
    assert_eq!(
        clock_labels(&fixed(Some(100_000)), Some(101_000)).timer,
        "FIXED DUE IF STILL OPEN"
    );
    assert_eq!(
        clock_labels(&fixed(Some(101_000)), Some(101_000)).timer,
        "FIXED DUE AT SNAPSHOT"
    );
}

#[test]
fn open_hold_notice_marks_old_missing_and_future_evidence() {
    assert_eq!(
        clock_labels(&fixed(Some(100_000)), Some(160_000)).evidence,
        "AGE 1m00s"
    );
    let old = clock_labels(&fixed(Some(100_000)), Some(160_001));
    assert_eq!(old.evidence, "AGE 1m00s OLD");
    assert!(old.attention);
    assert_eq!(
        clock_labels(&fixed(None), Some(160_001)).evidence,
        "AGE UNKNOWN"
    );
    for now in [None, Some(99_999)] {
        assert_eq!(
            clock_labels(&fixed(Some(100_000)), now).timer,
            "CLOCK INVALID"
        );
    }
}

#[test]
fn open_hold_notice_does_not_extend_from_old_regime_support() {
    let mut plan = fixed(Some(120_000));
    plan.maximum_hold_policy = "extend_while_regime_supported".into();
    plan.hard_deadline_timestamp_ms = Some(300_000);
    plan.extension_active = true;
    assert_eq!(
        clock_labels(&plan, Some(130_000)).timer,
        "HARD IN 2m50s IF STILL OPEN"
    );
    assert_eq!(
        clock_labels(&plan, Some(181_000)).timer,
        "SOFT PASSED; EXTENSION UNKNOWN"
    );
    assert_eq!(
        clock_labels(&plan, Some(310_000)).timer,
        "HARD +10s IF STILL OPEN"
    );
    plan.as_of_timestamp_ms = Some(90_000);
    plan.extension_active = false;
    assert_eq!(
        clock_labels(&plan, Some(100_000)).timer,
        "SOFT IN 1s IF STILL OPEN"
    );
    assert_eq!(
        clock_labels(&plan, Some(105_000)).timer,
        "SOFT PASSED; EXTENSION UNKNOWN"
    );
}

#[test]
fn open_hold_notice_labels_origin_and_unknown_plan() {
    let mut plan = fixed(Some(100_000));
    assert_eq!(clock_labels(&plan, Some(100_000)).origin, "DECISION CLOCK");
    plan.timer_origin = Some("venue_entry_fill_fallback_legacy".into());
    assert_eq!(clock_labels(&plan, Some(100_000)).origin, "FILL FALLBACK");
    plan.timer_origin = None;
    assert_eq!(clock_labels(&plan, Some(100_000)).origin, "ORIGIN UNKNOWN");
    plan.maximum_hold_policy = "other".into();
    assert_eq!(clock_labels(&plan, Some(100_000)).timer, "PLAN UNKNOWN");
}

#[test]
fn open_hold_notice_unknown_policy_needs_attention_before_any_deadline() {
    let mut plan = fixed(Some(100_000));
    plan.maximum_hold_policy = "unsupported".into();
    assert!(clock_labels(&plan, Some(100_000)).attention);
}

#[test]
fn open_hold_notice_missing_deadlines_remain_unknown() {
    let mut plan = fixed(Some(100_000));
    plan.soft_deadline_timestamp_ms = 0;
    assert_eq!(clock_labels(&plan, Some(100_000)).timer, "PLAN UNKNOWN");
    plan.soft_deadline_timestamp_ms = 101_000;
    plan.maximum_hold_policy = "extend_while_regime_supported".into();
    assert_eq!(clock_labels(&plan, Some(100_000)).timer, "PLAN UNKNOWN");
}

#[test]
fn open_hold_notice_observed_unextended_expiry_keeps_snapshot_clock() {
    let mut plan = fixed(Some(102_000));
    plan.maximum_hold_policy = "extend_while_regime_supported".into();
    plan.hard_deadline_timestamp_ms = Some(300_000);
    assert_eq!(
        clock_labels(&plan, Some(110_000)).timer,
        "SOFT +1s AT SNAPSHOT"
    );
}
