#[test]
fn renders_identity_bound_growth_sizing_and_selected_asset_friction() {
    let mut app = config_app();
    app.active_tab = 8;
    app.backend.cohort_checkpoint.configuration_generation = Some(CohortConfigurationGeneration {
        state: "stale_runtime_configuration".into(),
        matches_runtime: false,
        runtime_profile_fingerprint: "runtime-profile".into(),
        current_profile_fingerprint: "b".repeat(64),
        source_path: "configs/multi_asset_bidirectional_growth_5000_candidate_v37.toml".into(),
        source_modified_at_utc: "2026-08-10T22:00:00+00:00".into(),
        current_provider_execution_scopes: None,
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
    app.backend.growth_preflight = GrowthPreflightTelemetry {
        configured: true,
        available: true,
        candidate_profile_id: Some("multi_asset_bidirectional_growth_5000_candidate_v37".into()),
        candidate_profile_fingerprint: Some("b".repeat(64)),
        sizing_reference_equity_usd: Some(5_000.0),
        maximum_positions: Some(10),
        maximum_configured_margin_fraction: Some(0.24),
        open_positions: Some(1),
        open_orders: Some(1),
        ledger_reconciled: Some(true),
        sizing_technically_ready: Some(true),
        technically_ready_for_profile_transition: Some(false),
        transition_blocking_assets: vec!["xyz:GOLD".into()],
        readiness_reasons: vec!["venue is not flat with no open orders".into()],
        assets: vec![GrowthPreflightAssetTelemetry {
            symbol: "BTC".into(),
            effective_fee_status: "resolved_account_base".into(),
            one_way_taker_fee_bps: Some(4.5),
            margin_fraction: 0.03,
            leverage: 5.0,
            planned_margin_usd: 150.0,
            planned_notional_usd: 750.0,
            above_minimum_lot: true,
            buy_complete: true,
            buy_visible_cost_bps: Some(0.2),
            sell_complete: true,
            sell_visible_cost_bps: Some(0.3),
            sizing_technically_ready: true,
        }],
        retired_assets: vec![GrowthPreflightRetiredAssetTelemetry {
            symbol: "ETH".into(),
            flat_no_orders: true,
            ledger_reconciled: true,
        }],
        ..GrowthPreflightTelemetry::default()
    };
    let mut terminal = Terminal::new(TestBackend::new(220, 62)).expect("terminal");

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
    assert!(screen.contains("$5K PREFLIGHT BLOCKED"), "{screen}");
    assert!(screen.contains("PENDING RESTART PROFILE V37"), "{screen}");
    assert!(screen.contains("10 SLOTS // MAX MARGIN 24.0%"), "{screen}");
    assert!(
        screen.contains("BTC 3.0% @ 5.0x // $150.00 → $750.00"),
        "{screen}"
    );
    assert!(
        screen.contains("FEE 4.50bps // L2 BUY 0.20 / SELL 0.30bps"),
        "{screen}"
    );

    app.selected_cohort_symbol_index = app
        .backend
        .cohort
        .asset_configs
        .iter()
        .position(|asset| asset.symbol == "ETH")
        .expect("asset absent from candidate sizing evidence");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw retiring asset");
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
        screen.contains("RETIRED ASSET ETH // FLAT + NO ORDERS // LEDGER RECONCILED"),
        "{screen}"
    );
}

#[test]
fn non_staged_scope_matrix_reports_bounded_overflow_and_pins_safety() {
    let seed = config_app();
    let mut backend = seed.backend.clone();
    backend.cohort.providers = v35_providers(&backend.cohort.providers[0]);
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app.active_tab = 8;

    for (width, height) in [(120, 36), (180, 50)] {
        let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
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
            screen.contains("CONTENT WINDOW"),
            "{width}x{height}\n{screen}"
        );
        assert!(
            screen.contains("LINES OMITTED"),
            "{width}x{height}\n{screen}"
        );
        assert!(
            screen.contains("LIVE ARMING IS CLI-ONLY"),
            "{width}x{height}\n{screen}"
        );
    }
}

fn pending_asset(max_notional_usd: f64) -> CohortPendingAssetSizing {
    CohortPendingAssetSizing {
        leverage: 5.0,
        margin_fraction: 0.03,
        max_notional_usd,
    }
}

