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
v66_brentoil_flat_5000_preflight_20260901T0912Z.json";
const ACTIVE_PROFILE: &str =
    "multi_asset_growth_first_5000_five_asset_bleeding_stopped_candidate_v65";
const ACTIVE_FINGERPRINT: &str = "167c090dc962b72f2e43c616f0f4cc8dfd9f70bda314ef0713a5a481a0590d0c";
const STAGED_PROFILE: &str =
    "multi_asset_growth_first_5000_four_asset_brentoil_retired_candidate_v66";
const STAGED_FINGERPRINT: &str = "b5e744120de021e72f872e733db23f88b182451c8de05eb14d5ad9f81098a132";

#[test]
#[ignore = "requires the local flat V65 ledger and report-only V66 checkpoint"]
fn staged_v66_retirement_is_visible_on_all_nine_screens() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(STAGED_CHECKPOINT)),
    );
    let mut backend = source.refresh();
    backend.growth_preflight = parse_growth_preflight(
        &fs::read_to_string(root.join(GROWTH_PREFLIGHT)).expect("V66 growth preflight"),
    )
    .expect("valid V66 growth preflight");

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
        .expect("V66 staged generation");
    assert!(!generation.matches_runtime);
    assert_eq!(generation.current_profile_fingerprint, STAGED_FINGERPRINT);
    assert!(generation.source_path.ends_with("candidate_v66.toml"));
    assert_eq!(
        backend.growth_preflight.candidate_profile_id.as_deref(),
        Some(STAGED_PROFILE)
    );
    assert_eq!(backend.growth_preflight.retired_assets.len(), 1);

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

    let mut screens = String::new();
    app.active_tab = 8;
    app.selected_cohort_symbol_index = app
        .backend
        .cohort
        .asset_configs
        .iter()
        .position(|asset| asset.symbol == "xyz:BRENTOIL")
        .expect("retired V65 BRENTOIL asset");
    for _ in 0..5 {
        screens.push_str(&render(&app, 160, 50));
        app.page_cohort_config_context(1);
    }
    for expected in [
        "PENDING RESTART PROFILE V66",
        "$5K PREFLIGHT READY // 10 SLOTS // MAX MARGIN 48.0% // BLOCKERS NONE",
        "PROFILE CHANGE APPROVED // RETIRED 2 // REPLACEMENTS 0 // EXECUTION AUTHORITY NONE",
        "RETIRED ASSET xyz:BRENTOIL // FLAT + NO ORDERS // LEDGER RECONCILED",
        "NEXT ASSETS 4 // ROUTES EFFECTIVE 8 // NEXT 7 // SIDE SCOPES 11 // REMOVE 1 // ADD 0",
        "LIVE ARMING IS CLI-ONLY",
    ] {
        assert!(screens.contains(expected), "missing {expected}\n{screens}");
    }
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V66 staged checkpoint");
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
