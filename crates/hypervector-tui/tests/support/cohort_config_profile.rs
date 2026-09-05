fn config_app() -> App {
    let assets = ["BTC", "ETH", "SOL", "HYPE"]
        .into_iter()
        .map(|symbol| CohortAssetConfig {
            symbol: symbol.into(),
            sides: vec!["long".into(), "short".into()],
            leverage: 5.0,
            venue_max_leverage: 20.0,
            margin_fraction: 0.03,
            max_notional_usd: 25.0,
            entry_slippage_cap_fraction: None,
            market_slippage_cap_fraction: None,
            stop_bps: 80.0,
            maximum_hold_seconds: 28_800,
        })
        .collect();
    let providers = vec![CohortProvider {
        strategy_id: "range_onset_bidirectional_v1".into(),
        symbols: vec!["BTC".into(), "ETH".into()],
        sides: vec!["long".into(), "short".into()],
        priority: 10,
        timeframe: "1m".into(),
        maximum_entry_delay_seconds: 60,
        execution_symbols: Some(vec!["BTC".into(), "ETH".into()]),
        execution_side_overrides: [("ETH".into(), vec!["long".into()])].into_iter().collect(),
        entry_context_overrides: [("ETH".into(), "dual_mtf_not_opposed".into())]
            .into_iter()
            .collect(),
        sizing_overrides: Default::default(),
        source_profile: None,
        execution: None,
    }];
    let mut backend = BackendTelemetrySnapshot::disconnected("fixture");
    backend.run_id = Some("cohort-observer-test".into());
    backend.profile_fingerprint = Some("a".repeat(64));
    backend.strategy_name = Some("multi_asset_bidirectional_cohort".into());
    backend.execution_mode = Some("observe".into());
    backend.live_armed = Some(false);
    backend.execution_authority = Some("none".into());
    backend.cohort = BackendCohortTelemetry {
        enabled_symbols: vec!["BTC".into(), "ETH".into(), "SOL".into(), "HYPE".into()],
        asset_configs: assets,
        providers,
        maximum_concurrent_positions: 4,
        config_source_path: Some("configs/multi_asset_bidirectional_canary.toml".into()),
        runtime: Some(CohortRuntimeConfig {
            poll_seconds: 5.0,
            lookback_days: 10,
        }),
        ..BackendCohortTelemetry::default()
    };
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app
}

fn v35_providers(template: &CohortProvider) -> Vec<CohortProvider> {
    let effective_scopes = BTreeMap::from([
        (
            "hulk_expansion_bidirectional_tuned_v2",
            vec!["BTC", "ETH", "SOL", "HYPE"],
        ),
        (
            "range_onset_bidirectional_v1",
            vec!["BTC", "ETH", "SOL", "HYPE"],
        ),
        (
            "hypervelocity_source_follow_bidirectional_5m_v1",
            vec!["BTC"],
        ),
        (
            "hype_breakout_onset_bidirectional_v1",
            vec!["BTC", "ETH", "SOL", "HYPE"],
        ),
        (
            "eth_breakout_precompression_pullback_bidirectional_v1",
            vec!["ETH"],
        ),
        (
            "hip3_swing_ha_sp500_spcx_bidirectional_v2",
            vec!["xyz:SP500", "xyz:SPCX"],
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
            vec!["xyz:SP500", "xyz:SPCX"],
        ),
        (
            "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
            vec!["xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL"],
        ),
        (
            "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1",
            vec!["xyz:SNDK", "xyz:GOLD", "xyz:BRENTOIL"],
        ),
    ]);
    effective_scopes
        .iter()
        .map(|(strategy_id, symbols)| {
            let mut provider = template.clone();
            provider.strategy_id = (*strategy_id).into();
            provider.symbols = symbols.iter().map(|symbol| (*symbol).into()).collect();
            provider.execution_symbols = Some(provider.symbols.clone());
            provider
        })
        .collect()
}

