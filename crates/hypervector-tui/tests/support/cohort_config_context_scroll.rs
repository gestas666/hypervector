fn config_screen(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal.draw(|frame| hypervector_tui::ui::draw(frame, app)).expect("draw");
    let buffer = terminal.backend().buffer();
    (0..height).map(|y| (0..width).map(|x| buffer[(x, y)].symbol())
        .collect::<String>()).collect::<Vec<_>>().join("\n")
}

fn config_context_pages(app: &mut App, width: u16, height: u16) -> String {
    let mut seen = String::new();
    for _ in 0..100 {
        let before = config_screen(app, width, height);
        seen.push_str(&before);
        app.page_cohort_config_context(1);
        if config_screen(app, width, height) == before {
            return seen;
        }
    }
    panic!("configuration context did not reach its endpoint");
}

#[test]
fn configuration_context_pages_do_not_skip_live_sizing_at_the_hard_floor() {
    let mut app = config_app();
    app.active_tab = 8;
    let seen = config_context_pages(&mut app, 100, 28);
    assert!(seen.contains("LIVE SIZING BTC"), "{seen}");
    assert!(seen.contains("NEXT-RUN SIZING BTC"), "{seen}");
}

#[test]
fn configuration_context_exposes_long_source_and_request_outcome_at_all_sizes() {
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let mut app = config_app();
        app.active_tab = 8;
        app.backend.cohort.providers[0].source_profile =
            Some(format!("{} SOURCE-END", "recorded provider source ".repeat(20)));
        app.cohort_notice = Some(format!("{} OUTCOME-END", "exact backend reason ".repeat(30)));
        let seen = config_context_pages(&mut app, width, height);
        assert!(seen.contains("SOURCE-END"), "source clipped at {width}x{height}: {seen}");
        assert!(seen.contains("OUTCOME-END"), "outcome clipped at {width}x{height}: {seen}");
        assert!(seen.contains("LIVE ARMING IS CLI-ONLY"), "{seen}");
    }
}

#[test]
fn configuration_context_repeated_page_down_then_one_up_leaves_the_endpoint() {
    let mut app = config_app();
    app.active_tab = 8;
    app.cohort_notice = Some("full request outcome ".repeat(50));
    for _ in 0..100 {
        config_screen(&app, 100, 28);
        app.page_cohort_config_context(1);
    }
    let bottom = config_screen(&app, 100, 28);
    app.page_cohort_config_context(-1);
    assert_ne!(config_screen(&app, 100, 28), bottom);
}

#[test]
fn configuration_compact_footer_exposes_edit_and_action_keys() {
    let mut app = config_app();
    app.active_tab = 8;
    let screen = config_screen(&app, 100, 28);
    let footer = screen.lines().nth(26).expect("footer");
    for control in ["[↑/↓] Row", "[+/-] Edit", "[Enter] Act"] {
        assert!(footer.contains(control), "missing {control}: {footer}");
    }
}

#[test]
fn configuration_context_keeps_complete_identity_accessible_beyond_the_summary() {
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let mut app = config_app();
        app.active_tab = 8;
        app.backend.cohort.config_source_path =
            Some(format!("{} IDENTITY-END.toml", "recorded source path ".repeat(20)));
        let seen = config_context_pages(&mut app, width, height);
        assert!(seen.contains("IDENTITY-END.toml"), "identity clipped at {width}x{height}");
    }
}

fn staged_config_request() -> (App, String, tempfile::TempDir) {
    let folder = tempdir().expect("temporary inbox");
    fs::create_dir(folder.path().join("pending")).expect("pending");
    let mut app = config_app();
    app.active_tab = 8;
    app.set_cohort_command_inbox(Some(folder.path().to_path_buf()));
    app.select_next_cohort_config();
    app.adjust_cohort_config(1.0);
    for _ in 0..8 {
        app.select_next_cohort_config();
    }
    app.activate_cohort_config_row();
    let request = fs::read_dir(folder.path().join("pending")).expect("pending")
        .next().expect("request").expect("entry").path();
    let value: Value = serde_json::from_str(&fs::read_to_string(request).expect("read")).expect("json");
    (app, value["request_id"].as_str().expect("request ID").to_string(), folder)
}

fn profile_outcome(request_id: String, status: &str) -> hypervector_tui::backend_cohort::CohortOperatorEvent {
    hypervector_tui::backend_cohort::CohortOperatorEvent {
        observed_at: "2026-09-12T00:00:00Z".into(), request_id,
        status: status.into(), reason: Some(format!("{} OUTCOME-RECEIVED", "backend validation detail ".repeat(20))),
        action: Some("stage_profile".into()), symbol: Some("MULTI".into()), provider: None, side: None,
    }
}

#[test]
fn configuration_request_replaces_pending_with_exact_completed_or_rejected_outcome() {
    for status in ["completed", "rejected"] {
        let (mut app, id, _folder) = staged_config_request();
        app.backend.cohort.operator_events.push(profile_outcome(id.clone(), status));
        let seen = config_context_pages(&mut app, 100, 28);
        assert!(seen.contains(&format!("BACKEND {}", status.to_uppercase())), "{seen}");
        assert!(seen.contains("OUTCOME-RECEIVED"), "{seen}");
        assert!(!seen.contains("BACKEND VALIDATION PENDING"), "{seen}");
    }
}

#[test]
fn configuration_request_does_not_accept_another_requests_outcome() {
    let (mut app, id, _folder) = staged_config_request();
    app.backend.cohort.operator_events.push(profile_outcome("b".repeat(32), "completed"));
    let seen = config_context_pages(&mut app, 100, 28);
    assert!(seen.contains(&id), "{seen}");
    assert!(seen.contains("BACKEND VALIDATION PENDING"), "{seen}");
    assert!(!seen.contains("OUTCOME-RECEIVED"), "{seen}");
}

#[test]
fn configuration_request_does_not_reuse_an_outcome_after_backend_identity_changes() {
    for change_run in [true, false] {
        let (mut app, id, _folder) = staged_config_request();
        app.backend.cohort.operator_events.push(profile_outcome(id, "completed"));
        if change_run {
            app.backend.run_id = Some("another-run".into());
        } else {
            app.backend.profile_fingerprint = Some("c".repeat(64));
        }
        let seen = config_context_pages(&mut app, 100, 28);
        assert!(seen.contains("BACKEND IDENTITY CHANGED"), "{seen}");
        assert!(!seen.contains("BACKEND COMPLETED"), "{seen}");
    }
}

#[test]
fn configuration_discard_restores_local_notice_after_a_completed_request() {
    let (mut app, id, _folder) = staged_config_request();
    app.backend.cohort.operator_events.push(profile_outcome(id, "completed"));
    app.select_next_cohort_config();
    app.activate_cohort_config_row();
    let seen = config_context_pages(&mut app, 100, 28);
    assert!(seen.contains("DRAFT DISCARDED"), "{seen}");
    assert!(seen.contains("DRAFT CLEAN"), "{seen}");
    assert!(!seen.contains("BACKEND VALIDATION PENDING"), "{seen}");
}
