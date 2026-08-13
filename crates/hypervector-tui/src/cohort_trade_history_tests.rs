use super::*;

#[test]
fn current_run_scope_is_not_inferred_from_profile_scope() {
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.backend.run_id = Some("current-run".into());
    let trade = CohortTradeReflection {
        source_run_id: "current-run".into(),
        ..CohortTradeReflection::default()
    };

    assert_eq!(trade_scope(&trade, &app), "RUN");
}
