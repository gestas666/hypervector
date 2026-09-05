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
const PROFILE: &str = "multi_asset_growth_first_5000_seven_asset_entry_ioc_hardened_v80";
const FINGERPRINT: &str = "89c84ecf8f927d1b22b3db7b28a9b6e62c89685d7049ef02f0cca90fc568d5ca";
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
#[ignore = "requires the local V80 live ledger and checkpoint"]
fn v80_exposes_complete_setup_and_trade_screens() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(ACTIVE_CHECKPOINT)),
    );
    let mut backend = source.refresh();
    backend.hip3_roster = Hip3RosterSource::new(Some(root.join(HIP3_ROSTER_STATUS))).refresh();

    assert!(
        matches!(
            backend.connection,
            BackendConnectionState::Connected | BackendConnectionState::Stale
        ),
        "V80 evidence must remain inspectable after a clean stop"
    );
    assert_eq!(backend.profile_id.as_deref(), Some(PROFILE));
    assert_eq!(backend.profile_fingerprint.as_deref(), Some(FINGERPRINT));
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS.map(str::to_string));
    assert!(backend.cohort_checkpoint.available);
    let coverage = backend
        .cohort
        .setup_coverage
        .as_ref()
        .expect("V80 coverage");
    assert_eq!(coverage.expected_provider_symbols, 9);
    assert_eq!(coverage.observed_provider_symbols, 9);
    assert!(coverage.complete);

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.set_cohort_command_inbox(Some(root.join(COMMAND_INBOX)));
    app.apply_backend_telemetry(backend);

    app.active_tab = 1;
    let setup = render(&app, 176, 65);
    let compact_setup = render(&app, 120, 36);
    let mut setup_pages = String::new();
    for index in 0..app.backend.cohort.evaluations.len() {
        app.selected_cohort_setup_index = index;
        setup_pages.push_str(&render(&app, 176, 65));
        setup_pages.push_str(&render(&app, 120, 36));
    }
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("\n===== V80 SCREEN 2 =====\n{setup}");
        println!("\n===== V80 SCREEN 2 COMPACT =====\n{compact_setup}");
    }
    for symbol in SYMBOLS {
        assert!(setup_pages.contains(symbol), "screen 2 missing {symbol}");
    }
    for route in ROUTES {
        assert!(setup_pages.contains(route), "screen 2 missing {route}");
    }
    for label in [
        "STOPPED SNAPSHOT",
        "V80 RUN STOPPED",
        "ARRIVAL ET",
        "DECISION ET",
        "LIVE INDICATORS",
        "NEXT GAPS",
        "FORCED EXIT OFF",
    ] {
        assert!(setup.contains(label), "screen 2 missing {label}\n{setup}");
    }

    app.active_tab = 4;
    let trades = render(&app, 176, 65);
    let compact_trades = render(&app, 120, 36);
    let mut fill_pages = String::new();
    for index in 0..app.backend.cohort.fills.len() {
        app.selected_cohort_fill_index = index;
        fill_pages.push_str(&render(&app, 176, 65));
        fill_pages.push_str(&render(&app, 120, 36));
    }
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("\n===== V80 SCREEN 5 =====\n{trades}");
        println!("\n===== V80 SCREEN 5 COMPACT =====\n{compact_trades}");
    }
    for label in [
        "STOPPED SNAPSHOT",
        "V80 RUN STOPPED",
        "CURRENT RUN",
        "DISPLAY EPOCH",
        "PRESERVED DATA",
        "COMPLETED TRADES",
        "VENUE FILL LEGS",
    ] {
        assert!(trades.contains(label), "screen 5 missing {label}\n{trades}");
        assert!(
            compact_trades.contains(label),
            "compact screen 5 missing {label}\n{compact_trades}"
        );
    }
    for symbol in SYMBOLS {
        assert!(trades.contains(symbol), "screen 5 missing {symbol}");
        assert!(
            compact_trades.contains(symbol),
            "compact screen 5 missing {symbol}"
        );
    }
    for fill_price in ["148.84000000", "147.06000000", "147.10000000"] {
        assert!(
            fill_pages.contains(fill_price),
            "screen 5 fill viewport missing {fill_price}"
        );
    }
    for value in ["0/0/0", "123", "50/73/0", "$-316.78", "$80.66", "+2.1723"] {
        assert!(trades.contains(value), "screen 5 missing {value}");
    }
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V80 checkpoint");
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
