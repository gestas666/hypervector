fn hourly_chart_app(count: u32) -> App {
    let mut app = cohort_app();
    app.backend.cohort.providers[0].timeframe = "1h".into();
    app.selected_cohort_symbol_index = 0;
    app.selected_cohort_chart_provider_index = 0;
    app.show_cohort_chart_modal = true;
    app.backend.cohort.candle_history.insert(
        "BTC".into(),
        (0..count)
            .map(|minute| CohortCandle {
                timestamp_ms: u64::from(minute) * 60_000,
                open: 100.0 + f64::from(minute),
                high: 102.0 + f64::from(minute),
                low: 99.0 + f64::from(minute),
                close: 101.0 + f64::from(minute),
                volume: 1.0,
            })
            .collect(),
    );
    app
}

#[test]
fn hourly_chart_renders_completed_btc_bars_at_supported_sizes() {
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let mut app = hourly_chart_app(120);
        let screen = render(&mut app, 2, width, height);
        for expected in ["BTC 1H CANDLES", "$220.0000", "2 bars", "DECISION TF 1H"] {
            assert!(screen.contains(expected), "missing {expected}\n{screen}");
        }
        assert!(
            !screen.contains("UNSUPPORTED DECISION TIMEFRAME"),
            "{screen}"
        );
    }
}

#[test]
fn hourly_chart_reports_insufficient_backend_history() {
    let mut app = hourly_chart_app(59);
    let screen = render(&mut app, 2, 120, 36);
    assert!(
        screen.contains("NO COMPLETE 1H BAR IN BACKEND WINDOW"),
        "{screen}"
    );
    assert!(
        !screen.contains("$159.0000"),
        "partial hour became a candle\n{screen}"
    );
}