#[test]
fn stages_a_complete_restart_only_profile_from_the_config_editor() {
    let temporary = tempdir().expect("tempdir");
    fs::create_dir(temporary.path().join("pending")).expect("pending");
    let mut app = config_app();
    app.set_cohort_command_inbox(Some(temporary.path().to_path_buf()));

    app.adjust_cohort_config(-1.0);
    app.select_next_cohort_config();
    app.adjust_cohort_config(1.0);
    for _ in 0..8 {
        app.select_next_cohort_config();
    }
    app.activate_cohort_config_row();

    let request_path = fs::read_dir(temporary.path().join("pending"))
        .expect("pending")
        .next()
        .expect("request")
        .expect("entry")
        .path();
    let request: Value =
        serde_json::from_str(&fs::read_to_string(request_path).expect("request content"))
            .expect("request json");
    assert_eq!(request["action"], "stage_profile");
    assert_eq!(request["symbol"], "MULTI");
    assert_eq!(request["provider"], Value::Null);
    assert_eq!(request["side"], Value::Null);
    assert_eq!(request["settings"]["maximum_positions"], 4);
    assert_eq!(request["settings"]["poll_seconds"], 6.0);
    assert_eq!(request["settings"]["assets"].as_array().unwrap().len(), 4);
    assert_eq!(
        request["settings"]["providers"].as_array().unwrap().len(),
        1
    );
    assert!(app
        .cohort_notice
        .as_deref()
        .unwrap()
        .contains("STAGED PROFILE"));
}

#[test]
fn refuses_to_stage_profile_while_live_execution_is_armed() {
    let temporary = tempdir().expect("tempdir");
    fs::create_dir(temporary.path().join("pending")).expect("pending");
    let mut app = config_app();
    app.backend.live_armed = Some(true);
    app.backend.execution_authority = Some("hyperliquid_mainnet".into());
    app.set_cohort_command_inbox(Some(temporary.path().to_path_buf()));
    for _ in 0..9 {
        app.select_next_cohort_config();
    }

    app.activate_cohort_config_row();

    assert!(fs::read_dir(temporary.path().join("pending"))
        .expect("pending")
        .next()
        .is_none());
    assert!(app.cohort_notice.as_deref().unwrap().contains("DISARM"));
}

#[test]
fn toggles_only_the_selected_provider_and_coin_scope() {
    let mut app = config_app();
    for _ in 0..7 {
        app.select_next_cohort_config();
    }

    app.activate_cohort_config_row();

    let summary = app.cohort_config_scope_summary().expect("scope summary");
    assert_eq!(summary, "RANGE ONSET // BTC // OBSERVE ONLY");
}

#[test]
fn renders_direction_specific_effective_execution_scope() {
    let mut app = config_app();
    app.active_tab = 8;
    app.move_cohort_symbol(1);
    let mut terminal = Terminal::new(TestBackend::new(165, 46)).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw config");

    let buffer = terminal.backend().buffer();
    let screen = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    assert!(screen.contains("EXECUTE LONG ONLY"), "{screen}");
    assert!(screen.contains("DUAL-MTF NOT OPPOSED"), "{screen}");
}

#[test]
fn renders_running_and_staged_entry_context_as_distinct_values() {
    let mut app = config_app();
    app.active_tab = 8;
    app.move_cohort_symbol(1);
    app.backend.cohort.providers[0]
        .entry_context_overrides
        .clear();
    app.backend.cohort_checkpoint = CohortCheckpointTelemetry {
        configured: true,
        available: true,
        configuration_generation: Some(CohortConfigurationGeneration {
            state: "stale_runtime_configuration".into(),
            matches_runtime: false,
            runtime_profile_fingerprint: "runtime-profile".into(),
            current_profile_fingerprint: "current-profile".into(),
            source_path: "configs/multi_asset_bidirectional_canary.toml".into(),
            source_modified_at_utc: "2026-08-03T11:16:04+00:00".into(),
            current_provider_execution_scopes: None,
            current_provider_execution_directions: None,
            current_asset_sizing: None,
            current_asset_entry_slippage_caps: None,
            current_asset_market_slippage_caps: None,
            current_entry_context_overrides: Some(
                [(
                    "range_onset_bidirectional_v1|ETH".into(),
                    "dual_mtf_not_opposed".into(),
                )]
                .into_iter()
                .collect(),
            ),
            current_provider_sizing_overrides: Some(BTreeMap::new()),
            current_provider_directional_sizing_overrides: None,
            current_provider_exit_policies: None,
            current_provider_directional_exit_policies: None,
            restart_state: "wait_for_flat_and_no_orders".into(),
            blocking_assets: vec!["HYPE".into()],
            execution_authority: "none".into(),
            automatic_restart: false,
        }),
        ..CohortCheckpointTelemetry::default()
    };
    let mut terminal = Terminal::new(TestBackend::new(165, 46)).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw config");

    let buffer = terminal.backend().buffer();
    let screen = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    let row = screen
        .lines()
        .find(|line| line.contains("ENTRY CONTEXT"))
        .expect("entry context row");
    assert!(row.contains("SOURCE CONTRACT"), "{row}");
    assert!(row.contains("DUAL-MTF NOT OPPOSED"), "{row}");
}

