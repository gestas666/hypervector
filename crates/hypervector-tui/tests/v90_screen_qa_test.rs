use std::path::PathBuf;

use hypervector_tui::{App, backend_telemetry::BackendTelemetrySource};
use ratatui::{Terminal, backend::TestBackend};

const LIVE_LEDGER: &str = "data/live/bidirectional_cohort/decisions.jsonl";
const RUNTIME_CHECKPOINT: &str = "data/runtime/bidirectional_cohort/latest_checkpoint.json";
const PROFILE: &str = "multi_asset_growth_first_5000_bankroll_builder_candidate_v90";
const FINGERPRINT: &str = "c8938787268cfa94fd6c92026c191985a11c0225325452f415787b23fe6cb841";
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
const EXECUTABLE_DONCHIAN: &str = "hourly_donchian_20_10_atr20_bidirectional_v1";
const DONCHIAN_SYMBOLS: [&str; 4] = ["SOL", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA"];
const OBSERVE_ONLY: [&str; 3] = [
    "eth_range_onset_long_dual_mtf_v2",
    "hype_breakout_compression_alignment_bidirectional_v2",
    "hourly_band20_reentry_atr20_bidirectional_v1",
];
const ROUTES: [&str; 5] = [
    "BTC SWEEP 60/60",
    "ETH RANGE LONG",
    "HOURLY CHANNEL20",
    "HYPE ALIGN",
    "HOURLY RECOVERY",
];

/// The V90 bankroll builder must project every asset, route, and authority label.
///
/// V90 demoted ETH, HYPE and xyz:SPCX to observe-only while leaving their
/// `execution_side_overrides` in place. Those overrides are inert in the backend,
/// which derives executable directions from `execution_symbols` alone. A
/// projection that refuses them blanks the entire cockpit for a healthy live run,
/// so this test pins the accepted shape against the real armed profile.
#[test]
#[ignore = "requires the local active V90 live ledger and runtime checkpoint"]
fn v90_cockpit_projects_every_asset_route_and_execution_authority() {
    let root = repository_root();
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(LIVE_LEDGER),
        Some(root.join(RUNTIME_CHECKPOINT)),
    );
    let backend = source.refresh();

    assert_eq!(backend.profile_id.as_deref(), Some(PROFILE));
    assert_eq!(backend.profile_fingerprint.as_deref(), Some(FINGERPRINT));
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS.map(str::to_string));
    assert_eq!(backend.cohort.providers.len(), 5);
    assert_eq!(backend.cohort.evaluations.len(), 8);

    let coverage = backend
        .cohort
        .setup_coverage
        .as_ref()
        .expect("V90 setup coverage");
    assert_eq!(coverage.expected_provider_symbols, 8);
    assert_eq!(coverage.observed_provider_symbols, 8);
    assert!(coverage.complete);

    let donchian = provider(&backend, EXECUTABLE_DONCHIAN);
    assert_eq!(
        donchian.execution_symbols.as_deref(),
        Some(DONCHIAN_SYMBOLS.map(str::to_string).as_slice()),
        "all four hourly channel routes stay executable",
    );
    for strategy_id in OBSERVE_ONLY {
        assert_eq!(
            provider(&backend, strategy_id).execution_symbols.as_deref(),
            Some([].as_slice()),
            "{strategy_id} stays observe-only",
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
    app.active_tab = 1;
    let mut setup_pages = String::new();
    for index in 0..app.backend.cohort.evaluations.len() {
        app.selected_cohort_setup_index = index;
        setup_pages.push_str(&render(&app, 176, 65));
        // The 120x36 acceptance floor must still carry all eight V90 routes.
        setup_pages.push_str(&render(&app, 120, 36));
    }
    pages.push_str(&setup_pages);

    for symbol in SYMBOLS {
        assert!(pages.contains(symbol), "cockpit missing {symbol}");
    }
    for route in ROUTES {
        assert!(setup_pages.contains(route), "screen 2 missing {route}");
    }
    for label in [
        "SETUPS 8/8 // COMPLETE",
        "SLOTS 0 / 8",
        "ASSETS 8",
        "BTC SWEEP 60/60 [LIVE]",
        "HOURLY CHANNEL20 [LIVE]",
        "ETH RANGE LONG [OBS]",
        "HYPE ALIGN [OBS]",
        "HOURLY RECOVERY [OBS]",
    ] {
        assert!(setup_pages.contains(label), "screen 2 missing {label}");
    }
    assert!(
        !pages.contains("BACKEND ERROR"),
        "cockpit refused the armed V90 telemetry",
    );
    assert!(
        pages.contains("LOCK OFF") && !pages.contains("LOCK ARMED"),
        "V90 option B runs every route without a profit lock",
    );
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
        .unwrap_or_else(|| panic!("V90 provider {strategy_id} is projected"))
}

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V90 cockpit");
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
