#[test]
fn routing_summary_distinguishes_capacity_from_tradable_assets() {
    let mut app = complete_portfolio_app();
    app.backend.cohort.maximum_concurrent_positions = 10;

    let router = render(&mut app, 1, 190, 52);

    assert!(router.contains("SLOTS 1 / 10"), "{router}");
    assert!(router.contains("ASSETS 9"), "{router}");
}

fn complete_portfolio_app() -> App {
    let mut app = cohort_app();
    let template = app.backend.cohort.assets[0].clone();
    app.backend.cohort.enabled_symbols = COMPLETE_SYMBOLS.map(str::to_string).to_vec();
    app.backend.cohort.assets = COMPLETE_SYMBOLS
        .into_iter()
        .map(|symbol| {
            let mut asset = template.clone();
            asset.symbol = symbol.into();
            asset
        })
        .collect();
    app
}

#[test]
fn transition_drain_projection_distinguishes_unavailable_and_inactive() {
    let unavailable = cohort_backend();
    assert!(unavailable.cohort.transition_drain.is_none());

    let null_ledger = [identity(), snapshot_with_transition_drain(2, Value::Null)].join("\n");
    let null = parse_backend_telemetry(&format!("{null_ledger}\n")).expect("null drain");
    assert!(null.cohort.transition_drain.is_none());

    let inactive = backend_with_transition_drain(transition_drain("inactive"));
    let state = inactive
        .cohort
        .transition_drain
        .expect("explicit inactive drain state");
    assert_eq!(state.status, "inactive");
    assert!(state.request_id.is_none());
}

#[test]
fn transition_drain_projection_accepts_active_and_completed_states() {
    let active = backend_with_transition_drain(transition_drain("active"));
    let state = active.cohort.transition_drain.expect("active drain");
    assert_eq!(state.status, "active");
    assert_eq!(state.origin_run_id.as_deref(), Some("cohort-test"));
    assert_eq!(state.resume_count, 0);
    assert!(state.last_resumed_at_utc.is_none());
    assert_eq!(
        state.request_id.as_deref(),
        Some("dddddddddddddddddddddddddddddddd")
    );
    assert!(state.completed_at_utc.is_none());

    let completed = backend_with_transition_drain(transition_drain("completed"));
    let state = completed.cohort.transition_drain.expect("completed drain");
    assert_eq!(state.status, "completed");
    assert_eq!(
        state.completed_at_utc.as_deref(),
        Some("2026-08-01T16:00:00+00:00")
    );

    for status in ["active", "completed"] {
        let backend = backend_with_transition_drain(resumed_transition_drain(status));
        let state = backend.cohort.transition_drain.expect("resumed drain");
        assert_eq!(state.origin_run_id.as_deref(), Some("origin-live-001"));
        assert_eq!(state.resume_count, 2);
        assert_eq!(
            state.last_resumed_at_utc.as_deref(),
            Some("2026-08-01T15:59:59.500+00:00")
        );
    }
}

