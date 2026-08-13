use std::path::PathBuf;

use hypervector_tui::{
    App,
    backend_growth_preflight::GrowthPreflightSource,
    backend_hip3_roster::Hip3RosterSource,
    backend_hype_l2_observer::HypeL2ObserverSource,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

const ACTIVE_LEDGER: &str = "data/live/bidirectional_cohort/decisions.jsonl";
const ACTIVE_CHECKPOINT: &str = "data/runtime/bidirectional_cohort/latest_checkpoint.json";
const GROWTH_PREFLIGHT: &str =
    "data/runtime/bidirectional_cohort/latest_current_500_v39_preflight.json";
const HYPE_L2_STATUS: &str = "data/runtime/research/hype_l2_ridge_observer_latest.json";
const HIP3_ROSTER_STATUS: &str = "data/runtime/research/hip3_roster_latest.json";
const ACTIVE_PROFILE: &str =
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39";
const ACTIVE_PROFILE_FINGERPRINT: &str =
    "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5";
const ACTIVE_SYMBOLS: [&str; 8] = [
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
    dashboard: Vec<String>,
    trades: Vec<String>,
}

#[test]
#[ignore = "requires the local active v39 ledger and checkpoint"]
fn active_v39_renders_all_nine_screens_at_160x50() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut backend_source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(ACTIVE_CHECKPOINT)),
    );
    let mut backend = backend_source.refresh();
    let mut growth_source = GrowthPreflightSource::new(Some(root.join(GROWTH_PREFLIGHT)));
    let mut hype_source = HypeL2ObserverSource::new(Some(root.join(HYPE_L2_STATUS)));
    let mut hip3_source = Hip3RosterSource::new(Some(root.join(HIP3_ROSTER_STATUS)));
    backend.growth_preflight = growth_source.refresh();
    backend.hype_l2_observer = hype_source.refresh();
    backend.hip3_roster = hip3_source.refresh();

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
    let all_closed = performance
        .all_time_live
        .as_ref()
        .expect("all-time")
        .total
        .closed_trades;
    let run_closed = performance
        .current_run
        .as_ref()
        .expect("current run")
        .total
        .closed_trades;
    assert!(all_closed >= 59, "retired history disappeared");
    assert!(run_closed >= 7, "current v39 history regressed");
    assert_eq!(
        backend.cohort_checkpoint.user_trade_reflections().len(),
        all_closed
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
    let expectations = runtime_expectations(all_closed, run_closed, open);
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
    assert_eq!(scopes.values().map(Vec::len).sum::<usize>(), 14);
    assert_eq!(
        scopes
            .values()
            .flatten()
            .collect::<std::collections::BTreeSet<_>>()
            .len(),
        8
    );

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.apply_backend_telemetry(backend);
    if std::env::var_os("HYPERVECTOR_QA_ALL").is_some() {
        for tab in 1..=9 {
            app.active_tab = tab - 1;
            assert_rendered_screen(tab, &render(&app, 160, 50), &expectations);
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
    assert_rendered_screen(tab, &screen, &expectations);
}

#[test]
#[ignore = "requires the local staged v51 accounting checkpoint"]
fn staged_v51_epoch_renders_zero_all_time_without_erasing_prior_rows() {
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
    assert_screen_contract(tab, &screen);
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
    let expected: &[&str] = match tab {
        1 => &[
            "PORTFOLIO PERFORMANCE // LIVE LEDGER",
            "LIVE POSITIONS",
            "xyz:BRENTOIL",
        ],
        2 => &["SETUPS 14/14 // COMPLETE", "ASSETS 8", "xyz:BRENTOIL"],
        3 => &["BACKEND 1M OVERVIEW", "BTC 1M CANDLES", "SOL 1M CANDLES"],
        4 => &["LIVE HYPERLIQUID L2", "EXACT LEVELS 20/20", "xyz:BRENTOIL"],
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
            "PROV-ONLY REG N/A",
            "Backend labels + causal evidence",
        ],
        9 => &[
            "PENDING RESTART PROFILE",
            "PENDING RESTART PROFILE  NONE // DISK MATCHES RUNTIME",
            "NEXT ASSETS 8 // ROUTES EFFECTIVE 14 // NEXT 14 // SIDE SCOPES 28",
            "LIVE ARMING IS CLI-ONLY",
        ],
        _ => unreachable!(),
    };
    for value in expected {
        assert!(
            screen.contains(value),
            "screen {tab} missing {value}\n{screen}"
        );
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
