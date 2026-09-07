#[test]
fn compact_setup_inspector_scrolls_to_last_indicator_and_back() {
    use crossterm::event::KeyCode;
    let mut app = cohort_app();
    app.backend.cohort.evaluations[0].readiness.indicators = (0..40)
        .map(|index| format!("EXACT PRICE DETAIL {index:02}"))
        .collect();
    app.toggle_cohort_setup_modal();
    let top = render(&mut app, 1, 100, 28);
    assert!(!top.contains("EXACT PRICE DETAIL 39"), "{top}");
    app.handle_cohort_detail_scroll(KeyCode::End);
    let bottom = render(&mut app, 1, 100, 28);
    assert!(bottom.contains("EXACT PRICE DETAIL 39"), "{bottom}");
    app.handle_cohort_detail_scroll(KeyCode::Home);
    assert_eq!(render(&mut app, 1, 100, 28), top);
    app.handle_cohort_detail_scroll(KeyCode::PageDown);
    assert!(app.cohort_detail_scroll > 0);
    app.close_cohort_modals();
    assert_eq!(app.cohort_detail_scroll, 0);
}

#[test]
fn compact_regime_pages_keep_hidden_panes_reachable() {
    let mut app = cohort_app();
    app.cohort_regime_page = 1;
    let first = render(&mut app, 7, 100, 28);
    assert!(first.contains("CANONICAL LABEL TAPE"), "{first}");
    assert!(first.contains("OPEN"), "{first}");
    app.cohort_regime_page = 2;
    let second = render(&mut app, 7, 100, 28);
    assert!(second.contains("LAST CLOSED // REGIME REFLECTION"), "{second}");
    assert!(second.contains("ARBITRATION"), "{second}");
}
