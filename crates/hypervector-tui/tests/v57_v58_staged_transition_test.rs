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

const V57: &str = "724c259bd94be60d80ffc2e6b9a760412b9729ab1f8fea403e61d266f0d9cb8d";
const V58: &str = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b";
const V59: &str = "c057882fdd0818831076685aa0fb0134b22889618f6c145ca8e1f9f33111ab78";
const INDEX: &str = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3";
const COMMODITY: &str = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2";

#[test]
fn v58_all_eight_assets_and_direction_scopes_are_visible_at_160x50() {
    let mut app = staged_app();
    let mut pages = render(&app);
    for _ in 0..6 {
        app.page_cohort_config_context(1);
        pages.push_str(&render(&app));
    }

    assert!(pages.contains(
        "NEXT ASSETS 8 // ROUTES EFFECTIVE 5 // NEXT 10 // SIDE SCOPES 14 // REMOVE 0 // ADD 5"
    ));
    for symbol in [
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:BRENTOIL",
    ] {
        assert!(pages.contains(symbol), "missing {symbol}\n{pages}");
    }
    for provider in [
        "BTC HULK SHORT",
        "BTC SWEEP 60/60",
        "ETH BK PULLBACK",
        "HULK EXPANSION",
        "HYPE ALIGN",
        "HIP3 BK15 IDX",
        "SPCX CASH OPEN",
        "HIP3 BK15 CMD",
    ] {
        assert!(pages.contains(provider), "missing {provider}\n{pages}");
    }
    assert!(pages.contains("SOL:short"), "{pages}");
    assert!(pages.contains("xyz:SNDK:short"), "{pages}");
    assert!(pages.contains("xyz:BRENTOIL:long+short"), "{pages}");
}

#[test]
fn v58_sizing_profit_lock_and_cli_only_safety_are_visible() {
    let mut app = staged_app();
    let mut pages = render(&app);
    for _ in 0..6 {
        app.page_cohort_config_context(1);
        pages.push_str(&render(&app));
    }

    assert!(pages.contains("PROFIT LOCK 100/40/80bps"), "{pages}");
    assert!(pages.contains("WAIT FOR FLAT + NO ORDERS"), "{pages}");
    assert!(pages.contains("AUTO RESTART NO"), "{pages}");
    assert!(pages.contains("LIVE ARMING IS CLI-ONLY"), "{pages}");
    assert!(pages.contains("10.0x/10.00%/$5000 BTC,HYPE"), "{pages}");
    assert!(
        pages.contains("5.0x/7.00%/$1750 xyz:SP500,xyz:SPCX"),
        "{pages}"
    );
    assert!(
        pages.contains("5.0x/3.00%/$750 ETH,SOL,xyz:BRENTOIL,xyz:SNDK"),
        "{pages}"
    );
}

#[test]
fn v59_sp500_short_containment_is_visible_without_other_scope_drift() {
    let mut app = v59_staged_app();
    let mut pages = render(&app);
    for _ in 0..6 {
        app.page_cohort_config_context(1);
        pages.push_str(&render(&app));
    }

    assert!(pages.contains(
        "NEXT ASSETS 8 // ROUTES EFFECTIVE 10 // NEXT 10 // SIDE SCOPES 13 // REMOVE 0 // ADD 0"
    ));
    assert!(pages.contains("xyz:SP500:short"), "{pages}");
    assert!(!pages.contains("xyz:SP500:long+short"), "{pages}");
    assert!(pages.contains("xyz:BRENTOIL:long+short"), "{pages}");
    assert!(pages.contains("PROFIT LOCK 100/40/80bps"), "{pages}");
    assert!(pages.contains("BLOCKED BY xyz:SP500"), "{pages}");
    assert!(pages.contains("WAIT FOR FLAT + NO ORDERS"), "{pages}");
}

fn v59_staged_app() -> App {
    let mut app = staged_app();
    app.backend.run_id = Some("bidirectional-live-v58".into());
    app.backend.profile_fingerprint = Some(V58.into());
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
    app.backend.cohort.providers = v58_active_providers();
    let mut generation = staged_generation();
    generation.runtime_profile_fingerprint = V58.into();
    generation.current_profile_fingerprint = V59.into();
    generation.source_path = "configs/multi_asset_growth_first_5000_eight_asset_sp500_short_containment_candidate_v59.toml".into();
    generation.current_provider_execution_directions = Some(v59_directions());
    generation.blocking_assets = strings(&["xyz:SP500"]);
    app.backend.cohort_checkpoint.configuration_generation = Some(generation);
    app
}

