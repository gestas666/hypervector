//! Backend heartbeats, rather than file writes or acknowledgements, establish freshness.

use std::fs::{self, OpenOptions};
use std::io::Write;

use chrono::{Duration, Utc};
use hypervector_tui::backend_telemetry::BackendConnectionState;
use hypervector_tui::backend_telemetry::BackendTelemetrySource;
use serde_json::{Value, json};

fn event(sequence: u64, kind: &str, at: &str, mode: &str, payload: Value) -> String {
    json!({
        "schema_version": 1, "sequence": sequence, "event_type": kind,
        "observed_at_utc": at, "execution_mode": mode, "live_armed": mode == "live",
        "execution_authority": if mode == "live" { "hyperliquid_mainnet" } else { "none" },
        "run_id": "heartbeat-test", "profile_id": "heartbeat-fixture",
        "profile_fingerprint": "a".repeat(64), "payload": payload
    })
    .to_string()
}

fn content(mode: &str, heartbeat_at: &str, status: &str) -> String {
    let identity = event(
        1,
        "configuration_identity",
        heartbeat_at,
        mode,
        json!({
            "strategy_name": "multi_asset_bidirectional_cohort", "enabled_symbols": ["BTC"],
            "assets": [{"symbol": "BTC", "sides": ["long", "short"], "leverage": 5.0,
                        "venue_max_leverage": 40.0, "margin_fraction": 0.02,
                        "max_notional_usd": 25.0, "stop_bps": 80.0, "maximum_hold_seconds": 3600}],
            "providers": [{"strategy_id": "range_onset_bidirectional_v1", "symbols": ["BTC"],
                           "sides": ["long", "short"], "priority": 10, "timeframe": "1m",
                           "maximum_entry_delay_seconds": 60}],
            "position_policy": {"max_positions_per_symbol": 1, "maximum_concurrent_positions": 1}
        }),
    );
    let heartbeat = event(
        2,
        "heartbeat",
        heartbeat_at,
        mode,
        json!({"status": status}),
    );
    format!("{identity}\n{heartbeat}\n")
}

fn acknowledgement(sequence: u64, at: &str, mode: &str) -> String {
    event(
        sequence,
        "operator_command",
        at,
        mode,
        json!({
            "request_id": "b".repeat(32), "status": "completed", "action": "stage_profile",
            "symbol": "MULTI", "provider": null, "side": null, "reason": "isolated stage completed"
        }),
    )
}

#[test]
fn recently_copied_old_observer_is_stale() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let old = (Utc::now() - Duration::seconds(120)).to_rfc3339();
    fs::write(&path, content("observe", &old, "running")).expect("recorded observer");
    let snapshot = BackendTelemetrySource::new(path).refresh();
    assert_eq!(snapshot.connection, BackendConnectionState::Stale);
    assert!(snapshot.status_message.contains("heartbeat"));
}

#[test]
fn operator_event_compaction_does_not_discard_the_actual_heartbeat() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let old = (Utc::now() - Duration::seconds(120)).to_rfc3339();
    let now = Utc::now().to_rfc3339();
    let mut rows = content("observe", &old, "running");
    for sequence in 3..300 {
        rows.push_str(&acknowledgement(sequence, &now, "observe"));
        rows.push('\n');
    }
    fs::write(&path, rows).expect("compacted ledger");
    let snapshot = BackendTelemetrySource::new(path).refresh();
    assert_eq!(snapshot.connection, BackendConnectionState::Stale);
    assert_eq!(
        snapshot
            .cohort
            .heartbeat
            .expect("retained heartbeat")
            .observed_at,
        old
    );
}

#[test]
fn a_new_run_does_not_inherit_terminal_health_from_its_predecessor() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let now = Utc::now().to_rfc3339();
    let fault = event(
        3,
        "runtime_fault",
        &now,
        "observe",
        json!({"exception_type":"RuntimeError"}),
    );
    let mut rows = format!("{}{fault}\n", content("observe", &now, "running"));
    fs::write(&path, &rows).expect("faulted prior run");
    let mut source = BackendTelemetrySource::new(path.clone());
    assert_eq!(source.refresh().connection, BackendConnectionState::Error);
    rows.push_str(&content("observe", &now, "running").replace("heartbeat-test", "next-run"));
    fs::write(path, rows).expect("new run identity and heartbeat");
    let snapshot = source.refresh();
    assert_eq!(snapshot.connection, BackendConnectionState::Connected);
    assert_eq!(snapshot.run_id.as_deref(), Some("next-run"));
    assert!(snapshot.cohort.runtime_fault_at.is_none());
}

