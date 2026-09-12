use super::*;
use serde_json::json;

fn evaluation(decision: u64, observed: &str) -> CohortProviderEvaluation {
    serde_json::from_value(json!({
        "observed_at": observed, "strategy_id": "strategy", "symbol": "BTC",
        "decision_time_ms": decision, "reference_price": 100.0,
        "decision_action": "hold", "eligible": false, "reason": "no_entry",
        "side": null, "score": null, "minimum_score": null, "trigger": null,
        "primary_regime": null, "state_1m": null, "state_5m": null,
        "context_15m": null, "confidence": null,
        "readiness": {"side": null, "conditions_met": 1, "conditions_required": 2,
            "readiness_fraction": 0.5, "blockers": [], "indicators": []}
    }))
    .unwrap()
}

fn provider() -> CohortProvider {
    serde_json::from_value(json!({"strategy_id": "strategy", "symbols": ["BTC"],
        "sides": ["long", "short"], "priority": 1, "timeframe": "15m",
        "maximum_entry_delay_seconds": 60}))
    .unwrap()
}

#[test]
fn strategy_context_signal_metric_is_exact_and_legacy_fallback_explicit() {
    let provider = provider();
    let mut value = evaluation(1_000, "1970-01-01T00:00:02Z");
    assert_eq!(signal_timeframe(&provider, None), "15m");
    assert_eq!(signal_timeframe(&provider, Some(&value)), "15m");
    value
        .readiness
        .metrics
        .insert("signal_timeframe".into(), json!("1h"));
    assert_eq!(signal_timeframe(&provider, Some(&value)), "1h");
    value.strategy_id = "other".into();
    assert_eq!(signal_timeframe(&provider, Some(&value)), "15m");
    value.strategy_id = "strategy".into();
    value.symbol = "ETH".into();
    assert_eq!(signal_timeframe(&provider, Some(&value)), "15m");
}

#[test]
fn strategy_context_malformed_explicit_signal_cannot_become_source_clock() {
    let provider = provider();
    let mut value = evaluation(1_000, "1970-01-01T00:00:02Z");
    for metric in [json!(false), json!(null), json!("")] {
        value
            .readiness
            .metrics
            .insert("signal_timeframe".into(), metric);
        assert_eq!(signal_timeframe(&provider, Some(&value)), "N/A");
    }
}

#[test]
fn strategy_context_age_checks_clock_order_and_absence() {
    let value = evaluation(1_000, "1970-01-01T00:00:02Z");
    assert_eq!(evidence_age(&value, Some(62_000)), "DATA AGE 1m00s");
    assert_eq!(evidence_age(&value, Some(2_000)), "DATA AGE 0s");
    for now in [None, Some(1_999)] {
        assert_eq!(evidence_age(&value, now), "DATA AGE INVALID/UNKNOWN");
    }
    for (decision, at) in [
        (0, "1970-01-01T00:00:02Z"),
        (3_000, "1970-01-01T00:00:02Z"),
        (1_000, "bad"),
        (1_000, "1969-12-31T23:59:59Z"),
    ] {
        assert_eq!(
            evidence_age(&evaluation(decision, at), Some(62_000)),
            "DATA AGE INVALID/UNKNOWN"
        );
    }
}

#[test]
fn strategy_context_join_excludes_future_decisions_and_late_observations() {
    let value = evaluation(60_000, "1970-01-01T00:01:02Z");
    let mut prior = evaluation(50_000, "1970-01-01T00:00:51Z");
    prior.strategy_id = CANONICAL_PROVIDER.into();
    prior.state_5m = Some("TREND_DOWN".into());
    let mut future = prior.clone();
    future.decision_time_ms = 61_000;
    future.observed_at = "1970-01-01T00:01:01Z".into();
    let mut late = prior.clone();
    late.decision_time_ms = 60_000;
    late.observed_at = "1970-01-01T00:01:03Z".into();
    let history = vec![late, future, prior.clone()];
    assert_eq!(canonical_at_decision(&value, &history), Some(&prior));
    let lines = planning_lines(&value, &history, Some(70_000)).join("\n");
    assert!(lines.contains("AT DECISION:"));
    assert!(lines.contains("LATEST RECORDED:"));
    assert!(lines.contains("PRECEDES DECISION BY 10s"));
    assert!(lines.contains("CANONICAL 1M N/A // 5M TREND_DOWN // 15M N/A"));
}

#[test]
fn strategy_context_join_accepts_equal_clocks_and_rejects_foreign_evidence() {
    let value = evaluation(60_000, "1970-01-01T00:01:02Z");
    let mut canonical = value.clone();
    canonical.strategy_id = CANONICAL_PROVIDER.into();
    assert_eq!(
        canonical_at_decision(&value, &[canonical.clone()]),
        Some(&canonical)
    );
    let mut foreign = canonical.clone();
    foreign.symbol = "ETH".into();
    let wrong_provider = value.clone();
    let mut invalid = canonical;
    invalid.observed_at = "bad".into();
    assert!(canonical_at_decision(&value, &[foreign, wrong_provider, invalid]).is_none());
    let missing = evaluation(60_000, "bad");
    assert!(canonical_at_decision(&missing, &[]).is_none());
    let lines = planning_lines(&value, &[], Some(70_000)).join("\n");
    assert!(lines.contains("AT DECISION: CANONICAL UNAVAILABLE"));
    assert!(lines.contains("LATEST RECORDED: CANONICAL UNAVAILABLE"));
}
