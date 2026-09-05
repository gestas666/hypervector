use std::path::PathBuf;

use hypervector_tui::{
    App,
    backend_hip3_roster::Hip3RosterSource,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

const ACTIVE_LEDGER: &str = "data/live/bidirectional_cohort/decisions.jsonl";
const ACTIVE_CHECKPOINT: &str = "data/runtime/bidirectional_cohort/latest_checkpoint.json";
const HIP3_ROSTER_STATUS: &str = "data/runtime/research/hip3_roster_latest.json";
const COMMAND_INBOX: &str = "data/live/bidirectional_cohort/operator_commands";
const PROFILE: &str = "multi_asset_growth_first_5000_three_asset_btc_ioc_hardened_candidate_v68";
const FINGERPRINT: &str = "9c8df6faa8005290032802d58f7e53ec5cdc5b9605218bc426ee6d3a3b3b60fd";
const SYMBOLS: [&str; 3] = ["BTC", "HYPE", "xyz:SNDK"];
const RETIRED_SYMBOLS: [&str; 5] = ["ETH", "SOL", "xyz:SP500", "xyz:SPCX", "xyz:BRENTOIL"];

#[test]
#[ignore = "requires the local active V68 live ledger and checkpoint"]
fn active_v68_renders_current_data_on_all_nine_screens() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(ACTIVE_CHECKPOINT)),
    );
    let mut backend = source.refresh();
    backend.hip3_roster = Hip3RosterSource::new(Some(root.join(HIP3_ROSTER_STATUS))).refresh();

    assert!(matches!(
        backend.connection,
        BackendConnectionState::Connected | BackendConnectionState::Stale
    ));
    assert_eq!(backend.profile_id.as_deref(), Some(PROFILE));
    assert_eq!(backend.profile_fingerprint.as_deref(), Some(FINGERPRINT));
    assert_eq!(backend.live_armed, Some(true));
    assert_eq!(
        backend.execution_authority.as_deref(),
        Some("hyperliquid_mainnet")
    );
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS.map(str::to_string));
    let coverage = backend
        .cohort
        .setup_coverage
        .as_ref()
        .expect("V68 setup coverage");
    assert_eq!(coverage.expected_provider_symbols, 5);
    assert_eq!(coverage.observed_provider_symbols, 5);
    assert!(coverage.complete);
    assert_eq!(
        backend
            .cohort
            .asset_configs
            .iter()
            .map(|asset| asset.symbol.as_str())
            .collect::<Vec<_>>(),
        SYMBOLS
    );
    assert!(backend.cohort.evaluations.iter().all(|evaluation| {
        SYMBOLS.contains(&evaluation.symbol.as_str())
            && !RETIRED_SYMBOLS.contains(&evaluation.symbol.as_str())
    }));
    assert!(
        backend.cohort_checkpoint.available,
        "V68 checkpoint unavailable: {:?}",
        backend.cohort_checkpoint.issue
    );
    let generation = backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
        .expect("V68 current generation");
    assert!(generation.matches_runtime);
    let caps = generation
        .current_asset_market_slippage_caps
        .as_ref()
        .expect("V68 IOC cap map");
    assert_eq!(caps.get("BTC"), Some(&0.002));
    assert_eq!(caps.get("HYPE"), Some(&0.01));
    assert_eq!(caps.get("xyz:SNDK"), Some(&0.01));

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.set_cohort_command_inbox(Some(root.join(COMMAND_INBOX)));
    app.apply_backend_telemetry(backend);
    assert_all_screens(&mut app);
    assert_btc_current_ioc_cap(&mut app);
}

fn assert_all_screens(app: &mut App) {
    for (width, height) in [(120, 36), (160, 50), (190, 52)] {
        for tab in 1..=9 {
            app.active_tab = tab - 1;
            let screen = render(app, width, height);
            assert_runtime_screen(tab, width, height, &screen);
            if tab == 2 {
                assert_setup_rows_reachable(app, width, height, &screen);
            }
        }
    }
}

fn assert_setup_rows_reachable(app: &mut App, width: u16, height: u16, initial: &str) {
    let mut screens = initial.to_string();
    for index in 0..app.backend.cohort.evaluations.len() {
        app.selected_cohort_setup_index = index;
        screens.push_str(&render(app, width, height));
    }
    for symbol in SYMBOLS {
        assert!(
            screens.contains(symbol),
            "{width}x{height} setup pages missing {symbol}\n{screens}"
        );
    }
}

fn assert_btc_current_ioc_cap(app: &mut App) {
    app.active_tab = 8;
    app.selected_cohort_symbol_index = app
        .backend
        .cohort
        .asset_configs
        .iter()
        .position(|asset| asset.symbol == "BTC")
        .expect("BTC asset row");
    let mut config_pages = String::new();
    for _ in 0..8 {
        config_pages.push_str(&render(app, 160, 50));
        app.page_cohort_config_context(1);
    }
    assert!(
        config_pages.contains(
            "NEXT-RUN IOC CAPS BTC ENTRY 20.0bps // CLOSE 20.0bps // CURRENT // EFFECTIVE ENTRY 20.0bps / CLOSE 20.0bps"
        ),
        "current BTC IOC cap missing\n{config_pages}"
    );
}

fn assert_runtime_screen(tab: usize, width: u16, height: u16, screen: &str) {
    for invalid in [
        "BACKEND DISCONNECTED",
        "ANALYSIS UNAVAILABLE",
        "IDENTITY MISMATCH",
        "PATH IDENTITY INVALID",
        "RUNNING STALE",
    ] {
        assert!(
            !screen.contains(invalid),
            "{width}x{height} screen {tab}: {invalid}\n{screen}"
        );
    }
    if tab == 1 {
        for symbol in SYMBOLS {
            assert!(
                screen.contains(symbol),
                "{width}x{height} screen {tab} missing {symbol}\n{screen}"
            );
        }
        assert!(
            screen.contains("All 3 configured assets visible"),
            "{width}x{height} screen {tab} omitted roster count\n{screen}"
        );
    }
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V68 checkpoint");
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