#[test]
fn explicit_runtime_stop_is_terminal_until_the_same_observer_actually_resumes() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let now = Utc::now().to_rfc3339();
    let stop = event(
        3,
        "runtime_stopped",
        &now,
        "observe",
        json!({"reason":"operator_stop"}),
    );
    let mut rows = format!("{}{stop}\n", content("observe", &now, "running"));
    rows.push_str(&format!("{}\n", acknowledgement(4, &now, "observe")));
    fs::write(&path, &rows).expect("normally stopped observer");
    let mut source = BackendTelemetrySource::new(path.clone());
    let stopped = source.refresh();
    assert_eq!(stopped.connection, BackendConnectionState::Stale);
    assert!(stopped.cohort_backend_is_stopped());
    rows.push_str(&event(
        5,
        "heartbeat",
        &now,
        "observe",
        json!({"status":"running"}),
    ));
    rows.push('\n');
    fs::write(path, rows).expect("actual resumed poll");
    let resumed = source.refresh();
    assert_eq!(resumed.connection, BackendConnectionState::Connected);
    assert!(!resumed.cohort_backend_is_stopped());
}

#[test]
fn stale_observer_does_not_claim_a_persistent_running_backend() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let old = (Utc::now() - Duration::seconds(120)).to_rfc3339();
    fs::write(&path, content("observe", &old, "running")).expect("inactive observer");
    let mut app =
        hypervector_tui::app::App::new("MULTI".into(), "1m".into(), Vec::new(), true, false);
    app.backend = BackendTelemetrySource::new(path).refresh();
    app.detached_lifecycle = true;
    let text = screen(&mut app, 100, 28);
    assert!(text.contains("MONITOR-ONLY QUIT"), "{text}");
    assert!(!text.contains("BACKEND PERSISTS ON QUIT"));
    assert!(!text.contains("Quit keeps backend"));
    assert!(!text.contains("Quit leaves backend running"));
}

#[test]
fn stopped_timestamps_and_later_faults_cannot_claim_a_clean_shutdown() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let now = Utc::now().to_rfc3339();
    let future = (Utc::now() + Duration::seconds(120)).to_rfc3339();
    for at in ["not-a-clock", future.as_str(), now.as_str()] {
        let stop = event(
            3,
            "runtime_stopped",
            at,
            "observe",
            json!({"reason":"operator_stop"}),
        );
        let mut rows = format!("{}{stop}\n", content("observe", &now, "running"));
        if at == now {
            rows.push_str(&event(
                4,
                "runtime_fault",
                &now,
                "observe",
                json!({"exception_type":"OSError"}),
            ));
            rows.push('\n');
        }
        fs::write(&path, rows).expect("invalid stopped evidence");
        let result = BackendTelemetrySource::new(path.clone()).refresh();
        assert_eq!(result.connection, BackendConnectionState::Error);
        assert!(!result.cohort_backend_is_stopped());
    }
}

#[test]
fn fresh_acknowledgement_cannot_revive_an_old_armed_heartbeat() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let old = (Utc::now() - Duration::seconds(120)).to_rfc3339();
    let rows = format!(
        "{}{}\n",
        content("live", &old, "running"),
        acknowledgement(3, &Utc::now().to_rfc3339(), "live")
    );
    fs::write(&path, rows).expect("recorded armed evidence with recent acknowledgement");
    let snapshot = BackendTelemetrySource::new(path).refresh();
    assert_eq!(snapshot.connection, BackendConnectionState::Stale);
    assert_eq!(snapshot.cohort.operator_events.len(), 1);
}

#[test]
fn a_real_fresh_heartbeat_recovers_an_inactive_observer() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let old = (Utc::now() - Duration::seconds(120)).to_rfc3339();
    fs::write(&path, content("observe", &old, "running")).expect("old heartbeat");
    let mut source = BackendTelemetrySource::new(path.clone());
    assert_eq!(source.refresh().connection, BackendConnectionState::Stale);
    let mut file = OpenOptions::new()
        .append(true)
        .open(path)
        .expect("append ledger");
    writeln!(
        file,
        "{}",
        event(
            3,
            "heartbeat",
            &Utc::now().to_rfc3339(),
            "observe",
            json!({"status": "running"})
        )
    )
    .expect("new heartbeat");
    assert_eq!(
        source.refresh().connection,
        BackendConnectionState::Connected
    );
}

#[test]
fn fresh_degraded_heartbeat_does_not_claim_healthy_connection() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    fs::write(
        &path,
        content("observe", &Utc::now().to_rfc3339(), "degraded"),
    )
    .expect("degraded heartbeat");
    let snapshot = BackendTelemetrySource::new(path).refresh();
    assert_eq!(snapshot.connection, BackendConnectionState::Stale);
    assert!(snapshot.status_message.contains("degraded"));
}

