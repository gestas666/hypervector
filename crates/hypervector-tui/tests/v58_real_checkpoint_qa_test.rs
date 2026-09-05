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
const PROFILE: &str = "multi_asset_growth_first_5000_eight_asset_incremental_v58";
const FINGERPRINT: &str = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b";
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

struct RuntimeExpectations {
    all_closed: usize,
    current_closed: usize,
    open_symbols: Vec<String>,
}

#[test]
#[ignore = "requires the local active V58 ledger and checkpoint"]
fn active_v58_renders_current_data_on_all_nine_screens() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(ACTIVE_CHECKPOINT)),
    );
    let mut backend = source.refresh();
    backend.hype_l2_observer = HypeL2ObserverSource::new(Some(root.join(HYPE_L2_STATUS))).refresh();
    backend.hip3_roster = Hip3RosterSource::new(Some(root.join(HIP3_ROSTER_STATUS))).refresh();
    assert_eq!(backend.connection, BackendConnectionState::Connected);
    assert_eq!(backend.profile_id.as_deref(), Some(PROFILE));
    assert_eq!(backend.profile_fingerprint.as_deref(), Some(FINGERPRINT));
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS.map(str::to_string));
    assert!(
        backend.cohort_checkpoint.available,
        "V58 checkpoint unavailable: {:?}",
        backend.cohort_checkpoint.issue
    );
    assert_current_generation(&backend);
    let expectations = runtime_expectations(&backend);

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.set_cohort_command_inbox(Some(root.join(COMMAND_INBOX)));
    app.apply_backend_telemetry(backend);
    let requested_tab = std::env::var("HYPERVECTOR_QA_TAB")
        .ok()
        .and_then(|value| value.parse::<usize>().ok());
    for tab in 1..=9 {
        if requested_tab.is_some_and(|requested| requested != tab) {
            continue;
        }
        app.active_tab = tab - 1;
        let screen = render(&app);
        if requested_tab.is_some() || std::env::var_os("HYPERVECTOR_QA_DUMP").is_some() {
            println!("\n===== V58 SCREEN {tab} =====\n{screen}");
        }
        assert_screen_contract(tab, &screen, &expectations);
    }
}

fn assert_current_generation(
    backend: &hypervector_tui::backend_telemetry::BackendTelemetrySnapshot,
) {
    let generation = backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
        .expect("V58 configuration generation");
    assert!(generation.matches_runtime);
    assert_eq!(generation.runtime_profile_fingerprint, FINGERPRINT);
    assert_eq!(generation.current_profile_fingerprint, FINGERPRINT);
    assert_eq!(
        generation
            .current_provider_execution_directions
            .as_ref()
            .expect("V58 execution directions")
            .len(),
        10
    );
    assert!(generation.blocking_assets.is_empty());
}

fn runtime_expectations(
    backend: &hypervector_tui::backend_telemetry::BackendTelemetrySnapshot,
) -> RuntimeExpectations {
    let performance = backend
        .cohort_checkpoint
        .trade_performance
        .as_ref()
        .expect("V58 trade performance");
    let current_closed = performance
        .current_run
        .as_ref()
        .expect("current run")
        .total
        .closed_trades;
    let all_closed = backend
        .cohort_checkpoint
        .all_time_performance()
        .expect("all-time performance")
        .total
        .closed_trades;
    let open = &backend.cohort_checkpoint.open_trade_reflections;
    for trade in open {
        assert!(
            trade.protective_stop_oid.is_some(),
            "{} stop oid",
            trade.symbol
        );
        assert!(
            trade.protective_stop_price.is_some(),
            "{} stop price",
            trade.symbol
        );
    }
    RuntimeExpectations {
        all_closed,
        current_closed,
        open_symbols: open.iter().map(|trade| trade.symbol.clone()).collect(),
    }
}

