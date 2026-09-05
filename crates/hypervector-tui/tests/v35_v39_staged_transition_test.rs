use std::collections::BTreeMap;

use hypervector_tui::{
    App,
    backend_cohort::{
        BackendCohortTelemetry, CohortAssetConfig, CohortProvider, CohortRuntimeConfig,
    },
    backend_cohort_configuration::CohortConfigurationGeneration,
    backend_telemetry::BackendTelemetrySnapshot,
};
use ratatui::{Terminal, backend::TestBackend};

const BIDIRECTIONAL_SIDES: [&str; 2] = ["long", "short"];
const V35_FINGERPRINT: &str = "8acc70105f8254dc6a7a3f690cebbaec8b3b81c94547d11b895eb6bbe03a24c4";
const V39_FINGERPRINT: &str = "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5";
const V42_FINGERPRINT: &str = "c691ee99f6f450990b9c2e25059fba8b5f266f8d6caff33900fc8a259b003097";
const V44_FINGERPRINT: &str = "a947c234d900f01ba993358e75ef44589a3262e000d0a67070c94c353dc1249a";

#[test]
fn exact_v35_to_v39_scope_diff_is_visible_at_wide_acceptance_size() {
    let app = transition_app();
    let staged = staged_scopes();
    let screen = render(&app, 220, 58);

    assert_eq!(route_count(&app), 24);
    assert_eq!(staged.values().map(Vec::len).sum::<usize>(), 14);
    assert_eq!(
        staged
            .values()
            .map(|symbols| symbols.len() * BIDIRECTIONAL_SIDES.len())
            .sum::<usize>(),
        28
    );
    assert!(staged.values().all(|symbols| !symbols.is_empty()));
    assert!(screen.contains(
        "NEXT ASSETS 8 // ROUTES EFFECTIVE 24 // NEXT 14 // SIDE SCOPES 28 // REMOVE 11 // ADD 1"
    ));
    assert!(screen.contains("RANGE ONSET"));
    assert!(screen.contains("REMOVE BTC/ETH/HYPE/SOL"));
    assert!(screen.contains("HIP3 SWING IDX"));
    assert!(screen.contains("REMOVE xyz:SP500/xyz:SPCX"));
    assert!(screen.contains("HIP3 SWING CMD"));
    assert!(screen.contains("REMOVE xyz:BRENTOIL/xyz:GOLD/xyz:SNDK"));
    assert!(screen.contains("HT-Breakout"));
    assert!(screen.contains("REMOVE HYPE"));
    assert!(screen.contains("HYPE COMPRESSION"));
    assert!(screen.contains("EFFECTIVE ABSENT -> NEXT HYPE // ADD HYPE"));
    assert!(!screen.contains("OBSERVE ONLY"));
}

#[test]
fn staged_v39_blockers_and_safety_survive_acceptance_size_overflow() {
    let app = transition_app();

    for (width, height) in [(120, 36), (220, 58)] {
        let screen = render(&app, width, height);
        assert!(
            screen.contains("PENDING RESTART PROFILE"),
            "{width}x{height}\n{screen}"
        );
        assert!(
            screen.contains("BLOCKED BY SOL,xyz:SPCX"),
            "{width}x{height}\n{screen}"
        );
        assert!(
            screen.contains("WAIT FOR FLAT + NO ORDERS"),
            "{width}x{height}\n{screen}"
        );
        assert!(
            screen.contains("AUTO RESTART NO"),
            "{width}x{height}\n{screen}"
        );
        assert!(
            screen.contains("LIVE ARMING IS CLI-ONLY"),
            "{width}x{height}\n{screen}"
        );
        if width == 120 {
            assert!(screen.contains("CONTENT WINDOW"), "{screen}");
            assert!(screen.contains("LINES OMITTED"), "{screen}");
        }
    }
}

