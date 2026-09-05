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
v65_bleeding_assets_flat_5000_preflight_20260901T0830Z.json";
const ACTIVE_PROFILE: &str = "multi_asset_growth_first_5000_eight_asset_gold_removed_candidate_v64";
const ACTIVE_FINGERPRINT: &str = "3a687cb3de08eb4d8df82b91e0c8f9af3c40c335bd15027554501f9516781d38";
const STAGED_PROFILE: &str =
    "multi_asset_growth_first_5000_five_asset_bleeding_stopped_candidate_v65";
const STAGED_FINGERPRINT: &str = "167c090dc962b72f2e43c616f0f4cc8dfd9f70bda314ef0713a5a481a0590d0c";

#[test]
#[ignore = "requires the local flat V64 ledger and report-only V65 checkpoint"]
fn staged_v65_retirements_are_visible_on_all_nine_screens() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut source = BackendTelemetrySource::with_checkpoint_path(
        root.join(ACTIVE_LEDGER),
        Some(root.join(STAGED_CHECKPOINT)),
    );
    let mut backend = source.refresh();
    backend.growth_preflight = parse_growth_preflight(
        &fs::read_to_string(root.join(GROWTH_PREFLIGHT)).expect("V65 growth preflight"),
    )
    .expect("valid V65 growth preflight");

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
        .expect("V65 staged generation");
    assert!(!generation.matches_runtime);
    assert_eq!(generation.current_profile_fingerprint, STAGED_FINGERPRINT);
    assert!(generation.source_path.ends_with("candidate_v65.toml"));
    assert_eq!(
        backend.growth_preflight.candidate_profile_id.as_deref(),
        Some(STAGED_PROFILE)
    );
    assert_eq!(backend.growth_preflight.retired_assets.len(), 3);

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
    for symbol in ["ETH", "xyz:SP500", "xyz:SPCX"] {
        app.active_tab = 8;
        app.selected_cohort_symbol_index = app
            .backend
            .cohort
            .asset_configs
            .iter()
            .position(|asset| asset.symbol == symbol)
            .expect("retired V64 asset");
        for _ in 0..5 {
            screens.push_str(&render(&app, 160, 50));
            app.page_cohort_config_context(1);
        }
    }
    for expected in [
        "PENDING RESTART PROFILE V65",
        "$5K PREFLIGHT READY // 10 SLOTS // MAX MARGIN 56.0% // BLOCKERS NONE",
        "PROFILE CHANGE APPROVED // RETIRED 10 // REPLACEMENTS 0 // EXECUTION AUTHORITY NONE",
        "RETIRED ASSET ETH // FLAT + NO ORDERS // LEDGER RECONCILED",
        "RETIRED ASSET xyz:SP500 // FLAT + NO ORDERS // LEDGER RECONCILED",
        "RETIRED ASSET xyz:SPCX // FLAT + NO ORDERS // LEDGER RECONCILED",
        "NEXT ASSETS 5 // ROUTES EFFECTIVE 13 // NEXT 8 // SIDE SCOPES 13 // REMOVE 5 // ADD 0",
        "LIVE ARMING IS CLI-ONLY",
    ] {
        assert!(screens.contains(expected), "missing {expected}\n{screens}");
    }
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw V65 staged checkpoint");
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