fn v58_active_providers() -> Vec<CohortProvider> {
    let directions = v58_directions();
    v58_scopes()
        .into_iter()
        .map(|(strategy, symbols)| CohortProvider {
            strategy_id: strategy.clone(),
            symbols: symbols.clone(),
            sides: strings(&["long", "short"]),
            priority: 10,
            timeframe: "15m".into(),
            maximum_entry_delay_seconds: 60,
            execution_symbols: Some(symbols.clone()),
            execution_side_overrides: symbols
                .iter()
                .map(|symbol| {
                    let route = format!("{strategy}|{symbol}");
                    (symbol.clone(), directions[&route].clone())
                })
                .collect(),
            entry_context_overrides: BTreeMap::new(),
            sizing_overrides: BTreeMap::new(),
            source_profile: None,
            execution: None,
        })
        .collect()
}

fn v59_directions() -> BTreeMap<String, Vec<String>> {
    let mut directions = v58_directions();
    directions.insert(format!("{INDEX}|xyz:SP500"), strings(&["short"]));
    directions
}

fn staged_app() -> App {
    let mut backend = BackendTelemetrySnapshot::disconnected("fixture");
    backend.run_id = Some("bidirectional-live-v57".into());
    backend.profile_fingerprint = Some(V57.into());
    backend.strategy_name = Some("multi_asset_bidirectional_cohort".into());
    backend.execution_mode = Some("live".into());
    backend.live_armed = Some(true);
    backend.execution_authority = Some("hyperliquid_mainnet".into());
    backend.cohort = BackendCohortTelemetry {
        enabled_symbols: strings(&["BTC", "HYPE", "xyz:SPCX"]),
        asset_configs: ["BTC", "HYPE", "xyz:SPCX"]
            .into_iter()
            .map(active_asset)
            .collect(),
        providers: active_providers(),
        maximum_concurrent_positions: 10,
        config_source_path: Some("configs/v57.toml".into()),
        runtime: Some(CohortRuntimeConfig {
            poll_seconds: 15.0,
            lookback_days: 14,
        }),
        ..BackendCohortTelemetry::default()
    };
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app.backend.cohort_checkpoint.configuration_generation = Some(staged_generation());
    app.active_tab = 8;
    app
}

fn active_asset(symbol: &str) -> CohortAssetConfig {
    CohortAssetConfig {
        symbol: symbol.into(),
        sides: strings(&["long", "short"]),
        leverage: 10.0,
        venue_max_leverage: 20.0,
        margin_fraction: 0.10,
        max_notional_usd: 5_000.0,
        entry_slippage_cap_fraction: None,
        market_slippage_cap_fraction: None,
        stop_bps: 80.0,
        maximum_hold_seconds: 86_400,
    }
}

fn active_providers() -> Vec<CohortProvider> {
    active_scopes()
        .into_iter()
        .map(|(strategy, symbols)| CohortProvider {
            strategy_id: strategy.into(),
            symbols: strings(symbols),
            sides: strings(&["long", "short"]),
            priority: 10,
            timeframe: "15m".into(),
            maximum_entry_delay_seconds: 60,
            execution_symbols: Some(strings(symbols)),
            execution_side_overrides: BTreeMap::new(),
            entry_context_overrides: BTreeMap::new(),
            sizing_overrides: BTreeMap::new(),
            source_profile: None,
            execution: None,
        })
        .collect()
}

