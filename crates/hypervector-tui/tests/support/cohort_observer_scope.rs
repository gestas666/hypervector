fn observer_scope_screen(app: &App) -> String {
    let mut terminal = Terminal::new(TestBackend::new(165, 46)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw observer");
    let buffer = terminal.backend().buffer();
    (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn source_single_side_without_override_remains_single_side_in_both_columns() {
    for side in ["long", "short"] {
        let mut app = config_app();
        app.backend.cohort.providers[0].sides = vec![side.into()];
        app.backend.cohort.providers[0].execution_side_overrides.clear();
        app.active_tab = 8;
        let screen = observer_scope_screen(&app);
        let row = screen.lines().find(|line| line.contains("PROVIDER / COIN SCOPE"))
            .expect("provider scope row");
        assert_eq!(row.matches(&format!("EXECUTE {} ONLY", side.to_uppercase())).count(), 2, "{row}");
        assert!(!row.contains("EXECUTE LONG + SHORT"), "{row}");
    }
}

#[test]
fn observer_operations_cannot_infer_flatness_without_asset_observation() {
    let mut app = config_app();
    app.active_tab = 6;
    assert!(app.backend.cohort.assets.is_empty());
    let screen = observer_scope_screen(&app);
    assert!(screen.contains("POSITION UNOBSERVED"), "{screen}");
    assert!(!screen.contains("POSITION FLAT"), "{screen}");
}
