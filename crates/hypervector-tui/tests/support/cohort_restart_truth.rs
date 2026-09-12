fn mark_restart_snapshot_stopped(app: &mut App, state: &str) {
    app.backend.cohort_checkpoint.lifecycle_state = Some(state.into());
    app.backend.cohort_checkpoint.asset_states = app
        .backend
        .cohort
        .enabled_symbols
        .iter()
        .map(|symbol| (symbol.clone(), "STOPPED".into()))
        .collect();
}

#[test]
fn restart_stopped_snapshot_does_not_claim_connected_or_persistent_backend() {
    let mut app = cohort_app();
    app.detached_lifecycle = true;
    for state in [
        "stopped_consistent",
        "stale_running_heartbeat_after_asset_stop",
    ] {
        mark_restart_snapshot_stopped(&mut app, state);
        for (width, height) in [(100, 28), (120, 36), (190, 52)] {
            for tab in 0..9 {
                let screen = render(&mut app, tab, width, height);
                assert!(screen.contains("STOPPED SNAPSHOT"), "{screen}");
                assert!(screen.contains("BACKEND STOPPED"), "{screen}");
                for forbidden in [
                    "BACKEND CONNECTED",
                    "BACKEND PERSISTS ON QUIT",
                    "Quit leaves backend running",
                    "Quit keeps backend",
                ] {
                    assert!(!screen.contains(forbidden), "{forbidden}: {screen}");
                }
            }
        }
    }
}

#[test]
fn restart_stopped_snapshot_disables_operator_requests_and_routing_claims() {
    let mut app = cohort_app();
    app.cohort_command_inbox = Some("unused-test-inbox".into());
    app.cohort_control_focus = 2;
    mark_restart_snapshot_stopped(&mut app, "stopped_consistent");

    app.prepare_cohort_confirmation();

    assert!(app.cohort_confirmation.is_none());
    let screen = render(&mut app, 6, 190, 52);
    assert!(
        screen.contains("BACKEND STOPPED // MANUAL REQUESTS DISABLED"),
        "{screen}"
    );
    for forbidden in [
        "REQUEST CHANNEL ENABLED",
        "LIVE BACKEND ARMED",
        "AUTO ROUTING CONTINUES",
        "AUTOMATIC ENTRY + EXIT ROUTING ACTIVE",
    ] {
        assert!(!screen.contains(forbidden), "{forbidden}: {screen}");
    }
}

#[test]
fn restart_stop_after_confirmation_prevents_local_request_write() {
    let temporary = tempfile::tempdir().expect("tempdir");
    let inbox = temporary.path().join("operator_commands");
    fs::create_dir_all(inbox.join("pending")).expect("pending inbox");
    let mut app = cohort_app();
    app.cohort_command_inbox = Some(inbox.clone());
    app.cohort_control_focus = 1;
    app.prepare_cohort_confirmation();
    assert!(app.cohort_confirmation.is_some());
    mark_restart_snapshot_stopped(&mut app, "stale_running_heartbeat_after_asset_stop");

    app.submit_cohort_confirmation();

    assert!(
        app.cohort_notice
            .as_deref()
            .unwrap()
            .contains("REQUEST NOT SUBMITTED")
    );
    assert_eq!(
        fs::read_dir(inbox.join("pending"))
            .expect("pending inbox")
            .count(),
        0
    );
}

#[test]
fn restart_friction_excludes_historical_fills_from_current_run() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = trade_checkpoint();
    let historical = app.backend.cohort.fills[0].clone();
    assert_ne!(historical.origin_run_id, app.backend.run_id);
    for checkpoint_details in [false, true] {
        app.backend.cohort_checkpoint.fill_details = if checkpoint_details {
            vec![historical.clone()]
        } else {
            vec![]
        };
        let screen = render(&mut app, 4, 190, 52);
        assert!(screen.contains("CURRENT RUN FILL LEGS 0"), "{screen}");
        assert!(screen.contains("FILL FEES $0.00"), "{screen}");
        assert!(
            screen.contains("HISTORY 1"),
            "historical fill must remain visible: {screen}"
        );
    }
}

#[test]
fn restart_friction_retains_only_attributed_current_measurements() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = trade_checkpoint();
    let mut current = app.backend.cohort.fills[0].clone();
    current.trade_id = 102;
    current.origin_run_id.clone_from(&app.backend.run_id);
    current.fee_usd = 0.25;
    current.slippage_bps = Some(2.0);
    let mut unknown = current.clone();
    unknown.trade_id = 103;
    unknown.origin_run_id = None;
    unknown.fee_usd = 10.0;
    app.backend.cohort.fills.extend([current, unknown]);

    let screen = render(&mut app, 4, 190, 52);

    assert!(screen.contains("CURRENT RUN FILL LEGS 1"), "{screen}");
    assert!(screen.contains("FILL FEES $0.25"), "{screen}");
    assert!(screen.contains("+2.00 bps"), "{screen}");
    assert!(screen.contains("UNATTRIBUTED 1"), "{screen}");
}

#[test]
fn restart_friction_missing_run_identity_is_unavailable() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = trade_checkpoint();
    app.backend.run_id = None;

    let screen = render(&mut app, 4, 190, 52);

    assert!(screen.contains("CURRENT RUN ID UNAVAILABLE"), "{screen}");
    assert!(!screen.contains("CURRENT RUN FILL LEGS 0"), "{screen}");
}
