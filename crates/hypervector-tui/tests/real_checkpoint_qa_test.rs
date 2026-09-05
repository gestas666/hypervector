use std::path::PathBuf;

use hypervector_tui::{
    App,
    backend_hip3_roster::Hip3RosterSource,
    backend_hype_l2_observer::HypeL2ObserverSource,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySnapshot, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

const ACTIVE_LEDGER: &str = "data/live/bidirectional_cohort/decisions.jsonl";
const ACTIVE_CHECKPOINT: &str = "data/runtime/bidirectional_cohort/latest_checkpoint.json";
const HYPE_L2_STATUS: &str = "data/runtime/research/hype_l2_ridge_observer_latest.json";
const HIP3_ROSTER_STATUS: &str = "data/runtime/research/hip3_roster_latest.json";
const ACTIVE_PROFILE: &str = "multi_asset_growth_first_5000_spcx_cash_open_v55";
const ACTIVE_PROFILE_FINGERPRINT: &str =
    "e918f81e55abb36ad207a1af69517dd4d8765b79eb972669195a6b180702d3c7";
const ACTIVE_SYMBOLS: [&str; 3] = ["BTC", "HYPE", "xyz:SPCX"];

struct RuntimeExpectations {
    dashboard: Vec<String>,
    trades: Vec<String>,
}

#[test]
#[ignore = "requires the local active v55 ledger and checkpoint"]
fn active_v55_renders_all_nine_screens_at_160x50() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let backend = load_v55_backend(&root);
    let expectations = assert_v55_backend(&backend);
    assert_v55_generation(&backend);
    render_requested_screens(backend, &expectations);
}

fn load_v55_backend(root: &std::path::Path) -> BackendTelemetrySnapshot {
    let mut backend_source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(ACTIVE_CHECKPOINT)),
    );
    let mut backend = backend_source.refresh();
    let mut hype_source = HypeL2ObserverSource::new(Some(root.join(HYPE_L2_STATUS)));
    let mut hip3_source = Hip3RosterSource::new(Some(root.join(HIP3_ROSTER_STATUS)));
    backend.hype_l2_observer = hype_source.refresh();
    backend.hip3_roster = hip3_source.refresh();
    backend
}

fn assert_v55_backend(backend: &BackendTelemetrySnapshot) -> RuntimeExpectations {
    assert_eq!(backend.connection, BackendConnectionState::Connected);
    assert_eq!(backend.profile_id.as_deref(), Some(ACTIVE_PROFILE));
    assert_eq!(
        backend.cohort.enabled_symbols,
        ACTIVE_SYMBOLS.map(str::to_string)
    );
    let performance = backend
        .cohort_checkpoint
        .trade_performance
        .as_ref()
        .expect("trade performance");
    let all_closed = backend
        .cohort_checkpoint
        .all_time_performance()
        .expect("epoch all-time")
        .total
        .closed_trades;
    let run_closed = performance
        .current_run
        .as_ref()
        .expect("current run")
        .total
        .closed_trades;
    assert_eq!(all_closed, 0, "v55 accounting epoch must start at zero");
    assert_eq!(run_closed, 0, "v55 has no completed lifecycle yet");
    assert!(
        backend.cohort_checkpoint.user_trade_reflections().len() >= 73,
        "prior reflection history must remain inspectable"
    );
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
    runtime_expectations(all_closed, run_closed, open)
}

fn assert_v55_generation(backend: &BackendTelemetrySnapshot) {
    let generation = backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
        .expect("staged generation");
    assert_eq!(
        generation.runtime_profile_fingerprint,
        ACTIVE_PROFILE_FINGERPRINT
    );
    assert!(generation.matches_runtime);
    assert!(generation.blocking_assets.is_empty());
    let scopes = generation
        .current_provider_execution_scopes
        .as_ref()
        .expect("staged route scopes");
    assert_eq!(scopes.values().map(Vec::len).sum::<usize>(), 4);
    assert_eq!(
        scopes
            .values()
            .flatten()
            .collect::<std::collections::BTreeSet<_>>()
            .len(),
        3
    );
}

fn render_requested_screens(backend: BackendTelemetrySnapshot, expectations: &RuntimeExpectations) {
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.apply_backend_telemetry(backend);
    if std::env::var_os("HYPERVECTOR_QA_ALL").is_some() {
        for tab in 1..=9 {
            app.active_tab = tab - 1;
            assert_rendered_screen(tab, &render(&app, 160, 50), expectations);
        }
        return;
    }
    let tab = std::env::var("HYPERVECTOR_QA_TAB")
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(1);
    assert!((1..=9).contains(&tab), "HYPERVECTOR_QA_TAB must be 1..=9");
    app.active_tab = tab - 1;
    let screen = render(&app, 160, 50);
    println!("\n===== SCREEN {tab} =====\n{screen}");
    assert_rendered_screen(tab, &screen, expectations);
}

#[test]
#[ignore = "requires the local active v55 accounting checkpoint"]
fn active_v55_epoch_renders_zero_all_time_without_erasing_prior_rows() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(ACTIVE_CHECKPOINT)),
    );
    let backend = source.refresh();
    let all_time = backend
        .cohort_checkpoint
        .all_time_performance()
        .expect("epoch performance");

    assert_eq!(all_time.total.closed_trades, 0);
    assert!(
        backend.cohort_checkpoint.user_trade_reflections().len() >= 73,
        "prior reflection history must remain inspectable"
    );
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.apply_backend_telemetry(backend);
    let screen = render(&app, 160, 50);
    assert!(screen.contains("ALL-TIME 0 CLOSED"), "{screen}");
}