fn active_scopes() -> [(&'static str, &'static [&'static str]); 5] {
    [
        ("hulk_expansion_short_robust_v3", &["BTC"]),
        ("hulk_expansion_short_tuned_v2", &["BTC"]),
        ("liquidity_sweep_long_1h_stop60_target60_v2", &["BTC"]),
        (
            "hype_breakout_compression_alignment_bidirectional_v2",
            &["HYPE"],
        ),
        (
            "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1",
            &["xyz:SPCX"],
        ),
    ]
}

fn staged_generation() -> CohortConfigurationGeneration {
    CohortConfigurationGeneration {
        state: "stale_runtime_configuration".into(),
        matches_runtime: false,
        runtime_profile_fingerprint: V57.into(),
        current_profile_fingerprint: V58.into(),
        source_path: "configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml"
            .into(),
        source_modified_at_utc: "2026-08-18T23:15:00+00:00".into(),
        current_provider_execution_scopes: Some(v58_scopes()),
        current_provider_execution_directions: Some(v58_directions()),
        current_asset_sizing: Some(v58_sizing()),
        current_asset_entry_slippage_caps: None,
        current_asset_market_slippage_caps: None,
        current_entry_context_overrides: Some(BTreeMap::new()),
        current_provider_sizing_overrides: Some(BTreeMap::new()),
        current_provider_directional_sizing_overrides: Some(BTreeMap::new()),
        current_provider_exit_policies: Some(v58_exit_policies()),
        current_provider_directional_exit_policies: None,
        restart_state: "wait_for_flat_and_no_orders".into(),
        blocking_assets: Vec::new(),
        execution_authority: "none".into(),
        automatic_restart: false,
    }
}

fn v58_scopes() -> BTreeMap<String, Vec<String>> {
    BTreeMap::from([
        ("hulk_expansion_short_robust_v3".into(), strings(&["BTC"])),
        ("hulk_expansion_short_tuned_v2".into(), strings(&["BTC"])),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2".into(),
            strings(&["BTC"]),
        ),
        (
            "eth_breakout_precompression_pullback_bidirectional_v1".into(),
            strings(&["ETH"]),
        ),
        (
            "hulk_expansion_bidirectional_tuned_v2".into(),
            strings(&["SOL"]),
        ),
        (
            "hype_breakout_compression_alignment_bidirectional_v2".into(),
            strings(&["HYPE"]),
        ),
        (INDEX.into(), strings(&["xyz:SP500"])),
        (
            "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1".into(),
            strings(&["xyz:SPCX"]),
        ),
        (COMMODITY.into(), strings(&["xyz:SNDK", "xyz:BRENTOIL"])),
    ])
}

fn v58_directions() -> BTreeMap<String, Vec<String>> {
    BTreeMap::from([
        (
            "hulk_expansion_short_robust_v3|BTC".into(),
            strings(&["short"]),
        ),
        (
            "hulk_expansion_short_tuned_v2|BTC".into(),
            strings(&["short"]),
        ),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2|BTC".into(),
            strings(&["long"]),
        ),
        (
            "eth_breakout_precompression_pullback_bidirectional_v1|ETH".into(),
            strings(&["long", "short"]),
        ),
        (
            "hulk_expansion_bidirectional_tuned_v2|SOL".into(),
            strings(&["short"]),
        ),
        (
            "hype_breakout_compression_alignment_bidirectional_v2|HYPE".into(),
            strings(&["long", "short"]),
        ),
        (format!("{INDEX}|xyz:SP500"), strings(&["long", "short"])),
        (
            "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX".into(),
            strings(&["short"]),
        ),
        (format!("{COMMODITY}|xyz:SNDK"), strings(&["short"])),
        (
            format!("{COMMODITY}|xyz:BRENTOIL"),
            strings(&["long", "short"]),
        ),
    ])
}

fn v58_sizing() -> BTreeMap<String, CohortPendingAssetSizing> {
    BTreeMap::from([
        ("BTC".into(), sizing(10.0, 0.10, 5_000.0)),
        ("ETH".into(), sizing(5.0, 0.03, 750.0)),
        ("SOL".into(), sizing(5.0, 0.03, 750.0)),
        ("HYPE".into(), sizing(10.0, 0.10, 5_000.0)),
        ("xyz:SP500".into(), sizing(5.0, 0.07, 1_750.0)),
        ("xyz:SPCX".into(), sizing(5.0, 0.07, 1_750.0)),
        ("xyz:SNDK".into(), sizing(5.0, 0.03, 750.0)),
        ("xyz:BRENTOIL".into(), sizing(5.0, 0.03, 750.0)),
    ])
}

fn sizing(leverage: f64, margin: f64, cap: f64) -> CohortPendingAssetSizing {
    CohortPendingAssetSizing {
        leverage,
        margin_fraction: margin,
        max_notional_usd: cap,
    }
}

fn v58_exit_policies() -> BTreeMap<String, CohortPendingExitPolicy> {
    BTreeMap::from([(
        INDEX.into(),
        CohortPendingExitPolicy {
            maximum_hold_seconds: 86_400,
            maximum_hold_policy: "fixed".into(),
            hard_maximum_hold_seconds: None,
            maximum_hold_evidence_maximum_age_seconds: None,
            provider_recipe_exit_policy: "ignore".into(),
            profit_lock_policy: "completed_bar_trailing".into(),
            profit_lock_activation_bps: Some(100.0),
            profit_lock_floor_bps: Some(40.0),
            profit_lock_giveback_bps: Some(80.0),
        },
    )])
}

fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).into()).collect()
}

fn render(app: &App) -> String {
    let mut terminal = Terminal::new(TestBackend::new(160, 50)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw v58 transition");
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