#[test]
fn future_heartbeat_is_not_current_health_evidence() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let future = (Utc::now() + Duration::seconds(120)).to_rfc3339();
    fs::write(&path, content("observe", &future, "running")).expect("future heartbeat");
    let snapshot = BackendTelemetrySource::new(path).refresh();
    assert_ne!(snapshot.connection, BackendConnectionState::Connected);
    assert!(snapshot.status_message.contains("future"));
}

#[test]
fn terminal_fault_outlives_subsequent_operator_acknowledgements() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let now = Utc::now().to_rfc3339();
    let fault = event(
        3,
        "runtime_fault",
        &now,
        "live",
        json!({"exception_type": "RuntimeError"}),
    );
    fs::write(
        &path,
        format!(
            "{}{fault}\n{}\n",
            content("live", &now, "running"),
            acknowledgement(4, &now, "live")
        ),
    )
    .expect("terminal fault");
    let snapshot = BackendTelemetrySource::new(path).refresh();
    assert_eq!(snapshot.connection, BackendConnectionState::Error);
    assert!(snapshot.status_message.contains("terminal"));
}

#[test]
fn missing_or_invalid_heartbeat_cannot_claim_current_health() {
    for rows in [
        content("observe", "not-a-clock", "running"),
        content("observe", &Utc::now().to_rfc3339(), "unrecognized"),
        content("observe", &Utc::now().to_rfc3339(), "stopped"),
        content("observe", &Utc::now().to_rfc3339(), "running")
            .lines()
            .next()
            .expect("identity")
            .to_string(),
    ] {
        let directory = tempfile::tempdir().expect("temporary ledger");
        let path = directory.path().join("decisions.jsonl");
        fs::write(&path, rows).expect("unavailable health evidence");
        let snapshot = BackendTelemetrySource::new(path).refresh();
        assert_ne!(snapshot.connection, BackendConnectionState::Connected);
    }
}

fn screen(app: &mut hypervector_tui::App, width: u16, height: u16) -> String {
    let mut terminal = ratatui::Terminal::new(ratatui::backend::TestBackend::new(width, height))
        .expect("terminal");
    let frame = terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw");
    frame
        .buffer
        .content()
        .iter()
        .map(|cell| cell.symbol())
        .collect()
}

#[test]
fn header_uses_heartbeat_clock_instead_of_recent_operator_clock() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    let old = Utc::now() - Duration::seconds(120);
    fs::write(
        &path,
        format!(
            "{}{}\n",
            content("observe", &old.to_rfc3339(), "running"),
            acknowledgement(3, &Utc::now().to_rfc3339(), "observe")
        ),
    )
    .expect("old heartbeat and new acknowledgement");
    let mut app = hypervector_tui::App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(BackendTelemetrySource::new(path).refresh());
    let clock = old
        .with_timezone(&chrono_tz::America::New_York)
        .format("%H:%M:%S %Z");
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let text = screen(&mut app, width, height);
        assert!(text.contains(&format!("HEARTBEAT {clock}")), "{text}");
        assert!(text.contains("BACKEND STALE"));
    }
}

#[test]
fn stopped_heartbeat_does_not_claim_backend_persists_after_quit() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    fs::write(
        &path,
        content("observe", &Utc::now().to_rfc3339(), "stopped"),
    )
    .expect("stopped heartbeat");
    let mut app = hypervector_tui::App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.apply_backend_telemetry(BackendTelemetrySource::new(path).refresh());
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let text = screen(&mut app, width, height);
        assert!(text.contains("BACKEND STOPPED"), "{text}");
        assert!(text.contains("MONITOR-ONLY QUIT"), "{text}");
        assert!(!text.contains("BACKEND PERSISTS ON QUIT"), "{text}");
    }
}

#[test]
fn chart_reports_source_candle_age_independently_of_fresh_heartbeat() {
    let directory = tempfile::tempdir().expect("temporary ledger");
    let path = directory.path().join("decisions.jsonl");
    fs::write(
        &path,
        content("observe", &Utc::now().to_rfc3339(), "running"),
    )
    .expect("fresh heartbeat");
    let mut app = hypervector_tui::App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(BackendTelemetrySource::new(path).refresh());
    let minute = 60_000_u64;
    let latest = Utc::now().timestamp_millis() as u64 / minute * minute;
    let bars = (0..10)
        .map(|index| hypervector_tui::backend_cohort::CohortCandle {
            timestamp_ms: latest - 12 * minute + index * minute,
            open: 100.0,
            high: 102.0,
            low: 99.0,
            close: 101.0,
            volume: 1.0,
        })
        .collect();
    app.backend.cohort.candle_history.insert("BTC".into(), bars);
    app.show_cohort_chart_modal = true;
    assert_eq!(app.backend.connection, BackendConnectionState::Connected);
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        let text = screen(&mut app, width, height);
        assert!(text.contains("1M CANDLE AGE"), "{text}");
        assert!(text.contains("BOOK AGE UNAVAILABLE"), "{text}");
    }
}
