fn strategy_context_app() -> App {
    let mut app = hourly_chart_app(120);
    let provider = &mut app.backend.cohort.providers[0];
    provider.timeframe = "15m".into();
    let mut value = app.backend.cohort.evaluations[0].clone();
    value.symbol = "BTC".into();
    value.strategy_id = provider.strategy_id.clone();
    value.readiness.metrics.insert("signal_timeframe".into(), serde_json::json!("1h"));
    value.readiness.metrics.insert("source_timeframe".into(), serde_json::json!("15m"));
    app.backend.cohort.evaluations = vec![value];
    app
}

#[test]
fn strategy_context_hourly_signal_uses_hourly_candles_with_source_distinct() {
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let mut app = strategy_context_app();
        let screen = render(&mut app, 2, width, height);
        for expected in ["BTC 1H CANDLES", "2 bars", "DECISION TF 1H", "SOURCE TF 15M"] {
            assert!(screen.contains(expected), "{expected}: {screen}");
        }
    }
}

#[test]
fn strategy_context_arrival_lag_is_distinct_from_evidence_age() {
    let mut app = strategy_context_app();
    app.show_cohort_chart_modal = false;
    let screen = render(&mut app, 1, 190, 52);
    assert!(screen.contains("ARRIVAL LAG"), "{screen}");
    assert!(screen.contains("DATA AGE"), "{screen}");
    assert!(screen.contains("RECORDED INDICATORS"), "{screen}");
}

#[test]
fn strategy_context_plan_indicators_and_corresponding_regimes_remain_reachable() {
    use crossterm::event::KeyCode;
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let mut app = strategy_context_app();
        app.show_cohort_chart_modal = false;
        app.show_cohort_setup_modal = true;
        let value = &mut app.backend.cohort.evaluations[0];
        value.decision_time_ms = 60_000;
        value.observed_at = "1970-01-01T00:01:02Z".into();
        let mut prior = value.clone();
        prior.strategy_id = "canonical_regime_telemetry_v1".into();
        prior.decision_time_ms = 50_000;
        prior.observed_at = "1970-01-01T00:00:51Z".into();
        prior.state_5m = Some("TREND_DOWN".into());
        let mut latest = prior.clone();
        latest.decision_time_ms = 61_000;
        latest.observed_at = "1970-01-01T00:01:03Z".into();
        latest.state_5m = Some("TREND_UP".into());
        app.backend.cohort.regime_history = vec![prior, latest];
        let mut pages = String::new();
        for _ in 0..100 {
            pages.push_str(&render(&mut app, 1, width, height));
            let previous = app.cohort_detail_scroll;
            app.handle_cohort_detail_scroll(KeyCode::PageDown);
            if app.cohort_detail_scroll == previous { break; }
        }
        for expected in ["PLAN ENTRY", "CONFIGURED RISK", "RECORDED INDICATORS",
            "AT DECISION:", "LATEST RECORDED:", "TREND_DOWN", "TREND_UP",
            "PRECEDES DECISION BY 10s", "PROVIDER ENTRY RULES REMAIN SEPARATE"] {
            assert!(pages.contains(expected), "{expected} at {width}x{height}: {pages}");
        }
    }
}