#[test]
fn renders_the_external_next_flat_profile_and_restart_blockers() {
    let mut app = config_app();
    app.active_tab = 8;
    app.backend.cohort_checkpoint.configuration_generation = Some(CohortConfigurationGeneration {
        state: "stale_runtime_configuration".into(),
        matches_runtime: false,
        runtime_profile_fingerprint: "runtime-profile".into(),
        current_profile_fingerprint: "next-profile".into(),
        source_path: "configs/multi_asset_bidirectional_range_retired_hype75_candidate.toml".into(),
        source_modified_at_utc: "2026-08-05T04:25:14+00:00".into(),
        current_provider_execution_scopes: None,
        current_provider_execution_directions: None,
        current_asset_sizing: Some(BTreeMap::from([
            ("BTC".into(), pending_asset(25.0)),
            ("ETH".into(), pending_asset(25.0)),
            ("HYPE".into(), pending_asset(75.0)),
            ("SOL".into(), pending_asset(75.0)),
        ])),
        current_asset_entry_slippage_caps: None,
        current_asset_market_slippage_caps: None,
        current_entry_context_overrides: Some(BTreeMap::new()),
        current_provider_sizing_overrides: Some(BTreeMap::new()),
        current_provider_directional_sizing_overrides: None,
        current_provider_exit_policies: Some(BTreeMap::from([(
            "hype_breakout_onset_bidirectional_v1".into(),
            CohortPendingExitPolicy {
                maximum_hold_seconds: 28_800,
                maximum_hold_policy: "extend_while_regime_supported".into(),
                hard_maximum_hold_seconds: Some(86_400),
                maximum_hold_evidence_maximum_age_seconds: None,
                provider_recipe_exit_policy: "ignore".into(),
                profit_lock_policy: "none".into(),
                profit_lock_activation_bps: None,
                profit_lock_floor_bps: None,
                profit_lock_giveback_bps: None,
            },
        )])),
        current_provider_directional_exit_policies: None,
        restart_state: "wait_for_flat_and_no_orders".into(),
        blocking_assets: vec!["BTC".into(), "HYPE".into()],
        execution_authority: "none".into(),
        automatic_restart: false,
    });
    let mut terminal = Terminal::new(TestBackend::new(190, 52)).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw config");

    let buffer = terminal.backend().buffer();
    let screen = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    assert!(screen.contains("PENDING RESTART PROFILE"), "{screen}");
    assert!(
        screen.contains("PENDING PROFILE EXIT HT-Breakout"),
        "{screen}"
    );
    assert!(screen.contains("RECIPE EXIT IGNORE"), "{screen}");
    assert!(screen.contains("PROFIT LOCK OFF"), "{screen}");
    assert!(
        screen.contains("multi_asset_bidirectional_range_retired_hype75_candidate.toml"),
        "{screen}"
    );
    assert!(screen.contains("BLOCKED BY BTC,HYPE"), "{screen}");
    assert!(screen.contains("WAIT FOR FLAT + NO ORDERS"), "{screen}");
    assert!(screen.contains("AUTO RESTART NO"), "{screen}");
    assert!(
        screen.contains("NEXT TIERS 5.0x/3.00%/$75 HYPE,SOL | 5.0x/3.00%/$25 BTC,ETH"),
        "{screen}"
    );
    assert!(
        screen.contains("PENDING PROFILE EXIT HT-Breakout // REGIME EXTEND 8H → HARD 24H"),
        "{screen}"
    );
}

