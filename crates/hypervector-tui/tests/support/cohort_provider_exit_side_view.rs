fn native_exit_side_app() -> App {
    let mut app = complete_portfolio_app();
    let value: hypervector_tui::backend_cohort::CohortProviderEvaluation =
        serde_json::from_str(include_str!("../fixtures/spcx_short_exit_20260915.json"))
            .expect("authenticated native SPCX evaluation");
    let mut provider = app.backend.cohort.providers[0].clone();
    provider.strategy_id = value.strategy_id.clone();
    provider.symbols = vec![value.symbol.clone()];
    app.backend.cohort.providers = vec![provider];
    app.backend.cohort.evaluations = vec![value];
    app.selected_cohort_setup_index = 0;
    app
}

#[test]
fn native_short_exit_is_side_specific_in_setup_and_router_views() {
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let mut app = native_exit_side_app();
        let router = render(&mut app, 1, width, height);
        assert!(router.contains("EXIT SHORT"), "{width}x{height}\n{router}");
        app.show_cohort_setup_modal = true;
        let inspector = render(&mut app, 1, width, height);
        assert!(
            inspector.contains("EXIT SHORT"),
            "{width}x{height}\n{inspector}"
        );
        assert!(!inspector.contains("CLOSE_OPEN_POSITION"), "{inspector}");
    }
}

#[test]
fn exit_side_display_preserves_recorded_sides_and_legacy_uncertainty() {
    let cases = [
        ("close_open_position", json!(["long"]), "EXIT LONG"),
        (
            "close_open_position",
            json!(["short", "long"]),
            "EXIT LONG/SHORT",
        ),
        ("close_open_position", Value::Null, "EXIT SIDE N/A"),
        ("close_open_position", json!([]), "EXIT SIDE N/A"),
        ("close_open_position", json!(["unknown"]), "EXIT SIDE N/A"),
        (
            "close_open_position",
            json!(["short", "short"]),
            "EXIT SIDE N/A",
        ),
        ("close_long", Value::Null, "EXIT LONG"),
        ("close_short", Value::Null, "EXIT SHORT"),
        ("close_long", json!(["short"]), "EXIT SIDE N/A"),
    ];
    for (action, sides, expected) in cases {
        let screen = render_exit_variant(action, sides);
        assert!(screen.contains(expected), "{action}: {expected}\n{screen}");
    }
}

fn render_exit_variant(action: &str, sides: Value) -> String {
    let mut app = native_exit_side_app();
    let mut raw: Value =
        serde_json::from_str(include_str!("../fixtures/spcx_short_exit_20260915.json")).unwrap();
    raw["decision_action"] = json!(action);
    raw["exit_sides"] = sides;
    raw["side"] = json!("long");
    app.backend.cohort.evaluations = vec![serde_json::from_value(raw).unwrap()];
    app.show_cohort_setup_modal = true;
    render(&mut app, 1, 120, 36)
}

#[test]
fn simultaneous_entry_and_exit_signals_preserve_both_recorded_actions() {
    for action in ["enter_long", "hold"] {
        let screen = render_exit_variant(action, json!(["short"]));
        let expected = format!("{} / EXIT SHORT", action.to_uppercase());
        assert!(screen.contains(&expected), "{expected}\n{screen}");
    }
    for sides in [Value::Null, json!([])] {
        let screen = render_exit_variant("hold", sides);
        assert!(!screen.contains("HOLD / EXIT"), "{screen}");
    }
}

#[test]
fn regime_provider_fallback_retains_exit_direction_in_compact_matrix() {
    for (action, sides, expected) in [
        ("close_open_position", vec!["short"], "EXIT S"),
        ("close_open_position", vec!["long", "short"], "EXIT L/S"),
        ("enter_long", vec!["short"], "ENTER L/EXIT S"),
        ("enter_short", vec!["long"], "ENTER S/EXIT L"),
    ] {
        let mut app = native_exit_side_app();
        app.backend.cohort.regime_history.clear();
        app.selected_cohort_symbol_index = app.backend.cohort.enabled_symbols.iter()
            .position(|symbol| symbol == "xyz:SPCX").unwrap();
        let value = &mut app.backend.cohort.evaluations[0];
        value.decision_action = action.into();
        value.exit_sides = Some(sides.into_iter().map(str::to_string).collect());
        let screen = render(&mut app, 7, 190, 52);
        let row = screen.lines().find(|line| line.contains("xyz:SPCX")
            && line.contains("NOT CLASS")).expect("provider-only matrix row");
        assert!(row.contains(expected), "{expected}\n{screen}");
    }
}

#[test]
fn native_short_exit_is_side_specific_in_chart_inspector() {
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let mut app = native_exit_side_app();
        app.selected_cohort_symbol_index = app
            .backend
            .cohort
            .assets
            .iter()
            .position(|asset| asset.symbol == "xyz:SPCX")
            .unwrap();
        app.selected_cohort_chart_provider_index = 0;
        app.show_cohort_chart_modal = true;
        let screen = render(&mut app, 2, width, height);
        assert!(screen.contains("EXIT SHORT"), "{width}x{height}\n{screen}");
    }
}