#[test]
#[ignore = "requires the local active v55 ledger and checkpoint"]
fn active_v55_screen_two_diagnostic() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(ACTIVE_CHECKPOINT)),
    );
    let backend = source.refresh();
    assert_eq!(backend.connection, BackendConnectionState::Connected);
    assert!(backend.cohort.setup_coverage.is_some());
    let evaluation_count = backend.cohort.evaluations.len();
    let action_count = backend.cohort.actions.len();
    let withheld_count = backend.cohort.withheld.len();
    let configured_sides = |strategy_id: &str| {
        let provider = backend
            .cohort
            .providers
            .iter()
            .find(|provider| provider.strategy_id == strategy_id)
            .expect("configured provider");
        provider
            .execution_side_overrides
            .get("BTC")
            .unwrap_or(&provider.sides)
            .clone()
    };
    assert_eq!(
        configured_sides("hulk_expansion_short_robust_v3"),
        ["short"]
    );
    assert_eq!(
        configured_sides("liquidity_sweep_long_1h_stop60_target60_v2"),
        ["long"]
    );
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.apply_backend_telemetry(backend);
    app.active_tab = 1;
    let screen = render(&app, 160, 50);
    assert!(screen.contains("BTC HULK SHORT [LIVE]"), "{screen}");
    assert!(screen.contains("BTC SWEEP 60/60 [LIVE]"), "{screen}");
    assert!(screen.contains("HYPE ALIGN [LIVE]"), "{screen}");
    assert!(screen.contains("SPCX CASH OPEN [LIVE]"), "{screen}");
    println!(
        "\n===== V55 SCREEN 2 // EVAL {evaluation_count} ACTION {action_count} WITHHELD {withheld_count} =====\n{screen}"
    );
}

fn runtime_expectations(
    all_closed: usize,
    run_closed: usize,
    open: &[hypervector_tui::backend_cohort_open_trade_reflection::CohortOpenTradeReflection],
) -> RuntimeExpectations {
    let mut dashboard = vec![
        format!("THIS RUN {run_closed} CLOSED"),
        format!("ALL-TIME {all_closed} CLOSED"),
        format!("OPEN {} / 10", open.len()),
    ];
    let mut trades = vec![all_closed.to_string()];
    for trade in open {
        dashboard.push(trade.symbol.clone());
        trades.push(trade.symbol.clone());
    }
    RuntimeExpectations { dashboard, trades }
}

fn assert_rendered_screen(tab: usize, screen: &str, runtime: &RuntimeExpectations) {
    assert!(
        !screen.contains("BACKEND DISCONNECTED"),
        "screen {tab}\n{screen}"
    );
    assert!(
        !screen.contains("IDENTITY MISMATCH"),
        "screen {tab}\n{screen}"
    );
    assert!(
        !screen.contains("PATH IDENTITY INVALID"),
        "screen {tab}\n{screen}"
    );
    assert_screen_contract(tab, screen);
    let values = match tab {
        1 => &runtime.dashboard,
        5 => &runtime.trades,
        _ => return,
    };
    for value in values {
        assert!(
            screen.contains(value),
            "screen {tab} missing {value}\n{screen}"
        );
    }
}

fn assert_screen_contract(tab: usize, screen: &str) {
    for value in screen_contract(tab) {
        assert!(
            screen.contains(value),
            "screen {tab} missing {value}\n{screen}"
        );
    }
}

fn screen_contract(tab: usize) -> &'static [&'static str] {
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
            "LIVE POSITIONS",
            "ASSETS 1-3 / 3",
            "BTC",
            "HYPE",
            "xyz:SPCX",
        ],
        2 => &[
            "SETUPS 4/4 // COMPLETE",
            "ASSETS 3",
            "BTC SWEEP 60/60",
            "HYPE",
            "SPCX CASH OPEN",
        ],
        3 => &[
            "BACKEND 1M OVERVIEW",
            "BTC 1M CANDLES",
            "HYPE 1M CANDLES",
            "SPCX 1M CANDLES",
        ],
        4 => &[
            "SELECTED MARKET // MARKETS 1-3 / 3",
            "LIVE HYPERLIQUID L2",
            "EXACT LEVELS 20/20",
        ],
        _ => unreachable!(),
    }
}

fn secondary_screen_contract(tab: usize) -> &'static [&'static str] {
    match tab {
        5 => &["ALL-TIME", "CURRENT RUN"],
        6 => &[
            "MODE LIVE_EXECUTION",
            "EVALUATIONS",
            "EVIDENCE-CLASS JOURNAL",
        ],
        7 => &[
            "RUST HAS NO SDK, SIGNER, OR VENUE CLIENT",
            "DRAIN INACTIVE // READY",
        ],
        8 => &[
            "REGIME COMMAND DECK",
            "BTC",
            "HYPE",
            "SPCX",
            "Backend labels + causal evidence",
        ],
        9 => &[
            "PENDING RESTART PROFILE",
            "PENDING RESTART PROFILE  NONE // DISK MATCHES RUNTIME",
            "NEXT ASSETS 3 // ROUTES EFFECTIVE 4 // NEXT 4 // SIDE SCOPES 6",
            "LIVE ARMING IS CLI-ONLY",
        ],
        _ => unreachable!(),
    }
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw real checkpoint");
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
