//! Opt-in, read-only acceptance against the operator's checkpoint and ledger.

use std::{fs, path::PathBuf};

use hypervector_tui::{
    App,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySnapshot, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

#[test]
#[ignore = "requires explicit local ledger, checkpoint and new capture directory"]
fn research_import_status_renders_with_current_backend_on_all_nine_screens() {
    let root = required_path("HYPERVECTOR_SYNC_QA_ROOT");
    let checkpoint = required_path("HYPERVECTOR_SYNC_QA_CHECKPOINT");
    let output = required_path("HYPERVECTOR_SYNC_QA_OUTPUT");
    fs::create_dir(&output).expect("capture directory must not already exist");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join("data/live/bidirectional_cohort/decisions.jsonl"),
        Some(checkpoint.clone()),
    );
    let backend = source.refresh();
    assert_checkpoint_parity(&backend, &checkpoint);
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.apply_backend_telemetry(backend);
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        for tab in 0..9 {
            app.active_tab = tab;
            let screen = render(&app, width, height);
            assert!(screen.contains("IMPORT "), "{screen}");
            assert!(!screen.contains("IMPORT UNREPORTED"), "{screen}");
            assert!(screen.contains("[9] CFG"), "{screen}");
            assert!(screen.contains("LIVE EXECUTION ARMED"), "{screen}");
            fs::write(
                output.join(format!("screen_{}_{width}x{height}.txt", tab + 1)),
                screen,
            )
            .expect("write read-only screen capture");
        }
    }
}

fn assert_checkpoint_parity(backend: &BackendTelemetrySnapshot, checkpoint: &PathBuf) {
    assert_eq!(backend.connection, BackendConnectionState::Connected);
    let document: serde_json::Value =
        serde_json::from_slice(&fs::read(checkpoint).expect("checkpoint")).expect("JSON");
    assert_eq!(
        backend.profile_id.as_deref(),
        document["audit"]["run"]["profile_id"].as_str()
    );
    let status = backend
        .cohort_checkpoint
        .research_sync
        .as_ref()
        .expect("import status");
    assert_eq!(
        status.last_imported_events,
        document["research_sync"]["last_imported_events"].as_u64()
    );
    assert_eq!(
        status.error.as_deref(),
        document["research_sync"]["error"].as_str()
    );
}

fn required_path(name: &str) -> PathBuf {
    PathBuf::from(std::env::var_os(name).unwrap_or_else(|| panic!("{name} required")))
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("render");
    terminal.backend().to_string()
}