#[test]
fn transition_drain_projection_rejects_inconsistent_states() {
    let cases = [
        json!({
            "status": "inactive", "request_id": "d".repeat(32),
            "origin_run_id": null,
            "run_id": "cohort-test", "profile_fingerprint": "a".repeat(64),
            "requested_at_utc": null, "activated_at_utc": null,
            "resume_count": 0, "last_resumed_at_utc": null, "completed_at_utc": null
        }),
        json!({
            "status": "active", "request_id": null,
            "origin_run_id": "cohort-test",
            "run_id": "cohort-test", "profile_fingerprint": "a".repeat(64),
            "requested_at_utc": "2026-08-01T15:59:58+00:00",
            "activated_at_utc": "2026-08-01T15:59:59+00:00",
            "resume_count": 0, "last_resumed_at_utc": null, "completed_at_utc": null
        }),
        json!({
            "status": "completed", "request_id": "d".repeat(32),
            "origin_run_id": "cohort-test",
            "run_id": "cohort-test", "profile_fingerprint": "a".repeat(64),
            "requested_at_utc": "2026-08-01T15:59:58+00:00",
            "activated_at_utc": "2026-08-01T15:59:59+00:00",
            "resume_count": 0, "last_resumed_at_utc": null, "completed_at_utc": null
        }),
        json!({
            "status": "paused", "request_id": null,
            "origin_run_id": null,
            "run_id": "cohort-test", "profile_fingerprint": "a".repeat(64),
            "requested_at_utc": null, "activated_at_utc": null,
            "resume_count": 0, "last_resumed_at_utc": null, "completed_at_utc": null
        }),
        json!({
            "status": "active", "request_id": "d".repeat(32),
            "origin_run_id": "origin-live-001",
            "run_id": "cohort-test", "profile_fingerprint": "a".repeat(64),
            "requested_at_utc": "2026-08-01T15:59:58+00:00",
            "activated_at_utc": "2026-08-01T15:59:59+00:00",
            "resume_count": 1, "last_resumed_at_utc": null, "completed_at_utc": null
        }),
        json!({
            "status": "active", "request_id": "d".repeat(32),
            "origin_run_id": "origin-live-001",
            "run_id": "cohort-test", "profile_fingerprint": "a".repeat(64),
            "requested_at_utc": "2026-08-01T15:59:58+00:00",
            "activated_at_utc": "2026-08-01T15:59:59+00:00",
            "resume_count": 1,
            "last_resumed_at_utc": "2026-08-01T15:59:58.500+00:00",
            "completed_at_utc": null
        }),
    ];
    for drain in cases {
        let ledger = [identity(), snapshot_with_transition_drain(2, drain)].join("\n");
        let error = parse_backend_telemetry(&format!("{ledger}\n"))
            .expect_err("inconsistent drain accepted");
        assert!(error.to_string().contains("transition drain"), "{error}");
    }
}

#[test]
fn transition_drain_projection_rejects_nested_identity_mismatch() {
    let mut mismatched_run = transition_drain("active");
    mismatched_run["run_id"] = json!("different-run");
    let mut mismatched_profile = transition_drain("active");
    mismatched_profile["profile_fingerprint"] = json!("b".repeat(64));

    for drain in [mismatched_run, mismatched_profile] {
        let ledger = [identity(), snapshot_with_transition_drain(2, drain)].join("\n");
        let error = parse_backend_telemetry(&format!("{ledger}\n"))
            .expect_err("mismatched nested drain identity accepted");
        assert!(
            error
                .to_string()
                .contains("transition drain identity differs from cohort snapshot"),
            "{error}"
        );
    }
}

#[test]
fn operator_projection_accepts_drained_transition_lifecycle() {
    let operator = row(
        3,
        "operator_command",
        json!({
            "request_id": "d".repeat(32),
            "status": "drained",
            "reason": "portfolio flat with no owned order identities",
            "action": "transition_drain",
            "symbol": "MULTI",
            "provider": null,
            "side": null
        }),
    );
    let ledger = [
        identity(),
        snapshot_with_transition_drain(2, transition_drain("completed")),
        operator,
    ]
    .join("\n");
    let backend = parse_backend_telemetry(&format!("{ledger}\n")).expect("drained event");

    assert_eq!(backend.cohort.operator_events[0].status, "drained");
    assert_eq!(
        backend.cohort.operator_events[0].action.as_deref(),
        Some("transition_drain")
    );
}

#[test]
fn transition_drain_control_builds_portfolio_draft_without_a_selected_coin() {
    let mut app = cohort_app();
    app.cohort_command_inbox = Some("data/live/bidirectional_cohort/operator_commands".into());
    app.selected_cohort_symbol_index = usize::MAX;

    app.move_cohort_control_focus(2);
    app.prepare_cohort_confirmation();

    assert_eq!(app.cohort_control_focus, 2);
    let draft = app.cohort_confirmation.expect("transition drain draft");
    assert_eq!(draft.symbol, "MULTI");
    assert_eq!(draft.action, CohortOperatorAction::TransitionDrain);
}

