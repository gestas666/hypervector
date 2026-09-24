use std::collections::BTreeMap;

use hypervector_tui::{
    App,
    backend_cohort::{
        BackendCohortTelemetry, CohortAssetConfig, CohortProvider, CohortRuntimeConfig,
    },
    backend_cohort_configuration::{
        CohortConfigurationGeneration, CohortPendingAssetSizing, CohortPendingExitPolicy,
    },
    backend_telemetry::BackendTelemetrySnapshot,
};
use ratatui::{Terminal, backend::TestBackend};

const V39: &str = "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5";
const V51: &str = "30cd54bb5b5b17249ae0a6a3b01d5702b276d51f8dc5ddd6b4d36ab6aa7d1908";
const INDEX: &str = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3";

#[test]
fn v51_exit_and_exact_index_sides_fit_at_160x50() {
    let app = staged_app();
    let screen = render(&app);

    assert!(
        screen.contains("PENDING PROFILE EXIT HIP3 BK15 IDX"),
        "{screen}"
    );
    assert!(screen.contains("PROFIT LOCK 100/40/80bps"), "{screen}");
    assert!(
        screen.contains("xyz:SP500:long+short,xyz:SPCX:long+short"),
        "{screen}"
    );
    assert!(
        screen.contains("LOCAL EDIT DRAFT // ACTIVE-RUNTIME COPY // SEPARATE FROM PENDING PROFILE"),
        "{screen}"
    );
}

#[test]
fn every_v51_transition_row_is_accessible_with_context_paging() {
    let mut app = staged_app();
    let mut pages = render(&app);
    for _ in 0..4 {
        app.page_cohort_config_context(1);
        pages.push_str(&render(&app));
    }

    for provider in [
        "BTC HULK SHORT",
        "BTC SWEEP 60/60",
        "RANGE ONSET",
        "HYPE COMPRESSION",
        "HIP3 BK15 IDX",
        "HV SOURCE 5M",
        "ETH BK PULLBACK",
        "HIP3 BK CMD",
    ] {
        assert!(pages.contains(provider), "missing {provider}\n{pages}");
    }
    assert!(pages.contains("[PgUp/PgDn] Scope"), "{pages}");
    assert!(pages.contains("LIVE ARMING IS CLI-ONLY"), "{pages}");

    app.page_cohort_config_context(-1);
    let previous = render(&app);
    assert!(previous.contains("CONTENT WINDOW"), "{previous}");
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
        asset_configs: [
            "BTC",
            "ETH",
            "SOL",
            "HYPE",
            "xyz:SP500",
            "xyz:SPCX",
            "xyz:SNDK",
            "xyz:BRENTOIL",
        ]
        .into_iter()
        .map(asset_config)
        .collect(),
        providers: v39_providers(),
        maximum_concurrent_positions: 10,
        config_source_path: Some("configs/v39.toml".into()),
        runtime: Some(CohortRuntimeConfig {
            poll_seconds: 30.0,
            lookback_days: 10,
        }),
        ..BackendCohortTelemetry::default()
    };
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app.backend.cohort_checkpoint.configuration_generation = Some(staged_generation());
    app.active_tab = 8;
    app
}

fn asset_config(symbol: &str) -> CohortAssetConfig {
    CohortAssetConfig {
        symbol: symbol.into(),
        sides: strings(&["long", "short"]),
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

fn staged_generation() -> CohortConfigurationGeneration {
    CohortConfigurationGeneration {
        state: "stale_runtime_configuration".into(),
        matches_runtime: false,
        runtime_profile_fingerprint: V39.into(),
        current_profile_fingerprint: V51.into(),
        source_path:
            "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml".into(),
        source_modified_at_utc: "2026-08-13T04:00:00+00:00".into(),
        current_provider_execution_scopes: Some(v51_scopes()),
        current_provider_execution_directions: Some(v51_directions()),
        current_asset_sizing: Some(v51_sizing()),
        current_asset_entry_slippage_caps: None,
        current_asset_market_slippage_caps: None,
        current_entry_context_overrides: Some(BTreeMap::new()),
        current_provider_sizing_overrides: Some(BTreeMap::new()),
        current_provider_directional_sizing_overrides: Some(BTreeMap::new()),
        current_provider_exit_policies: Some(BTreeMap::from([(
            INDEX.into(),
            CohortPendingExitPolicy {
                stop_risk_budget: None,
                maximum_hold_seconds: 86_400,
                maximum_hold_policy: "fixed".into(),
                hard_maximum_hold_seconds: None,
                maximum_hold_evidence_maximum_age_seconds: None,
                provider_recipe_exit_policy: "ignore".into(),
                adaptive_exit_policy: "none".into(),
                breakeven_stop_target: "entry_offset".into(),
                profit_lock_policy: "completed_bar_trailing".into(),
                profit_lock_activation_bps: Some(100.0),
                profit_lock_floor_bps: Some(40.0),
                profit_lock_giveback_bps: Some(80.0),
            },
        )])),
        current_provider_directional_exit_policies: None,
        restart_state: "wait_for_flat_and_no_orders".into(),
        blocking_assets: strings(&["BTC", "xyz:SP500", "xyz:SPCX"]),
        execution_authority: "none".into(),
        automatic_restart: false,
    }
}

fn v51_scopes() -> BTreeMap<String, Vec<String>> {
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
        (INDEX.into(), strings(&["xyz:SP500", "xyz:SPCX"])),
    ])
}

fn v51_directions() -> BTreeMap<String, Vec<String>> {
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
        (format!("{INDEX}|xyz:SP500"), strings(&["long", "short"])),
        (format!("{INDEX}|xyz:SPCX"), strings(&["long", "short"])),
    ])
}

fn v51_sizing() -> BTreeMap<String, CohortPendingAssetSizing> {
    ["BTC", "ETH", "SOL", "HYPE", "xyz:SP500", "xyz:SPCX"]
        .into_iter()
        .map(|symbol| {
            (
                symbol.into(),
                CohortPendingAssetSizing {
                    leverage: 10.0,
                    margin_fraction: 0.10,
                    max_notional_usd: 5_000.0,
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

fn render(app: &App) -> String {
    let mut terminal = Terminal::new(TestBackend::new(160, 50)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw v51 transition");
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
