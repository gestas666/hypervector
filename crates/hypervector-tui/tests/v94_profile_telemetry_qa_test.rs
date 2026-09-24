use std::path::PathBuf;

use hypervector_tui::{
    App,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

const LEDGER_VARIABLE: &str = "HYPERVECTOR_V94_LEDGER";
const PROFILE: &str = "multi_asset_growth_first_5000_review_actions_v94";
const FINGERPRINT: &str = "930117e9ac0f4bb91fc66631666f47eb68a5d66bd8928684d8792f63122b3fd1";
const SYMBOLS: [&str; 8] = [
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
    "xyz:TSLA",
];
const STRONG_SHORT: &str = "hourly_donchian_20_10_atr20_strong_short_v1";
const DONCHIAN_SYMBOLS: [&str; 4] = ["SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA"];
const WATCH_ONLY: [&str; 2] = [
    "hype_breakout_compression_alignment_bidirectional_v2",
    "hourly_band20_reentry_atr20_bidirectional_v1",
];
const BTC_SWEEP: &str = "liquidity_sweep_long_1h_stop60_target60_v2";

/// Project V94's backend-published identity without refusing inert watch-only scopes.
///
/// Point `HYPERVECTOR_V94_LEDGER` at a cohort `decisions.jsonl` whose
/// configuration identity was written by the backend's own telemetry for the V94
/// profile: before deployment a scratch ledger, after deployment the live one.
#[test]
#[ignore = "requires a V94 cohort ledger named by HYPERVECTOR_V94_LEDGER"]
fn v94_cockpit_accepts_the_published_profile_identity() {
    let ledger = PathBuf::from(
        std::env::var_os(LEDGER_VARIABLE)
            .unwrap_or_else(|| panic!("set {LEDGER_VARIABLE} to a V94 cohort ledger")),
    );
    let backend = BackendTelemetrySource::new(ledger).refresh();

    assert_ne!(
        backend.connection,
        BackendConnectionState::Error,
        "cockpit refused V94 telemetry: {}",
        backend.status_message,
    );
    assert_eq!(backend.profile_id.as_deref(), Some(PROFILE));
    assert_eq!(backend.profile_fingerprint.as_deref(), Some(FINGERPRINT));
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS.map(str::to_string));
    assert_eq!(backend.cohort.providers.len(), 5);

    let donchian = provider(&backend, STRONG_SHORT);
    assert_eq!(
        donchian.execution_symbols.as_deref(),
        Some(DONCHIAN_SYMBOLS.map(str::to_string).as_slice()),
    );
    for strategy_id in WATCH_ONLY {
        let watch_only = provider(&backend, strategy_id);
        assert_eq!(watch_only.execution_symbols.as_deref(), Some(&[][..]));
    }
    for candidate in &backend.cohort.providers {
        let execution = candidate
            .execution
            .as_ref()
            .expect("bound execution contract");
        assert_eq!(
            execution.adaptive_exit_policy,
            "regime_flip_floor_retention_v2"
        );
        let expected = if candidate.strategy_id == BTC_SWEEP {
            "entry_offset"
        } else {
            "floor"
        };
        assert_eq!(
            execution.breakeven_stop_target, expected,
            "{}",
            candidate.strategy_id
        );
    }

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    let mut pages = String::new();
    for tab in 0..9usize {
        app.active_tab = tab;
        pages.push_str(&render(&app, 176, 65));
        pages.push_str(&render(&app, 120, 36));
    }
    assert!(
        !pages.contains("BACKEND ERROR"),
        "cockpit refused the V94 telemetry",
    );
    for symbol in SYMBOLS {
        assert!(pages.contains(symbol), "cockpit missing {symbol}");
    }

    // The config screen shows the selected route's own raise target: the venue
    // floor on the Donchian routes, and V93's default on BTC's 60/60 bracket.
    app.active_tab = 8;
    for (strategy_id, symbol, venue_floor) in
        [(STRONG_SHORT, "xyz:SNDK", true), (BTC_SWEEP, "BTC", false)]
    {
        app.selected_cohort_provider_index = provider_index(&app, strategy_id);
        app.selected_cohort_symbol_index = SYMBOLS
            .iter()
            .position(|candidate| *candidate == symbol)
            .expect("configured symbol");
        let config = render(&app, 176, 65);
        assert!(
            config.contains("PROFIT FLOOR v2"),
            "{strategy_id}: v2 contract missing\n{config}"
        );
        // The contract line wraps at this width, so match the label on its own.
        assert_eq!(
            config.contains("VENUE STOP TO FLOOR"),
            venue_floor,
            "{strategy_id}: venue floor label\n{config}"
        );
        pages.push_str(&config);
    }
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("{pages}");
    }
}

fn provider_index(app: &App, strategy_id: &str) -> usize {
    app.backend
        .cohort
        .providers
        .iter()
        .position(|provider| provider.strategy_id == strategy_id)
        .unwrap_or_else(|| panic!("V94 provider {strategy_id} is projected"))
}

fn provider<'a>(
    backend: &'a hypervector_tui::backend_telemetry::BackendTelemetrySnapshot,
    strategy_id: &str,
) -> &'a hypervector_tui::backend_cohort::CohortProvider {
    backend
        .cohort
        .providers
        .iter()
        .find(|provider| provider.strategy_id == strategy_id)
        .unwrap_or_else(|| panic!("V94 provider {strategy_id} is projected"))
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V94 cockpit");
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
