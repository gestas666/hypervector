use std::path::PathBuf;

use hypervector_tui::{App, backend_telemetry::BackendTelemetrySource};
use ratatui::{Terminal, backend::TestBackend};

const LEDGER: &str = "data/observe/v86_screen_qa_20260904/decisions.jsonl";
const CHECKPOINT: &str = "data/runtime/bidirectional_cohort/v86_screen_qa_observer_checkpoint.json";
const PROFILE: &str = "multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86";
const SYMBOLS: [&str; 7] = ["BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK"];
const ROUTES: [&str; 9] = [
    "BTC HULK SHORT",
    "HULK EXPANSION",
    "BTC SWEEP 60/60",
    "ETH RANGE LONG",
    "SOL RANGE SHORT",
    "HYPE ALIGN",
    "ZEC DONCHIAN L",
    "SPCX CASH LONG",
    "SNDK BK15 SHORT",
];
const OBSERVE_ONLY: [&str; 3] = [
    "hulk_expansion_short_robust_v3",
    "hulk_expansion_short_tuned_v2",
    "zec_donchian_20_10_atr20_long_v1",
];

#[test]
fn v86_screen_2_retains_all_assets_routes_metrics_and_retirement_labels() {
    let root = repository_root();
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(LEDGER),
        Some(root.join(CHECKPOINT)),
    );
    let backend = source.refresh();

    assert_eq!(backend.profile_id.as_deref(), Some(PROFILE));
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS.map(str::to_string));
    assert_eq!(backend.cohort.providers.len(), 9);
    assert_eq!(backend.cohort.evaluations.len(), 9);
    let coverage = backend
        .cohort
        .setup_coverage
        .as_ref()
        .expect("V86 coverage");
    assert_eq!(coverage.expected_provider_symbols, 9);
    assert_eq!(coverage.observed_provider_symbols, 9);
    assert!(coverage.complete);
    for strategy_id in OBSERVE_ONLY {
        let provider = backend
            .cohort
            .providers
            .iter()
            .find(|provider| provider.strategy_id == strategy_id)
            .expect("retired route remains monitored");
        assert_eq!(provider.execution_symbols.as_deref(), Some([].as_slice()));
    }

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app.active_tab = 1;
    let mut wide_pages = String::new();
    let mut compact_pages = String::new();
    let mut detail_pages = String::new();
    for index in 0..app.backend.cohort.evaluations.len() {
        app.selected_cohort_setup_index = index;
        wide_pages.push_str(&render(&app, 176, 65));
        compact_pages.push_str(&render(&app, 120, 36));
        app.show_cohort_setup_modal = true;
        detail_pages.push_str(&render(&app, 120, 36));
        app.show_cohort_setup_modal = false;
    }
    let pages = format!("{wide_pages}{compact_pages}");

    for symbol in SYMBOLS {
        assert!(pages.contains(symbol), "screen 2 missing {symbol}");
    }
    for route in ROUTES {
        assert!(pages.contains(route), "screen 2 missing {route}");
    }
    for label in [
        "SETUPS 9/9 // COMPLETE",
        "BTC HULK SHORT [OBS]",
        "HULK EXPANSION [OBS]",
        "ZEC DONCHIAN L [OBS]",
        "ROUTE OBSERVE ONLY",
        "ARRIVAL ET",
        "DECISION ET",
        "SIGNAL DATE ET",
        "LIVE INDICATORS",
        "NEXT GAPS",
    ] {
        assert!(pages.contains(label), "screen 2 missing {label}");
    }
    for label in [
        "ENTRY TAKER IOC",
        "SL 20-75BPS",
        "TP 3.00R",
        "SL 60BPS",
        "TP 60BPS",
        "SL 20-250BPS",
        "TP 120BPS",
        "HOLD 6H15M",
        "HOLD 8H→24H",
    ] {
        assert!(pages.contains(label), "screen 2 missing route plan {label}");
    }
    for label in [
        "CONFIGURED RISK",
        "MAX SIGNAL AGE 60S",
        "PLAN UNAVAILABLE",
        "CONFIGURED RISK UNAVAILABLE",
    ] {
        assert!(
            detail_pages.contains(label) != label.ends_with("UNAVAILABLE"),
            "screen 2 detail availability differs for {label}",
        );
    }
}

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V86 checkpoint");
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
