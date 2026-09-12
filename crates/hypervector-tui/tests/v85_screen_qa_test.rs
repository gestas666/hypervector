use std::path::PathBuf;

use hypervector_tui::{App, backend_telemetry::BackendTelemetrySource};
use ratatui::{Terminal, backend::TestBackend};

const OBSERVER_LEDGER: &str = "data/observe/v85_screen_qa_complete_20260903/decisions.jsonl";
const OBSERVER_CHECKPOINT: &str =
    "data/runtime/bidirectional_cohort/v85_screen_qa_complete_observer_checkpoint.json";
const LIVE_LEDGER: &str = "data/live/bidirectional_cohort/decisions.jsonl";
const RUNTIME_CHECKPOINT: &str = "data/runtime/bidirectional_cohort/latest_checkpoint.json";
const PROFILE: &str = "multi_asset_growth_first_5000_seven_asset_btc_tuned_retired_v85";
const FINGERPRINT: &str = "18306afaaad1912b368f483c770c507a94a2403f9bd2741691776220b38633e8";
const TUNED: &str = "hulk_expansion_short_tuned_v2";
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

#[test]
#[ignore = "requires the local bounded V85 observer and staged accounting evidence"]
fn v85_screen_2_has_every_route_and_marks_the_retired_route_observe_only() {
    let root = repository_root();
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(OBSERVER_LEDGER),
        Some(root.join(OBSERVER_CHECKPOINT)),
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
        .expect("V85 coverage");
    assert_eq!(coverage.expected_provider_symbols, 9);
    assert_eq!(coverage.observed_provider_symbols, 9);
    assert!(coverage.complete);
    let tuned = backend
        .cohort
        .providers
        .iter()
        .find(|provider| provider.strategy_id == TUNED)
        .expect("retired tuned route remains monitored");
    assert_eq!(tuned.execution_symbols.as_deref(), Some([].as_slice()));

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
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("\n===== V85 SCREEN 2 =====\n{}", render(&app, 176, 65));
        println!(
            "\n===== V85 SCREEN 2 COMPACT =====\n{}",
            render(&app, 120, 36)
        );
    }

    for symbol in SYMBOLS {
        assert!(pages.contains(symbol), "screen 2 missing {symbol}");
    }
    for route in ROUTES {
        assert!(pages.contains(route), "screen 2 missing {route}");
    }
    for label in [
        "SETUPS 9/9 // COMPLETE",
        "HULK EXPANSION [OBS]",
        "ROUTE OBSERVE ONLY",
        "ARRIVAL ET",
        "DECISION ET",
        "SIGNAL DATE ET",
        "AGE",
        "1D9H7M",
        "RECORDED INDICATORS",
        "NEXT GAPS",
    ] {
        assert!(pages.contains(label), "screen 2 missing {label}");
    }
    assert!(
        pages.contains("CONFIGURED RISK // MARGIN"),
        "screen 2 selected route is missing configured risk"
    );
    for label in ["BTC HULK SHORT [CANARY]", "SNDK BK15 SHORT [CANARY]"] {
        assert!(wide_pages.contains(label), "wide screen 2 missing {label}");
        assert!(
            compact_pages.contains(label),
            "compact screen 2 missing {label}"
        );
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
        "MARGIN 5.0%",
        "NOTIONAL CAP $2500.00",
        "LEVERAGE 20.0X",
        "MAX SIGNAL AGE 60S",
    ] {
        assert!(
            detail_pages.contains(label),
            "screen 2 detail missing {label}"
        );
    }
    for unavailable in [
        "OBSERVER RUNTIME NOT RUNNING",
        "HIP-3 OBSERVER UNAVAILABLE",
        "PLAN UNAVAILABLE",
        "CONFIGURED RISK UNAVAILABLE",
        "RESEARCH STATE NOT REPORTED BY THIS RUN",
    ] {
        assert!(
            !pages.contains(unavailable) && !detail_pages.contains(unavailable),
            "screen 2 contains stale dependency state: {unavailable}"
        );
    }
}

#[test]
#[ignore = "requires the local active V85 ledger and accounting checkpoint"]
fn v85_screen_5_reconciles_current_lifecycles_and_retains_backend_history() {
    let root = repository_root();
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(LIVE_LEDGER),
        Some(root.join(RUNTIME_CHECKPOINT)),
    );
    let backend = source.refresh();
    let generation = backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
        .expect("V85 configuration generation");

    assert_eq!(generation.current_profile_fingerprint, FINGERPRINT);
    assert_eq!(
        generation
            .current_provider_execution_scopes
            .as_ref()
            .and_then(|scopes| scopes.get(TUNED)),
        Some(&Vec::new()),
    );

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app.active_tab = 4;
    let wide = render(&app, 176, 65);
    let compact = render(&app, 120, 36);
    let narrow_tall = render(&app, 120, 65);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("\n===== V85 SCREEN 5 =====\n{wide}");
        println!("\n===== V85 SCREEN 5 COMPACT =====\n{compact}");
    }

    for symbol in SYMBOLS {
        assert!(wide.contains(symbol), "wide screen 5 missing {symbol}");
        assert!(
            compact.contains(symbol),
            "compact screen 5 missing {symbol}"
        );
    }
    for label in [
        "9 MONITORED / 8 EXEC / 1 OBS",
        "DISPLAY EPOCH",
        "PRESERVED DATA",
        "COMPLETED TRADES",
        "VENUE FILL LEGS",
        "0/0/0",
        "$+0.00",
        "123",
        "50/73/0",
        "$-316.78",
        "$80.66",
        "+2.1723",
        "DISPLAY EPOCH 0/0",
        "No fills reported for this compatible execution profile",
    ] {
        assert!(
            wide.contains(label),
            "wide screen 5 missing {label}\n{wide}"
        );
        assert!(
            compact.contains(label),
            "compact screen 5 missing {label}\n{compact}"
        );
    }
    for route in ROUTES {
        assert!(
            wide.contains(route),
            "wide screen 5 missing zero-or-resolved route {route}\n{wide}"
        );
        assert!(
            compact.contains(route),
            "compact screen 5 missing zero-or-resolved route {route}\n{compact}"
        );
        assert!(
            narrow_tall.contains(route),
            "narrow-tall screen 5 missing zero-or-resolved route {route}\n{narrow_tall}"
        );
    }
    for label in [
        "BTC HULK SHORT [E/N0]",
        "HULK EXPANSION [O/N0]",
        "SPCX CASH LONG [E/N0]",
    ] {
        assert!(
            wide.contains(label),
            "wide screen 5 missing {label}\n{wide}"
        );
        assert!(
            compact.contains(label),
            "compact screen 5 missing {label}\n{compact}"
        );
        assert!(
            narrow_tall.contains(label),
            "narrow-tall screen 5 missing {label}\n{narrow_tall}"
        );
    }
    assert!(
        narrow_tall.contains("E=EXEC O=OBS N=EPOCH CLOSES"),
        "narrow-tall screen 5 did not select the complete dense view\n{narrow_tall}"
    );
    assert!(
        wide.contains("DISPLAY EPOCH                  0       0/0/0"),
        "wide screen 5 did not reset displayed trade history\n{wide}"
    );
    assert!(
        compact.contains("DISPLAY EPOCH 0T 0/0/0"),
        "compact screen 5 did not reset displayed trade history\n{compact}"
    );
}

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V85 checkpoint");
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
