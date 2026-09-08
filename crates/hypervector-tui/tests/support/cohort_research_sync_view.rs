#[test]
fn import_failure_is_visible_on_every_view_at_both_supported_sizes() {
    use hypervector_tui::backend_cohort_research_sync::{CohortResearchSync, ResearchSyncState};

    let mut app = cohort_app();
    app.backend.cohort_checkpoint.research_sync = Some(CohortResearchSync {
        state: ResearchSyncState::Failed, in_progress: false,
        last_attempt_at_utc: Some("2026-09-07T22:00:00Z".into()),
        last_success_at_utc: None, last_success_age_seconds: None,
        last_imported_events: None, error: Some("database locked".into()),
    });
    for (width, height) in [(100, 28), (120, 36)] {
        for tab in 0..9 {
            let screen = render(&mut app, tab, width, height);
            assert!(screen.contains("IMPORT FAILED"), "tab {tab}\n{screen}");
            assert!(screen.contains("database locked"), "tab {tab}\n{screen}");
            assert!(screen.contains("LIVE EXECUTION ARMED"), "tab {tab}\n{screen}");
            assert!(screen.contains("[9] CFG"), "tab {tab}\n{screen}");
        }
    }
}

#[test]
fn legacy_import_status_is_explicit_and_recovery_clears_warning() {
    use hypervector_tui::backend_cohort_research_sync::{CohortResearchSync, ResearchSyncState};

    let mut app = cohort_app();
    assert!(render(&mut app, 0, 100, 28).contains("IMPORT UNREPORTED"));
    app.backend.cohort_checkpoint.research_sync = Some(CohortResearchSync {
        state: ResearchSyncState::Ready, in_progress: false,
        last_attempt_at_utc: Some("2026-09-07T21:59:00Z".into()),
        last_success_at_utc: Some("2026-09-07T22:00:00Z".into()),
        last_success_age_seconds: Some(30.0), last_imported_events: Some(7), error: None,
    });
    let screen = render(&mut app, 0, 100, 28);
    assert!(screen.contains("IMPORT OK"), "{screen}");
    assert!(screen.contains("30s"), "{screen}");
    assert!(screen.contains("7 events"), "{screen}");
    assert!(!screen.contains("IMPORT FAILED"), "{screen}");
}

#[test]
fn long_import_errors_do_not_consume_existing_pane_rows() {
    use hypervector_tui::backend_cohort_research_sync::{CohortResearchSync, ResearchSyncState};

    let mut app = cohort_app();
    let baseline = render(&mut app, 0, 100, 28);
    app.backend.cohort_checkpoint.research_sync = Some(CohortResearchSync {
        state: ResearchSyncState::Deferred, in_progress: false,
        last_attempt_at_utc: Some("2026-09-07T22:00:00Z".into()),
        last_success_at_utc: None, last_success_age_seconds: None,
        last_imported_events: None,
        error: Some(format!("research sync deferred: insufficient disk space\n{}", "detail ".repeat(60))),
    });
    let screen = render(&mut app, 0, 100, 28);
    assert!(screen.contains("IMPORT DEFERRED"), "{screen}");
    assert!(screen.contains("insufficient disk space"), "{screen}");
    let existing_rows: Vec<_> = baseline.lines().take(25).collect();
    let failure_rows: Vec<_> = screen.lines().take(25).collect();
    assert_eq!(failure_rows, existing_rows, "{screen}");
    assert!(!screen.contains("0 events"), "{screen}");
}