#[test]
fn staged_side_scope_count_fails_closed_for_a_non_bidirectional_identity() {
    let mut app = transition_app();
    let scopes = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_mut()
        .and_then(|generation| generation.current_provider_execution_scopes.as_mut())
        .expect("staged scopes");
    let symbols = scopes
        .remove("hype_breakout_compression_pullback_bidirectional_v1")
        .expect("HYPE compression scope");
    scopes.insert("hype_breakout_compression_pullback_v1".into(), symbols);

    let screen = render(&app, 220, 58);

    assert!(screen.contains("SIDE SCOPES UNREPORTED"), "{screen}");
    assert!(!screen.contains("SIDE SCOPES 28"), "{screen}");
}

#[test]
fn exact_v39_to_v42_scope_reduction_is_visible_without_false_capacity() {
    let app = v39_to_v42_app();

    for (width, height) in [(160, 50), (220, 58)] {
        let screen = render(&app, width, height);
        assert!(
            screen.contains(
                "NEXT ASSETS 3 // ROUTES EFFECTIVE 14 // NEXT 3 // SIDE SCOPES 6 // REMOVE 11 // ADD 0"
            ),
            "{width}x{height}\n{screen}"
        );
        assert!(
            screen.contains("WAIT FOR FLAT + NO ORDERS"),
            "{width}x{height}\n{screen}"
        );
        assert!(
            screen.contains("LIVE ARMING IS CLI-ONLY"),
            "{width}x{height}\n{screen}"
        );
    }
}

#[test]
fn exact_v39_to_v44_correction_is_visible_without_claiming_activation() {
    let mut app = v39_to_v42_app();
    app.backend.cohort_checkpoint.configuration_generation = Some(v44_generation());

    for (width, height) in [(160, 50), (220, 58)] {
        let screen = render(&app, width, height);
        assert!(
            screen.contains(
                "NEXT ASSETS 3 // ROUTES EFFECTIVE 14 // NEXT 4 // SIDE SCOPES 6 // REMOVE 12 // ADD 2"
            ),
            "{width}x{height}\n{screen}"
        );
        assert!(screen.contains("BTC HULK SHORT"), "{screen}");
        assert!(screen.contains("BTC SWEEP 60/60"), "{screen}");
        assert!(screen.contains("WAIT FOR FLAT + NO ORDERS"), "{screen}");
        assert!(screen.contains("LIVE ARMING IS CLI-ONLY"), "{screen}");
    }
}

fn transition_app() -> App {
    let mut backend = BackendTelemetrySnapshot::disconnected("fixture");
    backend.run_id = Some("bidirectional-live-fixture".into());
    backend.profile_fingerprint = Some(V35_FINGERPRINT.into());
    backend.strategy_name = Some("multi_asset_bidirectional_cohort".into());
    backend.execution_mode = Some("live".into());
    backend.live_armed = Some(true);
    backend.execution_authority = Some("hyperliquid_mainnet".into());
    backend.cohort = BackendCohortTelemetry {
        enabled_symbols: symbols().iter().map(|value| (*value).into()).collect(),
        asset_configs: symbols().iter().map(|value| asset(value)).collect(),
        providers: providers(),
        maximum_concurrent_positions: 10,
        config_source_path: Some(
            "configs/multi_asset_bidirectional_all_live_canary_v35.toml".into(),
        ),
        runtime: Some(CohortRuntimeConfig {
            poll_seconds: 30.0,
            lookback_days: 10,
        }),
        ..BackendCohortTelemetry::default()
    };
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app.backend.cohort_checkpoint.configuration_generation = Some(configuration_generation());
    app.active_tab = 8;
    app
}