#[test]
fn transition_drain_control_renders_truthful_statuses_at_acceptance_size() {
    let cases = [
        (
            None,
            [
                "DRAIN UNKNOWN // BACKEND STATUS UNAVAILABLE",
                "STATE UNAVAILABLE // DO NOT INFER INACTIVE",
                "NO BACKEND DRAIN STATUS WAS REPORTED",
                "NO DRAIN REQUEST STATUS CLAIMED",
            ],
        ),
        (
            Some("inactive"),
            [
                "DRAIN INACTIVE // READY",
                "STATE INACTIVE // READY // DEFAULT-OFF",
                "AUTOMATIC ENTRY + EXIT ROUTING ACTIVE",
                "SELECT TO WITHHOLD NEW ENTRIES",
            ],
        ),
        (
            Some("active"),
            [
                "DRAIN ACTIVE // ENTRY ADMISSION OFF",
                "STATE ACTIVE // NEW ENTRIES WITHHELD",
                "EXITS + VENUE PROTECTION CONTINUE",
                "NO PROFILE START // NO AUTO RESTART",
            ],
        ),
        (
            Some("completed"),
            [
                "DRAIN COMPLETE // BACKEND STOPPING OR STOPPED",
                "STATE COMPLETED // FLAT + UNOWNED VERIFIED",
                "BACKEND STOPPING OR STOPPED",
                "ARCHIVE DRAIN EVIDENCE BEFORE NEXT START",
            ],
        ),
    ];
    for (status, expected_lines) in cases {
        let backend = status.map_or_else(cohort_backend, |value| {
            backend_with_transition_drain(transition_drain(value))
        });
        let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        app.apply_backend_telemetry(backend);

        let screen = render(&mut app, 6, 120, 36);

        for expected in expected_lines {
            assert!(screen.contains(expected), "missing {expected}\n{screen}");
        }
        assert!(screen.contains("MANUAL STRATEGY ENTRY"), "{screen}");
        assert!(screen.contains("MANUAL POSITION CLOSE"), "{screen}");
        assert!(screen.contains("TRANSITION DRAIN"), "{screen}");
        assert!(
            screen.contains("NO MANUAL COMMANDS RECORDED // AUTO ROUTING CONTINUES"),
            "{screen}"
        );
    }
}

#[test]
fn active_resumed_transition_drain_renders_recovery_identity_without_losing_safety_copy() {
    let backend = backend_with_transition_drain(resumed_transition_drain("active"));
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);

    let screen = render(&mut app, 6, 120, 36);

    assert!(
        screen.contains("RECOVERY #2 // ORIGIN origin-live-001"),
        "{screen}"
    );
    assert!(
        screen.contains("STATE ACTIVE // NEW ENTRIES WITHHELD"),
        "{screen}"
    );
    assert!(
        screen.contains("EXITS + VENUE PROTECTION CONTINUE"),
        "{screen}"
    );
    assert!(
        screen.contains("NO PROFILE START // NO AUTO RESTART"),
        "{screen}"
    );
}

#[test]
fn transition_drain_confirmation_states_backend_authority_boundary() {
    let mut app = cohort_app();
    app.cohort_command_inbox = Some("data/live/bidirectional_cohort/operator_commands".into());
    app.move_cohort_control_focus(2);
    app.prepare_cohort_confirmation();

    let screen = render(&mut app, 6, 120, 36);

    assert!(screen.contains("ACTION TRANSITION DRAIN"), "{screen}");
    assert!(screen.contains("NO DIRECT VENUE ORDER"), "{screen}");
    assert!(
        screen.contains("EXITS AND VENUE PROTECTION CONTINUE"),
        "{screen}"
    );
    assert!(
        screen.contains("NO PROFILE IS ACTIVATED OR STARTED AUTOMATICALLY"),
        "{screen}"
    );
}
