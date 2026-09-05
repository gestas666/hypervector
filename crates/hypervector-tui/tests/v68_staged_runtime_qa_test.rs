use std::{fs, path::PathBuf};

use hypervector_tui::{
    App,
    backend_growth_preflight::parse_growth_preflight,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

const ACTIVE_LEDGER: &str = "data/live/bidirectional_cohort/decisions.jsonl";
const STAGED_CHECKPOINT: &str = "data/runtime/bidirectional_cohort/v68_staged_checkpoint.json";
const GROWTH_PREFLIGHT: &str = "data/logs/research/bidirectional_cohort/\
v68_btc_ioc_hardening_flat_5000_preflight_20260901T1320Z.json";
const ACTIVE_PROFILE: &str =
    "multi_asset_growth_first_5000_three_asset_evidence_scope_repaired_candidate_v67";
const ACTIVE_FINGERPRINT: &str = "42afff8bd0dc871db2f6ef6321a6aacd14ec39c033105b6708a3208b96cfc12e";
const STAGED_PROFILE: &str =
    "multi_asset_growth_first_5000_three_asset_btc_ioc_hardened_candidate_v68";
const STAGED_FINGERPRINT: &str = "9c8df6faa8005290032802d58f7e53ec5cdc5b9605218bc426ee6d3a3b3b60fd";

#[test]
#[ignore = "requires the local active V67 ledger and report-only V68 checkpoint"]
fn staged_v68_ioc_hardening_is_visible_on_all_nine_screens() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(STAGED_CHECKPOINT)),
    );
    let mut backend = source.refresh();
    backend.growth_preflight = parse_growth_preflight(
        &fs::read_to_string(root.join(GROWTH_PREFLIGHT)).expect("V68 growth preflight"),
    )
    .expect("valid V68 growth preflight");

    assert!(matches!(
        backend.connection,
        BackendConnectionState::Connected | BackendConnectionState::Stale
    ));
    assert_eq!(backend.profile_id.as_deref(), Some(ACTIVE_PROFILE));
    assert_eq!(
        backend.profile_fingerprint.as_deref(),
        Some(ACTIVE_FINGERPRINT)
    );
    let generation = backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
        .expect("V68 staged generation");
    assert!(!generation.matches_runtime);
    assert_eq!(generation.current_profile_fingerprint, STAGED_FINGERPRINT);
    assert!(generation.source_path.ends_with("candidate_v68.toml"));
    assert_eq!(
        generation
            .current_asset_market_slippage_caps
            .as_ref()
            .and_then(|caps| caps.get("BTC")),
        Some(&0.002)
    );
    assert_eq!(
        backend.growth_preflight.candidate_profile_id.as_deref(),
        Some(STAGED_PROFILE)
    );
    assert!(backend.growth_preflight.retired_assets.is_empty());

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.apply_backend_telemetry(backend);
    for (width, height) in [(120, 36), (160, 50), (190, 52)] {
        for tab in 1..=9 {
            app.active_tab = tab - 1;
            let screen = render(&app, width, height);
            for invalid in [
                "BACKEND DISCONNECTED",
                "ANALYSIS UNAVAILABLE",
                "IDENTITY MISMATCH",
                "PATH IDENTITY INVALID",
            ] {
                assert!(
                    !screen.contains(invalid),
                    "{width}x{height} screen {tab}: {invalid}\n{screen}"
                );
            }
        }
    }

    app.active_tab = 8;
    app.selected_cohort_symbol_index = 0;
    let mut config_pages = String::new();
    for _ in 0..8 {
        config_pages.push_str(&render(&app, 160, 50));
        app.page_cohort_config_context(1);
    }
    for expected in [
        "PENDING RESTART PROFILE V68",
        "NEXT-RUN IOC CAPS BTC ENTRY 20.0bps // CLOSE 20.0bps // RESTART REQUIRED",
        "PROFILE CHANGE APPROVED // RETIRED 0 // REPLACEMENTS 0 // EXECUTION AUTHORITY NONE",
    ] {
        assert!(
            config_pages.contains(expected),
            "missing {expected}\n{config_pages}"
        );
    }
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V68 staged checkpoint");
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