#[test]
fn renders_report_only_effective_sizing_for_the_selected_asset() {
    let mut app = config_app();
    app.active_tab = 8;
    app.move_cohort_symbol(1);
    app.backend.cohort_checkpoint.risk_utilization = Some(CohortRiskUtilization {
        account_value_usd: 500.0,
        configured_assets: 1,
        cap_bound_assets: 1,
        configured_maximum_positions: 1,
        provider_symbols: 1,
        provider_symbol_overrides: 1,
        maximum_effective_margin_fraction: 0.01,
        by_asset: BTreeMap::from([(
            "ETH".into(),
            CohortAssetRiskUtilization {
                configured_leverage: 5.0,
                configured_margin_fraction: 0.03,
                configured_max_notional_usd: 25.0,
                uncapped_notional_usd: 75.0,
                planned_notional_usd: 25.0,
                planned_margin_usd: 5.0,
                effective_margin_fraction: 0.01,
                notional_fraction_of_equity: 0.05,
                cap_utilization_ratio: 1.0 / 3.0,
                cap_binding: true,
            },
        )]),
        by_provider_symbol: BTreeMap::from([(
            "range_onset_bidirectional_v1|ETH".into(),
            CohortProviderRiskUtilization {
                sizing: CohortAssetRiskUtilization {
                    configured_leverage: 5.0,
                    configured_margin_fraction: 0.06,
                    configured_max_notional_usd: 20.0,
                    uncapped_notional_usd: 150.0,
                    planned_notional_usd: 20.0,
                    planned_margin_usd: 4.0,
                    effective_margin_fraction: 0.008,
                    notional_fraction_of_equity: 0.04,
                    cap_utilization_ratio: 2.0 / 15.0,
                    cap_binding: true,
                },
                sizing_source: "provider_override".into(),
            },
        )]),
    });
    app.backend.cohort_checkpoint.configuration_generation = Some(CohortConfigurationGeneration {
        state: "stale_runtime_configuration".into(),
        matches_runtime: false,
        runtime_profile_fingerprint: "runtime-profile".into(),
        current_profile_fingerprint: "current-profile".into(),
        source_path: "configs/multi_asset_bidirectional_canary.toml".into(),
        source_modified_at_utc: "2026-08-04T01:30:00+00:00".into(),
        current_provider_execution_scopes: None,
        current_provider_execution_directions: None,
        current_asset_sizing: None,
        current_asset_entry_slippage_caps: None,
        current_asset_market_slippage_caps: None,
        current_entry_context_overrides: Some(BTreeMap::new()),
        current_provider_sizing_overrides: Some(BTreeMap::from([(
            "range_onset_bidirectional_v1|ETH".into(),
            CohortProviderSizing {
                margin_fraction: 0.10,
                max_notional_usd: 25.0,
            },
        )])),
        current_provider_directional_sizing_overrides: Some(BTreeMap::from([
            (
                "range_onset_bidirectional_v1|ETH|long".into(),
                CohortProviderSizing {
                    margin_fraction: 0.03,
                    max_notional_usd: 60.0,
                },
            ),
            (
                "range_onset_bidirectional_v1|ETH|short".into(),
                CohortProviderSizing {
                    margin_fraction: 0.03,
                    max_notional_usd: 15.0,
                },
            ),
        ])),
        current_provider_exit_policies: None,
        current_provider_directional_exit_policies: None,
        restart_state: "wait_for_flat_and_no_orders".into(),
        blocking_assets: vec!["HYPE".into()],
        execution_authority: "none".into(),
        automatic_restart: false,
    });
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
    assert!(
        screen.contains("LIVE SIZING ETH  CAP BOUND / PROVIDER OVERRIDE"),
        "{screen}"
    );
    assert!(
        screen.contains("CONFIG 6.00% -> EFFECTIVE 0.80%"),
        "{screen}"
    );
    assert!(
        screen.contains("REQUEST $150.00 -> PLAN $20.00"),
        "{screen}"
    );
    assert!(screen.contains("REPORT ONLY"), "{screen}");
    assert!(
        screen.contains("NEXT-RUN SIZING ETH  LONG 3.00%/$60.00 // SHORT 3.00%/$15.00"),
        "{screen}"
    );
    assert!(screen.contains("RESTART REQUIRED"), "{screen}");
}

#[test]
fn renders_verified_prestart_backup_provenance() {
    let mut app = config_app();
    app.active_tab = 8;
    app.backend.cohort.prestart_backup = Some(CohortPrestartBackupEvidence {
        status: "verified".into(),
        bundle_path: "data/backups/bidirectional_cohort/prestart_test".into(),
        manifest_path: "data/backups/bidirectional_cohort/prestart_test/manifest.json".into(),
        manifest_sha256: "a".repeat(64),
        strategy_changed: true,
        implementation_file_count: 1_156,
        implementation_sha256: "b".repeat(64),
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
    assert!(screen.contains("PRESTART VERIFIED"), "{screen}");
    assert!(screen.contains("MFT aaaaaaaaaaaa"), "{screen}");
    assert!(screen.contains("SRC 1156 / bbbbbbbbbbbb"), "{screen}");
}