fn assert_screen_contract(tab: usize, screen: &str, runtime: &RuntimeExpectations) {
    for invalid in [
        "BACKEND DISCONNECTED",
        "IDENTITY MISMATCH",
        "PATH IDENTITY INVALID",
    ] {
        assert!(
            !screen.contains(invalid),
            "screen {tab}: {invalid}\n{screen}"
        );
    }
    for expected in static_screen_contract(tab) {
        assert!(
            screen.contains(expected),
            "screen {tab} missing {expected}\n{screen}"
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
    if matches!(tab, 1 | 5) {
        for symbol in &runtime.open_symbols {
            assert!(
                screen.contains(symbol),
                "screen {tab} missing open {symbol}\n{screen}"
            );
        }
    }
    if tab == 4 {
        assert_depth_roster_state(screen);
    }
    if tab == 2 {
        assert_withheld_state(screen);
    }
    assert_dynamic_performance(tab, screen, runtime);
}

fn assert_withheld_state(screen: &str) {
    let populated = screen.contains("WITHHELD REASON");
    let empty = screen.contains("0 withheld intent records in retained window");
    assert!(
        populated || empty,
        "screen 2 neither populated nor explicitly empty\n{screen}"
    );
}

fn assert_depth_roster_state(screen: &str) {
    let populated = screen.contains("SYMBOL        MID");
    let unavailable = screen.contains("HIP-3 RESEARCH // UNAVAILABLE // NO LOCAL FALLBACK");
    assert!(
        populated || unavailable,
        "screen 4 neither populated nor explicitly unavailable\n{screen}"
    );
}

fn assert_dynamic_performance(tab: usize, screen: &str, runtime: &RuntimeExpectations) {
    if tab != 1 {
        return;
    }
    for expected in [
        format!("THIS RUN {} CLOSED", runtime.current_closed),
        format!("ALL-TIME {} CLOSED", runtime.all_closed),
        format!("OPEN {} / 10", runtime.open_symbols.len()),
    ] {
        assert!(
            screen.contains(&expected),
            "screen 1 missing {expected}\n{screen}"
        );
    }
}

fn static_screen_contract(tab: usize) -> &'static [&'static str] {
    match tab {
        1..=4 => primary_screen_contract(tab),
        5..=9 => secondary_screen_contract(tab),
        _ => unreachable!(),
    }
}

fn primary_screen_contract(tab: usize) -> &'static [&'static str] {
    match tab {
        1 => &[
            "PORTFOLIO PERFORMANCE // LIVE LEDGER",
            "ASSETS 1-4 / 8",
            "ASSETS 5-8 / 8",
            "All 8 configured assets visible",
        ],
        2 => &[
            "SETUPS 10/10 // COMPLETE",
            "ASSETS 8",
            "PROVIDER [AUTH]",
            "WITHHELD INTENTS // CURRENT RUN // NOTHING HIDDEN",
        ],
        3 => &[
            "BACKEND 1M OVERVIEW",
            "DETAIL USES PROVIDER TF + INDICATORS",
        ],
        4 => &["EXACT LEVELS 20/20", "hyperliquid_mainnet_l2_rest"],
        _ => unreachable!(),
    }
}

fn secondary_screen_contract(tab: usize) -> &'static [&'static str] {
    match tab {
        5 => &[
            "ALL-TIME",
            "CURRENT RUN",
            "VENUE FILL LEGS // NO ESTIMATES",
            "SCOPE   EXIT DATE ET",
        ],
        6 => &[
            "MODE LIVE_EXECUTION",
            "EXECUTION PARITY 10/10 ALIGNED",
            "COVERAGE COMPLETE",
            "ROUTE-SIDE FRONTIER",
        ],
        7 => &[
            "LIVE BACKEND ARMED",
            "REQUEST CHANNEL ENABLED",
            "RUST HAS NO SDK, SIGNER, OR VENUE CLIENT",
            "AUTOMATIC ENTRY + EXIT ROUTING ACTIVE",
        ],
        8 => &[
            "REGIME COMMAND DECK",
            "RANGE DETECTOR",
            "CANONICAL LABEL TAPE",
            "PROV-ONLY REG N/A",
        ],
        9 => &[
            "multi_asset_growth_first_5000_eight_asset_incremental_v58.toml",
            "DISK MATCHES RUNTIME",
            "NEXT ASSETS 8 // ROUTES EFFECTIVE 10 // NEXT 10 // SIDE SCOPES 14",
            "LIVE ARMING IS CLI-ONLY",
        ],
        _ => unreachable!(),
    }
}

fn render(app: &App) -> String {
    let mut terminal = Terminal::new(TestBackend::new(160, 50)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V58 checkpoint");
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
