use std::{fs, path::PathBuf};

use hypervector_tui::{
    App,
    backend_growth_preflight::parse_growth_preflight,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

const ACTIVE_LEDGER: &str = "data/live/bidirectional_cohort/decisions.jsonl";
const STAGED_CHECKPOINT: &str = "data/runtime/bidirectional_cohort/latest_checkpoint.json";
const GROWTH_PREFLIGHT: &str = "data/logs/research/bidirectional_cohort/\
v64_gold_removed_flat_preflight_20260901T0456Z.json";
const ACTIVE_PROFILE: &str =
    "multi_asset_growth_first_5000_nine_asset_bankroll_builder_candidate_v63";
const ACTIVE_FINGERPRINT: &str = "b81d0d22ed041ad007dfe4b6c55c652889ecc133bc9939e08eac5613e6fc1681";
const STAGED_PROFILE: &str = "multi_asset_growth_first_5000_eight_asset_gold_removed_candidate_v64";
const STAGED_FINGERPRINT: &str = "3a687cb3de08eb4d8df82b91e0c8f9af3c40c335bd15027554501f9516781d38";

#[test]
#[ignore = "requires the local flat V63 ledger and report-only V64 checkpoint"]
fn staged_v64_removal_is_visible_on_all_nine_screens() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(STAGED_CHECKPOINT)),
    );
    let mut backend = source.refresh();
    backend.growth_preflight = parse_growth_preflight(
        &fs::read_to_string(root.join(GROWTH_PREFLIGHT)).expect("V64 growth preflight"),
    )
    .expect("valid V64 growth preflight");

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
        .expect("V64 staged generation");
    assert!(!generation.matches_runtime);
    assert_eq!(generation.current_profile_fingerprint, STAGED_FINGERPRINT);
    assert!(generation.source_path.ends_with("candidate_v64.toml"));
    assert_eq!(
        backend.growth_preflight.candidate_profile_id.as_deref(),
        Some(STAGED_PROFILE)
    );
    assert_eq!(backend.growth_preflight.retired_assets.len(), 1);
    assert_eq!(
        backend.growth_preflight.retired_assets[0].symbol,
        "xyz:GOLD"
    );

    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.apply_backend_telemetry(backend);
    for (width, height) in [(120, 36), (160, 50), (190, 52)] {
        for tab in 1..=9 {
            app.active_tab = tab - 1;
            let screen = render(&app, width, height);
            if tab == 9 && std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
                println!("\n===== V64 {width}x{height} SCREEN {tab} =====\n{screen}");
            }
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
    app.selected_cohort_symbol_index = app
        .backend
        .cohort
        .asset_configs
        .iter()
        .position(|asset| asset.symbol == "xyz:GOLD")
        .expect("active GOLD asset");
    let mut screens = render(&app, 160, 50);
    for _ in 0..4 {
        app.page_cohort_config_context(1);
        screens.push_str(&render(&app, 160, 50));
    }
    for expected in [
        "PENDING RESTART PROFILE V64",
        "$5K PREFLIGHT READY // 10 SLOTS // MAX MARGIN 91.0% // BLOCKERS NONE",
        "PROFILE CHANGE APPROVED // RETIRED 2 // REPLACEMENTS 0 // EXECUTION AUTHORITY NONE",
        "RETIRED ASSET xyz:GOLD // FLAT + NO ORDERS // LEDGER RECONCILED",
        "NEXT ASSETS 8 // ROUTES EFFECTIVE 14 // NEXT 13 // SIDE SCOPES 23 // REMOVE 1 // ADD 0",
        "REMOVE xyz:GOLD",
        "LIVE ARMING IS CLI-ONLY",
    ] {
        assert!(screens.contains(expected), "missing {expected}\n{screens}");
    }
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V64 staged checkpoint");
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
