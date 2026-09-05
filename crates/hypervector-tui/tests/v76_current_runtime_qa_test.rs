use std::path::PathBuf;

use hypervector_tui::{
    App,
    backend_hip3_roster::Hip3RosterSource,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

const ACTIVE_LEDGER: &str = "data/live/bidirectional_cohort/decisions.jsonl";
const ACTIVE_CHECKPOINT: &str =
    "data/runtime/bidirectional_cohort/latest_v76_strategy_checkpoint.json";
const HIP3_ROSTER_STATUS: &str = "data/runtime/research/hip3_roster_latest.json";
const COMMAND_INBOX: &str = "data/live/bidirectional_cohort/operator_commands";
const PROFILE: &str = "multi_asset_growth_first_5000_seven_asset_validated_roster_candidate_v76";
const FINGERPRINT: &str = "2a52693eff41d3020efa5d079fac502890ba6950dd8c2b06817da08f44e412f3";
const SYMBOLS: [&str; 7] = ["BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK"];
const EXCLUDED: [&str; 3] = ["GOLD", "SP500", "BRENTOIL"];

#[test]
#[ignore = "requires the local active V76 live ledger and checkpoint"]
fn active_v76_renders_current_data_on_all_nine_screens() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(ACTIVE_CHECKPOINT)),
    );
    let mut backend = source.refresh();
    backend.hip3_roster = Hip3RosterSource::new(Some(root.join(HIP3_ROSTER_STATUS))).refresh();
    assert_runtime_identity(&backend);
    assert_market_coverage(&backend);
    assert_current_checkpoint(&backend);
    let named_btc_lock_open = backend.cohort.assets.iter().any(|asset| {
        asset
            .execution_plan
            .as_ref()
            .is_some_and(|plan| plan.profit_lock_policy == "btc_hulk_delayed_component_floor_v1")
    });

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.set_cohort_command_inbox(Some(root.join(COMMAND_INBOX)));
    app.apply_backend_telemetry(backend);
    assert_all_screens(&mut app, named_btc_lock_open);
}

fn assert_runtime_identity(backend: &hypervector_tui::backend_telemetry::BackendTelemetrySnapshot) {
    assert_eq!(backend.connection, BackendConnectionState::Connected);
    assert_eq!(backend.profile_id.as_deref(), Some(PROFILE));
    assert_eq!(backend.profile_fingerprint.as_deref(), Some(FINGERPRINT));
    assert_eq!(backend.live_armed, Some(true));
    assert_eq!(
        backend.execution_authority.as_deref(),
        Some("hyperliquid_mainnet")
    );
}

fn assert_market_coverage(backend: &hypervector_tui::backend_telemetry::BackendTelemetrySnapshot) {
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS.map(str::to_string));
    assert_eq!(backend.cohort.maximum_concurrent_positions, 3);
    assert_eq!(backend.cohort.candle_history.len(), SYMBOLS.len());
    assert_eq!(backend.cohort.books.len(), SYMBOLS.len());
    let coverage = backend
        .cohort
        .setup_coverage
        .as_ref()
        .expect("V76 setup coverage");
    assert_eq!(coverage.expected_provider_symbols, 9);
    assert_eq!(coverage.observed_provider_symbols, 9);
    assert!(coverage.complete);
    assert!(backend.cohort.evaluations.len() >= coverage.observed_provider_symbols);
}

fn assert_current_checkpoint(
    backend: &hypervector_tui::backend_telemetry::BackendTelemetrySnapshot,
) {
    assert!(
        backend.cohort_checkpoint.available,
        "V76 checkpoint unavailable: {:?}",
        backend.cohort_checkpoint.issue
    );
    let generation = backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
        .expect("V76 current generation");
    assert!(generation.matches_runtime);
}

fn assert_all_screens(app: &mut App, named_btc_lock_open: bool) {
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
        if named_btc_lock_open {
            assert!(
                dashboard.contains("HK24H/I/DCF"),
                "named BTC lock missing at {width}x{height}\n{dashboard}"
            );
        }
    }
}

fn assert_valid_screen(tab: usize, width: u16, height: u16, screen: &str) {
    for invalid in [
        "BACKEND DISCONNECTED",
        "ANALYSIS UNAVAILABLE",
        "IDENTITY MISMATCH",
        "PATH IDENTITY INVALID",
        "RUNNING STALE",
    ] {
        assert!(
            !screen.contains(invalid),
            "{width}x{height} screen {tab}: {invalid}"
        );
    }
    for excluded in EXCLUDED {
        assert!(
            !screen.contains(excluded),
            "{width}x{height} screen {tab}: {excluded}"
        );
    }
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V76 checkpoint");
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