fn v39_to_v42_app() -> App {
    let mut app = transition_app();
    app.backend.profile_fingerprint = Some(V39_FINGERPRINT.into());
    app.backend.cohort.enabled_symbols = strings(&[
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:BRENTOIL",
    ]);
    app.backend.cohort.providers = v39_scopes()
        .into_iter()
        .map(|(strategy, symbols)| CohortProvider {
            strategy_id: strategy.into(),
            symbols: strings(symbols),
            sides: strings(&BIDIRECTIONAL_SIDES),
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
        .collect();
    app.backend.cohort.config_source_path = Some(
        "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml"
            .into(),
    );
    app.backend.cohort_checkpoint.configuration_generation = Some(v42_configuration_generation());
    app
}

fn symbols() -> [&'static str; 9] {
    [
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:GOLD",
        "xyz:BRENTOIL",
    ]
}

fn asset(symbol: &str) -> CohortAssetConfig {
    CohortAssetConfig {
        symbol: symbol.into(),
        sides: strings(&BIDIRECTIONAL_SIDES),
        leverage: 5.0,
        venue_max_leverage: 20.0,
        margin_fraction: 0.03,
        max_notional_usd: 75.0,
        entry_slippage_cap_fraction: None,
        market_slippage_cap_fraction: None,
        stop_bps: 80.0,
        maximum_hold_seconds: 86_400,
    }
}

fn providers() -> Vec<CohortProvider> {
    active_scopes()
        .into_iter()
        .map(|(strategy, symbols)| CohortProvider {
            strategy_id: strategy.into(),
            symbols: strings(symbols),
            sides: strings(&BIDIRECTIONAL_SIDES),
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

fn active_scopes() -> [(&'static str, &'static [&'static str]); 9] {
    [
        (
            "hulk_expansion_bidirectional_tuned_v2",
            &["BTC", "ETH", "SOL", "HYPE"],
        ),
        (
            "range_onset_bidirectional_v1",
            &["BTC", "ETH", "SOL", "HYPE"],
        ),
        ("hypervelocity_source_follow_bidirectional_5m_v1", &["BTC"]),
        (
            "hype_breakout_onset_bidirectional_v1",
            &["BTC", "ETH", "SOL", "HYPE"],
        ),
        (
            "eth_breakout_precompression_pullback_bidirectional_v1",
            &["ETH"],
        ),
        (
            "hip3_swing_ha_sp500_spcx_bidirectional_v2",
            &["xyz:SP500", "xyz:SPCX"],
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
            &["xyz:SP500", "xyz:SPCX"],
        ),
        (
            "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
            &["xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL"],
        ),
        (
            "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1",
            &["xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL"],
        ),
    ]
}

fn staged_scopes() -> BTreeMap<String, Vec<String>> {
    BTreeMap::from([
        (
            "hulk_expansion_bidirectional_tuned_v2".into(),
            strings(&["BTC", "ETH", "SOL", "HYPE"]),
        ),
        (
            "hypervelocity_source_follow_bidirectional_5m_v1".into(),
            strings(&["BTC"]),
        ),
        (
            "hype_breakout_onset_bidirectional_v1".into(),
            strings(&["BTC", "ETH", "SOL"]),
        ),
        (
            "hype_breakout_compression_pullback_bidirectional_v1".into(),
            strings(&["HYPE"]),
        ),
        (
            "eth_breakout_precompression_pullback_bidirectional_v1".into(),
            strings(&["ETH"]),
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1".into(),
            strings(&["xyz:SP500", "xyz:SPCX"]),
        ),
        (
            "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1".into(),
            strings(&["xyz:SNDK", "xyz:BRENTOIL"]),
        ),
    ])
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

fn v42_scopes() -> BTreeMap<String, Vec<String>> {
    BTreeMap::from([
        (
            "hulk_expansion_bidirectional_tuned_v2".into(),
            strings(&["BTC"]),
        ),
        (
            "hype_breakout_compression_pullback_bidirectional_v1".into(),
            strings(&["HYPE"]),
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1".into(),
            strings(&["xyz:SP500"]),
        ),
    ])
}

fn v42_configuration_generation() -> CohortConfigurationGeneration {
    CohortConfigurationGeneration {
        state: "stale_runtime_configuration".into(),
        matches_runtime: false,
        runtime_profile_fingerprint: V39_FINGERPRINT.into(),
        current_profile_fingerprint: V42_FINGERPRINT.into(),
        source_path: "configs/multi_asset_bidirectional_focused_growth_5000_candidate_v42.toml"
            .into(),
        source_modified_at_utc: "2026-08-11T18:28:00+00:00".into(),
        current_provider_execution_scopes: Some(v42_scopes()),
        current_provider_execution_directions: None,
        current_asset_sizing: None,
        current_asset_entry_slippage_caps: None,
        current_asset_market_slippage_caps: None,
        current_entry_context_overrides: Some(BTreeMap::new()),
        current_provider_sizing_overrides: Some(BTreeMap::new()),
        current_provider_directional_sizing_overrides: Some(BTreeMap::new()),
        current_provider_exit_policies: None,
        current_provider_directional_exit_policies: None,
        restart_state: "wait_for_flat_and_no_orders".into(),
        blocking_assets: strings(&["BTC", "ETH", "SOL", "xyz:SP500"]),
        execution_authority: "none".into(),
        automatic_restart: false,
    }
}

fn v44_generation() -> CohortConfigurationGeneration {
    let scopes = BTreeMap::from([
        ("hulk_expansion_short_robust_v3".into(), strings(&["BTC"])),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2".into(),
            strings(&["BTC"]),
        ),
        (
            "hype_breakout_compression_pullback_bidirectional_v1".into(),
            strings(&["HYPE"]),
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1".into(),
            strings(&["xyz:SP500"]),
        ),
    ]);
    let directions = BTreeMap::from([
        (
            "hulk_expansion_short_robust_v3|BTC".into(),
            strings(&["short"]),
        ),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2|BTC".into(),
            strings(&["long"]),
        ),
        (
            "hype_breakout_compression_pullback_bidirectional_v1|HYPE".into(),
            strings(&BIDIRECTIONAL_SIDES),
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1|xyz:SP500".into(),
            strings(&BIDIRECTIONAL_SIDES),
        ),
    ]);
    let mut generation = v42_configuration_generation();
    generation.current_profile_fingerprint = V44_FINGERPRINT.into();
    generation.source_path =
        "configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml".into();
    generation.current_provider_execution_scopes = Some(scopes);
    generation.current_provider_execution_directions = Some(directions);
    generation
}

fn configuration_generation() -> CohortConfigurationGeneration {
    CohortConfigurationGeneration {
        state: "stale_runtime_configuration".into(),
        matches_runtime: false,
        runtime_profile_fingerprint: V35_FINGERPRINT.into(),
        current_profile_fingerprint: V39_FINGERPRINT.into(),
        source_path: "configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml".into(),
        source_modified_at_utc: "2026-08-11T00:18:59+00:00".into(),
        current_provider_execution_scopes: Some(staged_scopes()),
        current_provider_execution_directions: None,
        current_asset_sizing: None,
        current_asset_entry_slippage_caps: None,
        current_asset_market_slippage_caps: None,
        current_entry_context_overrides: Some(BTreeMap::new()),
        current_provider_sizing_overrides: Some(BTreeMap::new()),
        current_provider_directional_sizing_overrides: Some(BTreeMap::new()),
        current_provider_exit_policies: None,
        current_provider_directional_exit_policies: None,
        restart_state: "wait_for_flat_and_no_orders".into(),
        blocking_assets: strings(&["SOL", "xyz:SPCX"]),
        execution_authority: "none".into(),
        automatic_restart: false,
    }
}

fn route_count(app: &App) -> usize {
    app.backend
        .cohort
        .providers
        .iter()
        .map(|provider| provider.execution_symbols.as_ref().map_or(0, Vec::len))
        .sum()
}

fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).into()).collect()
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw staged transition");
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
