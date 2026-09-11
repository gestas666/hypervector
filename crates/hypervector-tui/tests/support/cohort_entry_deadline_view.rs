fn entry_deadline_app() -> App {
    use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;
    let mut app = cohort_app();
    app.apply_backend_telemetry(disarmed_cohort_backend());
    let setup = &app.backend.cohort.evaluations[0];
    let mut checkpoint = entry_deadline_fixtures::fixture();
    let routes = checkpoint["audit"]["routing"]["entry_age_diagnostics"]["by_provider_symbol"]
        .as_object_mut().unwrap();
    let mut route = routes.remove("provider_v1|BTC").unwrap();
    let limit = app.backend.cohort.providers.iter()
        .find(|provider| provider.strategy_id == setup.strategy_id).unwrap()
        .maximum_entry_delay_seconds * 1000;
    route["maximum_entry_delay_ms"] = json!(limit);
    route["maximum_submission_age_ms"] = json!(limit - 1000);
    routes.insert(format!("{}|{}", setup.strategy_id, setup.symbol), route);
    app.backend.cohort_checkpoint =
        parse_cohort_checkpoint(&checkpoint.to_string()).unwrap();
    app.toggle_cohort_setup_modal();
    app
}

#[test]
fn entry_deadline_inspector_renders_recorded_stage_at_all_supported_sizes() {
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let mut app = entry_deadline_app();
        let screen = render(&mut app, 1, width, height);
        if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
            println!("ENTRY DEADLINE SYNTHETIC {width}x{height}\n{screen}\nEND ENTRY DEADLINE");
        }
        for label in [
            "RUN AGGREGATE AT CHECKPOINT",
            "SDK DISPATCH CONTRACT OBSERVED",
            "CHECKS SDK 1",
            "ADAPTER 0",
            "ADMISSION/LEGACY 0",
            "59000 ms",
            "1000 ms",
            "CONFIGURED RISK",
        ] {
            assert!(screen.contains(label), "missing {label} at {width}x{height}\n{screen}");
        }
    }
}

#[test]
fn entry_deadline_inspector_does_not_borrow_another_routes_evidence() {
    let mut app = entry_deadline_app();
    app.backend.cohort.evaluations[0].symbol = "xyz:SNDK".into();
    let screen = render(&mut app, 1, 120, 36);
    assert!(screen.contains("ENTRY DEADLINE EVIDENCE UNAVAILABLE"), "{screen}");
    assert!(!screen.contains("SDK DISPATCH CONTRACT OBSERVED"), "{screen}");
}

#[test]
fn entry_deadline_inspector_keeps_existing_evidence_reachable() {
    use crossterm::event::KeyCode;
    let mut app = entry_deadline_app();
    app.backend.cohort.evaluations[0].readiness.indicators = (0..40)
        .map(|index| format!("EXACT PRICE DETAIL {index:02}"))
        .collect();
    let top = render(&mut app, 1, 100, 28);
    app.handle_cohort_detail_scroll(KeyCode::End);
    let bottom = render(&mut app, 1, 100, 28);
    assert!(bottom.contains("EXACT PRICE DETAIL 39"), "{bottom}");
    app.handle_cohort_detail_scroll(KeyCode::Home);
    assert_eq!(render(&mut app, 1, 100, 28), top);
}
