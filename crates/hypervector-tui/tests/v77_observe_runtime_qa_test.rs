use std::path::PathBuf;

use hypervector_tui::{
    App,
    backend_hip3_roster::Hip3RosterSource,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

const OBSERVE_LEDGER: &str =
    "data/runtime/bidirectional_cohort/observe/v77_qa_20260901/decisions.jsonl";
const HIP3_ROSTER_STATUS: &str = "data/runtime/research/hip3_roster_latest.json";
const PROFILE: &str = "multi_asset_growth_first_5000_seven_asset_btc_component_exit_repair_v77";
const FINGERPRINT: &str = "784ae7ecd5a45722e4a47b8196efe0a35abe2148153e69764d0e30eb899d4be0";
const SYMBOLS: [&str; 7] = ["BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK"];
const EXCLUDED: [&str; 3] = ["GOLD", "SP500", "BRENTOIL"];

#[test]
#[ignore = "requires a fresh one-poll V77 observe-only QA ledger"]
fn v77_observe_runtime_has_complete_seven_asset_tui_data() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::new(root.join(OBSERVE_LEDGER));
    let mut backend = source.refresh();
    backend.hip3_roster = Hip3RosterSource::new(Some(root.join(HIP3_ROSTER_STATUS))).refresh();

    assert_runtime_identity(&backend);
    assert_market_coverage(&backend);
    assert_v2_exit_contract(&backend);
    assert_no_excluded_identity(&backend);

    let robust_index = backend
        .cohort
        .providers
        .iter()
        .position(|provider| provider.strategy_id == "hulk_expansion_short_robust_v3")
        .expect("V77 robust-v3 provider");
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.selected_cohort_provider_index = robust_index;
    app.apply_backend_telemetry(backend);
    assert_all_screens(&mut app);
}

fn assert_runtime_identity(backend: &hypervector_tui::backend_telemetry::BackendTelemetrySnapshot) {
    assert!(
        matches!(
            backend.connection,
            BackendConnectionState::Connected | BackendConnectionState::Stale
        ),
        "{:?}: {}",
        backend.connection,
        backend.status_message
    );
    assert_eq!(backend.profile_id.as_deref(), Some(PROFILE));
    assert_eq!(backend.profile_fingerprint.as_deref(), Some(FINGERPRINT));
    assert_eq!(backend.live_armed, Some(false));
    assert_eq!(backend.execution_authority.as_deref(), Some("none"));
}

fn assert_market_coverage(backend: &hypervector_tui::backend_telemetry::BackendTelemetrySnapshot) {
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS.map(str::to_string));
    assert_eq!(backend.cohort.maximum_concurrent_positions, 3);
    assert_eq!(backend.cohort.candle_history.len(), SYMBOLS.len());
    assert_eq!(backend.cohort.books.len(), SYMBOLS.len());
    assert_eq!(backend.cohort.evaluations.len(), 9);
    assert!(backend.cohort.actions.is_empty());
    assert!(backend.cohort.withheld.is_empty());
    let coverage = backend
        .cohort
        .setup_coverage
        .as_ref()
        .expect("V77 setup coverage");
    assert_eq!(coverage.expected_provider_symbols, 9);
    assert_eq!(coverage.observed_provider_symbols, 9);
    assert!(coverage.complete);
}

fn assert_v2_exit_contract(backend: &hypervector_tui::backend_telemetry::BackendTelemetrySnapshot) {
    let robust = backend
        .cohort
        .providers
        .iter()
        .find(|provider| provider.strategy_id == "hulk_expansion_short_robust_v3")
        .expect("V77 robust-v3 provider");
    let execution = robust.execution.as_ref().expect("V77 robust-v3 execution");
    assert_eq!(
        execution.profit_lock_policy,
        "btc_hulk_delayed_component_exit_v2"
    );
}

fn assert_no_excluded_identity(
    backend: &hypervector_tui::backend_telemetry::BackendTelemetrySnapshot,
) {
    for provider in &backend.cohort.providers {
        assert!(
            EXCLUDED
                .iter()
                .all(|value| !provider.strategy_id.contains(value)),
            "excluded asset leaked into provider identity: {}",
            provider.strategy_id
        );
    }
}

fn assert_all_screens(app: &mut App) {
    for (width, height) in [(120, 36), (160, 50), (190, 52)] {
        for tab in 0..9 {
            app.active_tab = tab;
            for (symbol_index, symbol) in SYMBOLS.iter().enumerate() {
                app.selected_cohort_symbol_index = symbol_index;
                let screen = render(app, width, height);
                assert_valid_screen(tab + 1, width, height, &screen);
                if [0, 2, 3, 7, 8].contains(&tab) {
                    assert!(screen.contains(symbol), "missing {symbol}\n{screen}");
                }
            }
        }
        app.active_tab = 0;
        let dashboard = render(app, width, height);
        assert!(dashboard.contains("All 7 configured assets visible"));
        app.active_tab = 8;
        let config = render(app, width, height);
        if width == 190 {
            assert!(
                config.contains("FLOOR / REVERSAL CONTAINMENT"),
                "V2 exit policy missing at {width}x{height}\n{config}"
            );
        }
    }
}

fn assert_valid_screen(tab: usize, width: u16, height: u16, screen: &str) {
    for invalid in [
        "BACKEND DISCONNECTED",
        "IDENTITY MISMATCH",
        "PATH IDENTITY INVALID",
    ] {
        assert!(
            !screen.contains(invalid),
            "{width}x{height} screen {tab}: {invalid}\n{screen}"
        );
    }
    for excluded in EXCLUDED {
        assert!(
            !screen.contains(excluded),
            "{width}x{height} screen {tab} leaked {excluded}\n{screen}"
        );
    }
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V77 observe runtime");
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
