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
const PROFILE: &str = "multi_asset_growth_first_5000_nine_asset_bankroll_builder_candidate_v63";
const FINGERPRINT: &str = "b81d0d22ed041ad007dfe4b6c55c652889ecc133bc9939e08eac5613e6fc1681";
const SYMBOLS: [&str; 9] = [
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
    "xyz:GOLD",
];

#[test]
#[ignore = "requires the local active V63 ledger and checkpoint"]
fn active_v63_renders_current_data_on_all_nine_screens() {
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
        "V63 checkpoint unavailable: {:?}",
        backend.cohort_checkpoint.issue
    );

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.set_cohort_command_inbox(Some(root.join(COMMAND_INBOX)));
    app.apply_backend_telemetry(backend);
    for tab in 1..=9 {
        app.active_tab = tab - 1;
        let screen = render(&app);
        println!("\n===== V63 SCREEN {tab} =====\n{screen}");
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
            "xyz:GOLD",
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
        .expect("draw V63 checkpoint");
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
