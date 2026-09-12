fn hold_notice_app(stopped: bool) -> App {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = trade_checkpoint();
    let mut trade = open_regime_trade_reflection();
    trade.exit_plan.opened_at_ms = Some(1_785_600_000_000);
    trade.exit_plan.timer_origin = Some("persisted_runtime_opened_at".into());
    trade.exit_plan.as_of_timestamp_ms = Some(1_785_619_886_090);
    app.backend.cohort_checkpoint.open_trade_reflections = vec![trade];
    for asset in &mut app.backend.cohort.assets {
        asset.position_size_signed = if asset.symbol == "BTC" { -1.0 } else { 0.0 };
        asset.entry_oid = if asset.symbol == "BTC" { Some(508_726_900_000) } else { None };
    }
    app.backend.cohort.account.as_mut().unwrap().open_position_count = 1;
    if stopped {
        mark_restart_snapshot_stopped(&mut app, "stopped_consistent");
    } else {
        app.backend.connection = BackendConnectionState::Stale;
    }
    app
}

#[test]
fn open_hold_view_stopped_overdue_warning_is_visible_on_all_nine_screens() {
    let mut app = hold_notice_app(true);
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        for tab in 0..9 {
            let screen = render(&mut app, tab, width, height);
            for required in ["LAST OPEN BTC", "IF STILL OPEN", "EXITS OFF", " OLD", "STOPPED SNAPSHOT"] {
                assert!(screen.contains(required), "{required} at {width}x{height} tab {tab}: {screen}");
            }
            assert!(!screen.contains("BACKEND CONNECTED"));
        }
    }
}

#[test]
fn open_hold_view_reports_unknown_management_and_missing_hold_data() {
    let mut app = hold_notice_app(false);
    let screen = render(&mut app, 0, 100, 28);
    assert!(screen.contains("EXITS UNKNOWN"), "{screen}");
    app.backend.cohort_checkpoint.open_trade_reflections.clear();
    let screen = render(&mut app, 0, 100, 28);
    assert!(screen.contains("HOLD DATA MISSING"), "{screen}");
    assert!(!screen.contains("IF STILL OPEN"), "a missing plan cannot invent a deadline");
}

#[test]
fn open_hold_view_does_not_merge_conflicting_position_identities() {
    let mut app = hold_notice_app(true);
    app.backend.cohort.assets.iter_mut().find(|a| a.symbol == "BTC").unwrap().entry_oid = Some(999);
    let screen = render(&mut app, 0, 100, 28);
    assert!(screen.contains("POSITION EVIDENCE CONFLICT"), "{screen}");
    assert!(!screen.contains("FIXED +"), "a different position cannot inherit this timer");
}

#[test]
fn open_hold_view_flat_snapshot_does_not_invent_open_exposure() {
    let mut app = hold_notice_app(true);
    app.backend.cohort_checkpoint.open_trade_reflections.clear();
    for asset in &mut app.backend.cohort.assets { asset.position_size_signed = 0.0; }
    app.backend.cohort.account.as_mut().unwrap().open_position_count = 0;
    let screen = render(&mut app, 0, 100, 28);
    assert!(!screen.contains("LAST OPEN"));
    assert!(!screen.contains("HOLD DATA MISSING"));
}

#[test]
fn open_hold_view_missing_position_rows_cannot_erase_declared_exposure() {
    let mut app = hold_notice_app(true);
    app.backend.cohort.assets.clear();
    app.backend.cohort_checkpoint.open_trade_reflections.clear();
    app.backend.cohort.account.as_mut().unwrap().open_position_count = 1;
    let screen = render(&mut app, 0, 100, 28);
    assert!(screen.contains("POSITION EVIDENCE CONFLICT"), "{screen}");
}

fn make_hold_evidence_fresh(app: &mut App) {
    let now = u64::try_from(chrono::Utc::now().timestamp_millis()).unwrap();
    let plan = &mut app.backend.cohort_checkpoint.open_trade_reflections[0].exit_plan;
    plan.as_of_timestamp_ms = Some(now);
    plan.soft_deadline_timestamp_ms = now + 3_600_000;
    plan.deadline_timestamp_ms = plan.soft_deadline_timestamp_ms;
    app.backend.connection = BackendConnectionState::Connected;
    app.backend.live_armed = Some(true);
    app.backend.cohort_checkpoint.available = true;
    app.backend.cohort_checkpoint.stale = false;
}

#[test]
fn open_hold_view_prioritizes_uncertain_trade_over_fresh_earlier_deadline() {
    let mut app = hold_notice_app(false);
    make_hold_evidence_fresh(&mut app);
    let mut uncertain = app.backend.cohort_checkpoint.open_trade_reflections[0].clone();
    uncertain.symbol = "ETH".into();
    uncertain.lifecycle_id = "ETH:999".into();
    uncertain.exit_plan.as_of_timestamp_ms = None;
    uncertain.exit_plan.soft_deadline_timestamp_ms += 3_600_000;
    uncertain.exit_plan.deadline_timestamp_ms = uncertain.exit_plan.soft_deadline_timestamp_ms;
    app.backend.cohort_checkpoint.open_trade_reflections.push(uncertain);
    let asset = app.backend.cohort.assets.iter_mut().find(|a| a.symbol == "ETH").unwrap();
    asset.position_size_signed = -1.0;
    asset.entry_oid = Some(999);
    app.backend.cohort.account.as_mut().unwrap().open_position_count = 2;
    let screen = render(&mut app, 0, 100, 28);
    assert!(screen.contains("LAST OPEN ETH +1"), "{screen}");
    assert!(screen.contains("AGE UNKNOWN"), "{screen}");
}

#[test]
fn open_hold_view_fresh_polling_has_no_warning_but_unarmed_is_explicit() {
    let mut app = hold_notice_app(false);
    make_hold_evidence_fresh(&mut app);
    let screen = render(&mut app, 0, 100, 28);
    assert!(!screen.contains("LAST OPEN"), "{screen}");
    app.backend.live_armed = Some(false);
    let screen = render(&mut app, 0, 100, 28);
    assert!(screen.contains("LOCAL EXITS UNARMED"), "{screen}");
}
