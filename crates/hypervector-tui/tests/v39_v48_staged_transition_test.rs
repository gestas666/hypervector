use std::collections::BTreeMap;

use hypervector_tui::{
    App,
    backend_cohort::{BackendCohortTelemetry, CohortProvider},
    backend_cohort_configuration::{CohortConfigurationGeneration, CohortPendingAssetSizing},
    backend_telemetry::BackendTelemetrySnapshot,
};
use ratatui::{Terminal, backend::TestBackend};

const V39: &str = "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5";
const V48: &str = "badda60d549db4fcce9c6a6883198dd71a22f91b58a8073fa5f502c459716f22";

#[test]
fn v48_growth_roster_and_sizing_are_visible_before_restart() {
    let app = staged_app();

    for (width, height) in [(160, 50), (220, 58)] {
        let screen = render(&app, width, height);
        assert!(
            screen.contains(
                "NEXT ASSETS 4 // ROUTES EFFECTIVE 14 // NEXT 5 // SIDE SCOPES 8 // REMOVE 13 // ADD 4"
            ),
            "{width}x{height}\n{screen}"
        );
        assert!(screen.contains("BTC HULK SHORT"), "{screen}");
        assert!(screen.contains("BTC SWEEP 60/60"), "{screen}");
        assert!(screen.contains("RANGE ONSET"), "{screen}");
        assert!(screen.contains("HYPE COMPRESSION"), "{screen}");
        assert!(screen.contains("NEXT SIZING 4 ASSETS"), "{screen}");
        assert!(screen.contains("LEV 10.0x"), "{screen}");
        assert!(screen.contains("MARGIN 15.00%/ASSET"), "{screen}");
        assert!(screen.contains("CAP $7500/ASSET"), "{screen}");
        assert!(screen.contains("BLOCKED BY xyz:SNDK,xyz:SPCX"), "{screen}");
        assert!(screen.contains("WAIT FOR FLAT + NO ORDERS"), "{screen}");
        assert!(screen.contains("LIVE ARMING IS CLI-ONLY"), "{screen}");
    }
}

fn staged_app() -> App {
    let mut backend = BackendTelemetrySnapshot::disconnected("fixture");
    backend.run_id = Some("bidirectional-live-v39".into());
    backend.profile_fingerprint = Some(V39.into());
    backend.strategy_name = Some("multi_asset_bidirectional_cohort".into());
    backend.execution_mode = Some("live".into());
    backend.live_armed = Some(true);
    backend.execution_authority = Some("hyperliquid_mainnet".into());
    backend.cohort = BackendCohortTelemetry {
        enabled_symbols: strings(&[
            "BTC",
            "ETH",
            "SOL",
            "HYPE",
            "xyz:SP500",
            "xyz:SPCX",
            "xyz:SNDK",
            "xyz:BRENTOIL",
        ]),
        providers: v39_providers(),
        maximum_concurrent_positions: 10,
        config_source_path: Some("configs/v39.toml".into()),
        ..BackendCohortTelemetry::default()
    };
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app.backend.cohort_checkpoint.configuration_generation = Some(staged_generation());
    app.active_tab = 8;
    app
}

fn staged_generation() -> CohortConfigurationGeneration {
    CohortConfigurationGeneration {
        state: "stale_runtime_configuration".into(),
        matches_runtime: false,
        runtime_profile_fingerprint: V39.into(),
        current_profile_fingerprint: V48.into(),
        source_path: "configs/multi_asset_growth_first_5000_repaired_candidate_v48.toml".into(),
        source_modified_at_utc: "2026-08-12T16:00:00+00:00".into(),
        current_provider_execution_scopes: Some(v48_scopes()),
        current_provider_execution_directions: Some(v48_directions()),
        current_asset_sizing: Some(v48_sizing()),
        current_entry_context_overrides: Some(BTreeMap::from([(
            "range_onset_bidirectional_v1|ETH".into(),
            "dual_mtf_not_opposed".into(),
        )])),
        current_provider_sizing_overrides: Some(BTreeMap::new()),
        current_provider_directional_sizing_overrides: Some(BTreeMap::new()),
        current_provider_exit_policies: None,
        current_provider_directional_exit_policies: None,
        restart_state: "wait_for_flat_and_no_orders".into(),
        blocking_assets: strings(&["xyz:SNDK", "xyz:SPCX"]),
        execution_authority: "none".into(),
        automatic_restart: false,
    }
}

fn v48_scopes() -> BTreeMap<String, Vec<String>> {
    BTreeMap::from([
        ("hulk_expansion_short_robust_v3".into(), strings(&["BTC"])),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2".into(),
            strings(&["BTC"]),
        ),
        (
            "range_onset_bidirectional_v1".into(),
            strings(&["ETH", "SOL"]),
        ),
        (
            "hype_breakout_compression_pullback_bidirectional_v1".into(),
            strings(&["HYPE"]),
        ),
    ])
}

fn v48_directions() -> BTreeMap<String, Vec<String>> {
    BTreeMap::from([
        (
            "hulk_expansion_short_robust_v3|BTC".into(),
            strings(&["short"]),
        ),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2|BTC".into(),
            strings(&["long"]),
        ),
        (
            "range_onset_bidirectional_v1|ETH".into(),
            strings(&["long", "short"]),
        ),
        (
            "range_onset_bidirectional_v1|SOL".into(),
            strings(&["long", "short"]),
        ),
        (
            "hype_breakout_compression_pullback_bidirectional_v1|HYPE".into(),
            strings(&["long", "short"]),
        ),
    ])
}

fn v48_sizing() -> BTreeMap<String, CohortPendingAssetSizing> {
    ["BTC", "ETH", "SOL", "HYPE"]
        .into_iter()
        .map(|symbol| {
            (
                symbol.into(),
                CohortPendingAssetSizing {
                    leverage: 10.0,
                    margin_fraction: 0.15,
                    max_notional_usd: 7_500.0,
                },
            )
        })
        .collect()
}

fn v39_providers() -> Vec<CohortProvider> {
    v39_scopes()
        .into_iter()
        .map(|(strategy, symbols)| CohortProvider {
            strategy_id: strategy.into(),
            symbols: strings(symbols),
            sides: strings(&["long", "short"]),
            priority: 10,
            timeframe: "5m".into(),
            maximum_entry_delay_seconds: 300,
            execution_symbols: Some(strings(symbols)),
            execution_side_overrides: BTreeMap::new(),
            entry_context_overrides: BTreeMap::new(),
            sizing_overrides: BTreeMap::new(),
            source_profile: None,
            execution: None,
        })
        .collect()
}

fn v39_scopes() -> [(&'static str, &'static [&'static str]); 7] {
    [
        (
            "hulk_expansion_bidirectional_tuned_v2",
            &["BTC", "ETH", "SOL", "HYPE"],
        ),
        ("hypervelocity_source_follow_bidirectional_5m_v1", &["BTC"]),
        (
            "hype_breakout_onset_bidirectional_v1",
            &["BTC", "ETH", "SOL"],
        ),
        (
            "hype_breakout_compression_pullback_bidirectional_v1",
            &["HYPE"],
        ),
        (
            "eth_breakout_precompression_pullback_bidirectional_v1",
            &["ETH"],
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
            &["xyz:SP500", "xyz:SPCX"],
        ),
        (
            "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1",
            &["xyz:SNDK", "xyz:BRENTOIL"],
        ),
    ]
}

fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).into()).collect()
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw v48 transition");
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
