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

const COMPRESSION: &str = "hype_breakout_compression_alignment_bidirectional_v2";
const NATIVE: &str = "hype_native_breakout_onset_bidirectional_v2";

#[test]
fn staged_v54_exposes_native_hype_scope_sizing_and_exit() {
    let screen = render(&staged_app());

    assert!(
        screen.contains("NEXT ASSETS 2 // ROUTES EFFECTIVE 3 // NEXT 3"),
        "{screen}"
    );
    assert!(
        screen.contains("SIDE SCOPES 4 // REMOVE 1 // ADD 1"),
        "{screen}"
    );
    assert!(screen.contains("HYPE NATIVE"), "{screen}");
    assert!(screen.contains("HYPE ALIGN"), "{screen}");
    assert!(
        screen.contains("NEXT TIERS 10.0x/10.00%/$5000 BTC | 5.0x/5.00%/$1250 HYPE"),
        "{screen}"
    );
    assert!(screen.contains("FIXED 8H"), "{screen}");
    assert!(!screen.contains("REGIME EXTEND 8H"), "{screen}");
    assert!(!screen.contains("HARD 24H / EVIDENCE"), "{screen}");
    assert!(screen.contains("PROFIT LOCK OFF"), "{screen}");
    assert!(screen.contains("LIVE ARMING IS CLI-ONLY"), "{screen}");
}

fn staged_app() -> App {
    let mut backend = BackendTelemetrySnapshot::disconnected("fixture");
    backend.run_id = Some("bidirectional-live-v53".into());
    backend.profile_fingerprint = Some("v53".into());
    backend.strategy_name = Some("multi_asset_bidirectional_cohort".into());
    backend.execution_mode = Some("live".into());
    backend.live_armed = Some(true);
    backend.execution_authority = Some("hyperliquid_mainnet".into());
    backend.cohort = active_cohort();
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app.backend.cohort_checkpoint.configuration_generation = Some(staged_generation());
    app.active_tab = 8;
    app
}

fn active_cohort() -> BackendCohortTelemetry {
    BackendCohortTelemetry {
        enabled_symbols: strings(&["BTC", "HYPE"]),
        asset_configs: vec![
            asset("BTC", 10.0, 0.10, 5_000.0),
            asset("HYPE", 10.0, 0.10, 5_000.0),
        ],
        providers: active_providers(),
        maximum_concurrent_positions: 10,
        config_source_path: Some("configs/v53.toml".into()),
        runtime: Some(CohortRuntimeConfig {
            poll_seconds: 15.0,
            lookback_days: 14,
        }),
        ..BackendCohortTelemetry::default()
    }
}

fn active_providers() -> Vec<CohortProvider> {
    vec![
        provider("hulk_expansion_short_robust_v3", "BTC", &["short"]),
        provider(
            "liquidity_sweep_long_1h_stop60_target60_v2",
            "BTC",
            &["long"],
        ),
        provider(COMPRESSION, "HYPE", &["long", "short"]),
    ]
}

fn provider(strategy: &str, symbol: &str, sides: &[&str]) -> CohortProvider {
    CohortProvider {
        strategy_id: strategy.into(),
        symbols: strings(&[symbol]),
        sides: strings(sides),
        priority: 10,
        timeframe: "1m".into(),
        maximum_entry_delay_seconds: 60,
        execution_symbols: Some(strings(&[symbol])),
        execution_side_overrides: BTreeMap::new(),
        entry_context_overrides: BTreeMap::new(),
        sizing_overrides: BTreeMap::new(),
        source_profile: None,
        execution: None,
    }
}

fn asset(symbol: &str, leverage: f64, margin: f64, cap: f64) -> CohortAssetConfig {
    CohortAssetConfig {
        symbol: symbol.into(),
        sides: strings(&["long", "short"]),
        leverage,
        venue_max_leverage: 40.0,
        margin_fraction: margin,
        max_notional_usd: cap,
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
        runtime_profile_fingerprint: "v53".into(),
        current_profile_fingerprint: "v54".into(),
        source_path: "configs/v54-hype-native.toml".into(),
        source_modified_at_utc: "2026-08-18T00:00:00+00:00".into(),
        current_provider_execution_scopes: Some(staged_scopes()),
        current_provider_execution_directions: Some(staged_directions()),
        current_asset_sizing: Some(staged_sizing()),
        current_asset_entry_slippage_caps: None,
        current_asset_market_slippage_caps: None,
        current_entry_context_overrides: Some(BTreeMap::new()),
        current_provider_sizing_overrides: Some(BTreeMap::new()),
        current_provider_directional_sizing_overrides: Some(BTreeMap::new()),
        current_provider_exit_policies: Some(BTreeMap::from([(NATIVE.into(), native_exit())])),
        current_provider_directional_exit_policies: None,
        restart_state: "candidate_flat_no_orders".into(),
        blocking_assets: Vec::new(),
        execution_authority: "none".into(),
        automatic_restart: false,
    }
}

fn staged_scopes() -> BTreeMap<String, Vec<String>> {
    BTreeMap::from([
        ("hulk_expansion_short_robust_v3".into(), strings(&["BTC"])),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2".into(),
            strings(&["BTC"]),
        ),
        (NATIVE.into(), strings(&["HYPE"])),
    ])
}

fn staged_directions() -> BTreeMap<String, Vec<String>> {
    BTreeMap::from([
        (
            "hulk_expansion_short_robust_v3|BTC".into(),
            strings(&["short"]),
        ),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2|BTC".into(),
            strings(&["long"]),
        ),
        (format!("{NATIVE}|HYPE"), strings(&["long", "short"])),
    ])
}

fn staged_sizing() -> BTreeMap<String, CohortPendingAssetSizing> {
    BTreeMap::from([
        ("BTC".into(), pending_size(10.0, 0.10, 5_000.0)),
        ("HYPE".into(), pending_size(5.0, 0.05, 1_250.0)),
    ])
}

fn pending_size(leverage: f64, margin: f64, cap: f64) -> CohortPendingAssetSizing {
    CohortPendingAssetSizing {
        leverage,
        margin_fraction: margin,
        max_notional_usd: cap,
    }
}

fn native_exit() -> CohortPendingExitPolicy {
    CohortPendingExitPolicy {
        stop_risk_budget: None,
        maximum_hold_seconds: 28_800,
        maximum_hold_policy: "fixed".into(),
        hard_maximum_hold_seconds: None,
        maximum_hold_evidence_maximum_age_seconds: None,
        provider_recipe_exit_policy: "ignore".into(),
        adaptive_exit_policy: "none".into(),
        profit_lock_policy: "none".into(),
        profit_lock_activation_bps: None,
        profit_lock_floor_bps: None,
        profit_lock_giveback_bps: None,
    }
}

fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).into()).collect()
}

fn render(app: &App) -> String {
    let mut terminal = Terminal::new(TestBackend::new(160, 50)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw");
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
