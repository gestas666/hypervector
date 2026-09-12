fn long_chart_evidence_app() -> App {
    let mut app = cohort_app();
    app.selected_cohort_symbol_index = 0;
    app.selected_cohort_chart_provider_index = 0;
    app.show_cohort_chart_modal = true;
    let mut evaluation = app.backend.cohort.evaluations[0].clone();
    evaluation.symbol = "BTC".into();
    evaluation.strategy_id = app.backend.cohort.providers[0].strategy_id.clone();
    evaluation.readiness.indicators = (0..90)
        .map(|index| format!("INDICATOR {index} EXACT BACKEND VALUE"))
        .collect();
    evaluation.readiness.blockers = vec!["last_exact_blocker".into()];
    app.backend.cohort.evaluations = vec![evaluation];
    app
}

fn chart_without_advancing_market_clock(text: &str) -> String {
    text.lines().filter(|line| !line.contains("1M CANDLE AGE"))
        .collect::<Vec<_>>().join("\n")
}

#[test]
fn chart_detail_scroll_reaches_backend_provenance_without_moving_candles() {
    use crossterm::event::KeyCode;
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let mut app = long_chart_evidence_app();
        let initial = chart_without_advancing_market_clock(&render(&mut app, 2, width, height));
        app.handle_cohort_detail_scroll(KeyCode::End);
        assert!(
            app.cohort_detail_scroll > 0,
            "unreachable evidence\n{initial}"
        );
        let tail = chart_without_advancing_market_clock(&render(&mut app, 2, width, height));
        for expected in [
            "LAST EXACT BLOCKER",
            "SOURCE",
            "EFFECT report_only",
            "PgUp/Dn",
        ] {
            assert!(tail.contains(expected), "missing {expected}\n{tail}");
        }
        for (before, after) in initial.lines().zip(tail.lines()) {
            assert_eq!(
                before
                    .chars()
                    .take(usize::from(width / 2))
                    .collect::<String>(),
                after
                    .chars()
                    .take(usize::from(width / 2))
                    .collect::<String>()
            );
        }
        app.handle_cohort_detail_scroll(KeyCode::Home);
        assert_eq!(chart_without_advancing_market_clock(&render(&mut app, 2, width, height)), initial);
    }
}

#[test]
fn chart_detail_scroll_resets_on_provider_selection_and_open() {
    let mut app = long_chart_evidence_app();
    app.cohort_detail_scroll = 8;
    app.cycle_cohort_chart_provider(1);
    assert_eq!(app.cohort_detail_scroll, 0);
    app.show_cohort_chart_modal = false;
    app.cohort_detail_scroll = 8;
    app.toggle_cohort_chart_modal();
    assert!(app.show_cohort_chart_modal);
    assert_eq!(app.cohort_detail_scroll, 0);
}

#[test]
fn chart_detail_scroll_is_noop_when_complete_evidence_fits() {
    let mut app = long_chart_evidence_app();
    app.backend.cohort.evaluations[0].readiness.indicators = vec!["MEASURED VALUE".into()];
    let initial = chart_without_advancing_market_clock(&render(&mut app, 2, 190, 52));
    app.handle_cohort_detail_scroll(crossterm::event::KeyCode::End);
    assert_eq!(app.cohort_detail_scroll, 0);
    assert_eq!(chart_without_advancing_market_clock(&render(&mut app, 2, 190, 52)), initial);
}
