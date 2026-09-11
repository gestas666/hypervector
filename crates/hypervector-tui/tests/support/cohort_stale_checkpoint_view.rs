fn stale_checkpoint_app() -> App {
    use hypervector_tui::backend_cohort_research_sync::{CohortResearchSync, ResearchSyncState};

    let mut app = cohort_app();
    app.backend.connection = BackendConnectionState::Stale;
    app.backend.cohort_checkpoint = CohortCheckpointTelemetry {
        configured: true,
        available: true,
        stale: true,
        publication_stale: true,
        analysis_mode: Some("live_execution".into()),
        generated_at_utc: Some("2026-09-08T14:04:48.752796+00:00".into()),
        lifecycle_state: Some("running_consistent".into()),
        research_sync: Some(CohortResearchSync {
            state: ResearchSyncState::Ready,
            in_progress: false,
            last_attempt_at_utc: Some("2026-09-08T14:02:48.612393+00:00".into()),
            last_success_at_utc: Some("2026-09-08T14:03:28.663413+00:00".into()),
            last_success_age_seconds: Some(79.031641),
            last_imported_events: Some(350),
            error: None,
        }),
        ..CohortCheckpointTelemetry::default()
    };
    app
}

#[test]
fn stale_checkpoint_import_is_historical_on_all_nine_views() {
    let mut app = stale_checkpoint_app();
    for (width, height) in [(100, 28), (120, 36), (160, 45)] {
        for tab in 0..9 {
            let screen = render(&mut app, tab, width, height);
            assert!(screen.contains("IMPORT STALE // WAS OK"), "{screen}");
            assert!(screen.contains("LAST OK 10:03:28 EDT"), "{screen}");
            assert!(!screen.contains("(79s)"), "{screen}");
            assert!(!screen.contains("IMPORT OK"), "{screen}");
            assert!(!screen.contains("LIVE EXECUTION ARMED"), "{screen}");
            assert!(screen.contains("[9] CFG"), "{screen}");
        }
    }
}

#[test]
fn stale_checkpoint_lifecycle_is_explicitly_at_snapshot() {
    let mut app = stale_checkpoint_app();
    for (width, height) in [(120, 36), (160, 45)] {
        let screen = render(&mut app, 0, width, height);
        assert!(
            screen.contains("AT SNAPSHOT RUNNING CONSISTENT"),
            "{screen}"
        );
        assert!(
            screen.contains("CHECKPOINT STALE | AT SNAPSHOT"),
            "{screen}"
        );
        assert!(!screen.contains("| RUNNING CONSISTENT |"), "{screen}");
    }
}

#[test]
fn stale_checkpoint_import_warning_preserves_existing_panes() {
    let mut app = stale_checkpoint_app();
    for (width, height) in [(100, 28), (120, 36), (160, 45)] {
        for tab in 0..9 {
            let baseline = render(&mut app, tab, width, height);
            app.backend.cohort_checkpoint.research_sync = None;
            let missing = render(&mut app, tab, width, height);
            let body_rows = usize::from(height - 3);
            assert_eq!(
                baseline
                    .lines()
                    .take(body_rows)
                    .map(without_elapsed_book_age)
                    .collect::<Vec<_>>(),
                missing
                    .lines()
                    .take(body_rows)
                    .map(without_elapsed_book_age)
                    .collect::<Vec<_>>(),
                "tab {tab} at {width}x{height}"
            );
            app = stale_checkpoint_app();
        }
    }
}

fn without_elapsed_book_age(line: &str) -> String {
    let Some((prefix, age_and_venue)) = line.split_once("BOOK AGE ") else {
        return line.to_string();
    };
    let (age, suffix) = age_and_venue.split_once(" // MAINNET").expect("book venue");
    assert!(
        age.strip_suffix('s')
            .and_then(|value| value.parse::<f64>().ok())
            .is_some()
    );
    let border = suffix.trim_start_matches([' ', '─']);
    format!("{prefix}BOOK AGE <elapsed> // MAINNET{border}")
}

#[test]
fn fresh_checkpoint_with_backend_fault_keeps_current_import_status() {
    use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;

    let document = json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-09-08T14:04:48.752796+00:00",
        "lifecycle": {
            "state": "backend_heartbeat_stale",
            "cohort_heartbeat_status": "running",
            "asset_states": {"BTC": "FLAT"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 1},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0},
            "learning": {"evidence_state": "no_closed_trade_evidence"}
        }
    });
    let mut app = stale_checkpoint_app();
    let sync = app.backend.cohort_checkpoint.research_sync.take();
    app.backend.cohort_checkpoint = parse_cohort_checkpoint(&document.to_string()).unwrap();
    app.backend.cohort_checkpoint.research_sync = sync;
    assert!(app.backend.cohort_checkpoint.stale);
    let screen = render(&mut app, 0, 160, 45);
    assert!(screen.contains("IMPORT OK"), "{screen}");
    assert!(screen.contains("BACKEND HEARTBEAT STALE"), "{screen}");
    assert!(
        screen.contains("SOURCE ISSUE | BACKEND HEARTBEAT STALE"),
        "{screen}"
    );
    assert!(!screen.contains(">90S"), "{screen}");
    assert!(!screen.contains("IMPORT STALE"), "{screen}");
    assert!(!screen.contains("AT SNAPSHOT"), "{screen}");
}

#[test]
fn stale_checkpoint_recovery_restores_current_status_and_age() {
    let mut app = stale_checkpoint_app();
    assert!(render(&mut app, 0, 120, 36).contains("IMPORT STALE"));
    app.backend.cohort_checkpoint.stale = false;
    app.backend.cohort_checkpoint.publication_stale = false;
    app.backend.connection = BackendConnectionState::Connected;
    let screen = render(&mut app, 0, 120, 36);
    assert!(screen.contains("IMPORT OK"), "{screen}");
    assert!(screen.contains("(79s)"), "{screen}");
    assert!(screen.contains("LIVE EXECUTION ARMED"), "{screen}");
    assert!(screen.contains("| RUNNING CONSISTENT |"), "{screen}");
    assert!(!screen.contains("IMPORT STALE"), "{screen}");
    assert!(!screen.contains("AT SNAPSHOT"), "{screen}");
}

#[test]
fn stale_checkpoint_preserves_the_recorded_import_state() {
    use hypervector_tui::backend_cohort_research_sync::ResearchSyncState;

    let mut app = stale_checkpoint_app();
    for (state, in_progress, error, label) in [
        (ResearchSyncState::Disabled, false, None, "DISABLED"),
        (ResearchSyncState::Waiting, false, None, "WAITING"),
        (ResearchSyncState::Running, true, None, "RUNNING"),
        (
            ResearchSyncState::Running,
            true,
            Some("database locked"),
            "RETRYING",
        ),
        (
            ResearchSyncState::Deferred,
            false,
            Some("insufficient disk space"),
            "DEFERRED",
        ),
        (
            ResearchSyncState::Failed,
            false,
            Some("database locked"),
            "FAILED",
        ),
    ] {
        let sync = app
            .backend
            .cohort_checkpoint
            .research_sync
            .as_mut()
            .unwrap();
        sync.state = state;
        sync.in_progress = in_progress;
        sync.error = error.map(str::to_string);
        let screen = render(&mut app, 0, 160, 45);
        assert!(
            screen.contains(&format!("IMPORT STALE // WAS {label}")),
            "{screen}"
        );
        assert!(!screen.contains("(79s)"), "{screen}");
        if let Some(error) = error {
            assert!(screen.contains(error), "{screen}");
        }
    }
}
