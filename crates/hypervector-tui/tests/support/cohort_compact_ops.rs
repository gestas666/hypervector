#[test]
fn compact_ops_keeps_action_details_and_drain_effects_visible() {
    let mut app = cohort_app();
    app.apply_backend_telemetry(backend_with_transition_drain(transition_drain("active")));
    for (width, height) in [(100, 28), (100, 29), (119, 35), (120, 36), (190, 52)] {
        for focus in 0..3 {
            app.cohort_control_focus = focus;
            let screen = render(&mut app, 6, width, height);
            for required in [
                "PROVIDER", "SIDE LONG", "POSITION LONG", "BYPASS:",
                "venue checks", "reduce-only IOC", "VERIFY venue flat",
                "SELECTED", "[Enter] REVIEW", "NEW ENTRIES WITHHELD",
                "EXITS + VENUE PROTECTION CONTINUE", "NO AUTO RESTART",
            ] {
                assert!(screen.contains(required), "missing {required} at {width}x{height}\n{screen}");
            }
        }
    }
}

#[test]
fn compact_ops_confirmation_retains_action_scope_submit_and_cancel() {
    for (width, height) in [(100, 28), (119, 28), (120, 36), (190, 52)] {
        for focus in 0..3 {
            let mut app = cohort_app();
            app.cohort_command_inbox = Some("unused-compact-ops-inbox".into());
            app.cohort_control_focus = focus;
            app.selected_cohort_symbol_index = usize::from(focus == 0);
            app.prepare_cohort_confirmation();
            assert!(app.cohort_confirmation.is_some());
            let screen = render(&mut app, 6, width, height);
            for required in ["ACTION", "[y] CONFIRM AND SUBMIT", "[n/Esc] CANCEL"] {
                assert!(screen.contains(required), "missing {required} at {width}x{height}\n{screen}");
            }
            if focus == 2 {
                assert!(screen.contains("EXITS AND VENUE PROTECTION CONTINUE"), "{screen}");
                assert!(screen.contains("NO PROFILE IS ACTIVATED OR STARTED AUTOMATICALLY"), "{screen}");
            } else {
                let coin = if focus == 0 { "COIN ETH" } else { "COIN BTC" };
                assert!(screen.contains(coin), "{screen}");
                assert!(screen.contains("configured isolated sizing"), "{screen}");
                assert!(screen.contains("protective stop"), "{screen}");
            }
        }
    }
}

#[test]
fn compact_ops_latest_command_keeps_full_noncrypto_symbol_and_reason() {
    let mut app = cohort_app();
    app.backend.cohort.operator_events.push(serde_json::from_value(json!({
        "request_id": "deadbeef-request", "status": "rejected", "operator_action": "manual_enter",
        "symbol": "xyz:BRENTOIL", "provider": "test_provider", "side": "short",
        "reason": "owned_stop_not_cancellable"
    })).unwrap());
    for (width, height) in [(100, 28), (119, 35), (120, 36), (190, 52)] {
        let screen = render(&mut app, 6, width, height);
        for required in ["deadbeef", "REJECTED", "manual_enter", "xyz:BRENTOIL", "owned_stop_not_cancellable"] {
            assert!(screen.contains(required), "missing {required} at {width}x{height}\n{screen}");
        }
    }
}

#[test]
fn compact_ops_footer_keeps_full_navigation_and_review_shortcut() {
    let mut app = cohort_app();
    let screen = render(&mut app, 6, 100, 28);
    for required in ["[1-9]", "[q]", "[←/→]", "[p/P]", "[d]", "[↑/↓]", "[Enter] Review"] {
        assert!(screen.contains(required), "missing {required}\n{screen}");
    }
}

#[test]
fn compact_ops_command_notice_wraps_without_hiding_its_resolution() {
    let mut app = cohort_app();
    app.cohort_notice = Some(
        "REQUEST NOT SUBMITTED: the backend stopped after confirmation. The position and its owned stop remain unchanged. Review the latest backend status before retrying."
            .into(),
    );
    let screen = render(&mut app, 6, 100, 28);
    assert!(screen.contains("REQUEST NOT SUBMITTED"), "{screen}");
    assert!(screen.contains("before retrying."), "{screen}");
    assert!(screen.contains("PROVIDER"), "{screen}");
}

#[test]
fn compact_ops_stopped_snapshot_preserves_disabled_authority_and_action_details() {
    let mut app = cohort_app();
    app.cohort_command_inbox = Some("unused-compact-ops-inbox".into());
    mark_restart_snapshot_stopped(&mut app, "stopped_consistent");
    let screen = render(&mut app, 6, 100, 28);
    for required in ["BACKEND STOPPED", "MANUAL REQUESTS DISABLED", "PROVIDER", "POSITION LONG"] {
        assert!(screen.contains(required), "missing {required}\n{screen}");
    }
    assert!(!screen.contains("REQUEST CHANNEL ENABLED"), "{screen}");
    app.prepare_cohort_confirmation();
    assert!(app.cohort_confirmation.is_none());
}
