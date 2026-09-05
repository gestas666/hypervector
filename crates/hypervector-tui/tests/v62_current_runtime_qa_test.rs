use std::path::PathBuf;

use hypervector_tui::{
    App,
    backend_hip3_roster::Hip3RosterSource,
    backend_hype_l2_observer::HypeL2ObserverSource,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

const ACTIVE_LEDGER: &str = "data/live/bidirectional_cohort/decisions.jsonl";
const ACTIVE_CHECKPOINT: &str = "data/runtime/bidirectional_cohort/latest_checkpoint.json";
const HYPE_L2_STATUS: &str = "data/runtime/research/hype_l2_ridge_observer_latest.json";
const HIP3_ROSTER_STATUS: &str = "data/runtime/research/hip3_roster_latest.json";
const COMMAND_INBOX: &str = "data/live/bidirectional_cohort/operator_commands";
const PROFILE: &str = "multi_asset_growth_first_5000_eight_asset_hype_a60_candidate_v62";
const FINGERPRINT: &str = "a7cabf8bc59f38ba41898c2d1339e10c8dcc7c8a7a2940429f0ededefd928f8a";
const SYMBOLS: [&str; 8] = [
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
];

#[test]
#[ignore = "requires the local active V62 ledger and checkpoint"]
fn active_v62_renders_current_data_on_all_nine_screens() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(ACTIVE_CHECKPOINT)),
    );
    let mut backend = source.refresh();
    backend.hype_l2_observer = HypeL2ObserverSource::new(Some(root.join(HYPE_L2_STATUS))).refresh();
    backend.hip3_roster = Hip3RosterSource::new(Some(root.join(HIP3_ROSTER_STATUS))).refresh();

    assert!(matches!(
        backend.connection,
        BackendConnectionState::Connected | BackendConnectionState::Stale
    ));
    assert_eq!(backend.profile_id.as_deref(), Some(PROFILE));
    assert_eq!(backend.profile_fingerprint.as_deref(), Some(FINGERPRINT));
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS.map(str::to_string));
    assert!(
        backend.cohort_checkpoint.available,
        "V62 checkpoint unavailable: {:?}",
        backend.cohort_checkpoint.issue
    );
    assert_eq!(
        backend.cohort_checkpoint.lifecycle_state.as_deref(),
        Some("stale_running_heartbeat_after_asset_stop")
    );
    let performance = backend
        .cohort_checkpoint
        .trade_performance
        .as_ref()
        .expect("V62 Screen 5 performance");
    assert!(
        performance
            .current_run
            .as_ref()
            .is_some_and(|run| run.total.closed_trades > 0)
    );
    assert!(
        backend
            .cohort_checkpoint
            .all_time_performance()
            .is_some_and(|history| history.total.closed_trades > 0)
    );
    assert!(!backend.cohort_checkpoint.open_trade_reflections.is_empty());
    assert!(!backend.cohort_checkpoint.fill_details.is_empty());

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.set_cohort_command_inbox(Some(root.join(COMMAND_INBOX)));
    app.apply_backend_telemetry(backend);
    for tab in 1..=9 {
        app.active_tab = tab - 1;
        let screen = render(&app);
        println!("\n===== V62 SCREEN {tab} =====\n{screen}");
        assert_core_data_visible(tab, &screen);
    }
}

fn assert_core_data_visible(tab: usize, screen: &str) {
    for invalid in [
        "BACKEND DISCONNECTED",
        "ANALYSIS UNAVAILABLE",
        "IDENTITY MISMATCH",
        "PATH IDENTITY INVALID",
    ] {
        assert!(
            !screen.contains(invalid),
            "screen {tab}: {invalid}\n{screen}"
        );
    }
    if matches!(tab, 1 | 2) {
        for symbol in SYMBOLS {
            assert!(
                screen.contains(symbol),
                "screen {tab} missing {symbol}\n{screen}"
            );
        }
    }
    if tab == 5 {
        for expected in [
            "ALL-TIME",
            "CURRENT RUN",
            "COMPLETED TRADES",
            "VENUE FILL LEGS",
            "xyz:SP500",
            "xyz:BRENTOIL",
        ] {
            assert!(
                screen.contains(expected),
                "screen 5 missing {expected}\n{screen}"
            );
        }
    }
}

fn render(app: &App) -> String {
    let mut terminal = Terminal::new(TestBackend::new(160, 50)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V62 checkpoint");
    let buffer = terminal.backend().buffer();
    (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}