#[test]
fn renders_effective_v35_against_exact_staged_v36_route_removals() {
    let mut app = config_app();
    app.active_tab = 8;
    let template = app.backend.cohort.providers[0].clone();
    app.backend.cohort.providers = v35_providers(&template);
    app.backend.cohort_checkpoint.configuration_generation = Some(CohortConfigurationGeneration {
        state: "stale_runtime_configuration".into(),
        matches_runtime: false,
        runtime_profile_fingerprint: "8acc70105f8254dc6a7a3f690cebbaec8".into(),
        current_profile_fingerprint: "e472701ef9c386de7b68afcf28679f940".into(),
        source_path: "configs/multi_asset_bidirectional_evidence_roster_canary_v36.toml".into(),
        source_modified_at_utc: "2026-08-10T18:00:00+00:00".into(),
        current_provider_execution_scopes: Some(BTreeMap::from([
            (
                "hulk_expansion_bidirectional_tuned_v2".into(),
                vec!["BTC".into(), "ETH".into(), "HYPE".into(), "SOL".into()],
            ),
            ("range_onset_bidirectional_v1".into(), vec!["SOL".into()]),
            (
                "hypervelocity_source_follow_bidirectional_5m_v1".into(),
                vec!["BTC".into()],
            ),
            (
                "hype_breakout_onset_bidirectional_v1".into(),
                vec!["BTC".into(), "ETH".into(), "HYPE".into(), "SOL".into()],
            ),
            (
                "eth_breakout_precompression_pullback_bidirectional_v1".into(),
                vec!["ETH".into()],
            ),
            (
                "hip3_breakout_pressure_sp500_spcx_bidirectional_v1".into(),
                vec!["xyz:SP500".into(), "xyz:SPCX".into()],
            ),
            (
                "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1".into(),
                vec!["xyz:BRENTOIL".into(), "xyz:GOLD".into(), "xyz:SNDK".into()],
            ),
        ])),
        current_provider_execution_directions: None,
        current_asset_sizing: None,
        current_asset_entry_slippage_caps: None,
        current_asset_market_slippage_caps: None,
        current_entry_context_overrides: Some(BTreeMap::new()),
        current_provider_sizing_overrides: Some(BTreeMap::new()),
        current_provider_directional_sizing_overrides: None,
        current_provider_exit_policies: None,
        current_provider_directional_exit_policies: None,
        restart_state: "wait_for_flat_and_no_orders".into(),
        blocking_assets: vec!["xyz:GOLD".into()],
        execution_authority: "none".into(),
        automatic_restart: false,
    });
    let mut terminal = Terminal::new(TestBackend::new(220, 58)).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw config");

    let buffer = terminal.backend().buffer();
    let screen = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    assert!(
        screen.contains(
            "NEXT ASSETS 9 // ROUTES EFFECTIVE 24 // NEXT 16 // SIDE SCOPES 32 // REMOVE 8 // ADD 0"
        ),
        "{screen}"
    );
    assert!(screen.contains("RANGE ONSET"), "{screen}");
    assert!(screen.contains("REMOVE BTC/ETH/HYPE"), "{screen}");
    assert!(screen.contains("HIP3 SWING IDX"), "{screen}");
    assert!(screen.contains("REMOVE xyz:SP500/xyz:SPCX"), "{screen}");
    assert!(screen.contains("HIP3 SWING CMD"), "{screen}");
    assert!(
        screen.contains("REMOVE xyz:BRENTOIL/xyz:GOLD/xyz:SNDK"),
        "{screen}"
    );
    assert!(screen.contains("BLOCKED BY xyz:GOLD"), "{screen}");
    assert!(
        screen.contains("LIVE ARMING IS CLI-ONLY AND STILL REQUIRES BOTH EXPLICIT RISK FLAGS"),
        "{screen}"
    );

    app.selected_cohort_provider_index = app
        .backend
        .cohort
        .providers
        .iter()
        .position(|provider| provider.strategy_id == "hip3_swing_ha_sp500_spcx_bidirectional_v2")
        .expect("removed provider");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw removed provider");
    let buffer = terminal.backend().buffer();
    let screen = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    let scope_row = screen
        .lines()
        .find(|line| line.contains("PROVIDER / COIN SCOPE"))
        .expect("scope row");
    assert!(scope_row.contains("PROVIDER REMOVED"), "{scope_row}");
}
