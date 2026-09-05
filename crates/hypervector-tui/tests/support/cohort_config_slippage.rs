#[test]
fn renders_distinct_entry_and_close_ioc_caps() {
    let mut app = config_app();
    app.active_tab = 8;
    app.backend.cohort.asset_configs[0].entry_slippage_cap_fraction = Some(0.002);
    app.backend.cohort.asset_configs[0].market_slippage_cap_fraction = Some(0.01);
    app.backend.cohort_checkpoint.configuration_generation = Some(ioc_generation(
        Some(0.002),
        0.01,
    ));
    let screen = render_ioc_config(&app);
    assert!(
        screen.contains(
            "NEXT-RUN IOC CAPS BTC ENTRY 20.0bps // CLOSE 100.0bps // CURRENT // EFFECTIVE ENTRY 20.0bps / CLOSE 100.0bps"
        ),
        "{screen}"
    );
}

fn ioc_generation(entry_cap: Option<f64>, close_cap: f64) -> CohortConfigurationGeneration {
    CohortConfigurationGeneration {
        state: "current_runtime_configuration".into(),
        matches_runtime: true,
        runtime_profile_fingerprint: "runtime-profile".into(),
        current_profile_fingerprint: "runtime-profile".into(),
        source_path: "configs/v80.toml".into(),
        source_modified_at_utc: "2026-09-03T04:00:00+00:00".into(),
        current_provider_execution_scopes: None,
        current_provider_execution_directions: None,
        current_asset_sizing: None,
        current_asset_entry_slippage_caps: entry_cap
            .map(|cap| BTreeMap::from([("BTC".into(), cap)])),
        current_asset_market_slippage_caps: Some(BTreeMap::from([(
            "BTC".into(),
            close_cap,
        )])),
        current_entry_context_overrides: Some(BTreeMap::new()),
        current_provider_sizing_overrides: Some(BTreeMap::new()),
        current_provider_directional_sizing_overrides: None,
        current_provider_exit_policies: None,
        current_provider_directional_exit_policies: None,
        restart_state: "not_required_current_configuration".into(),
        blocking_assets: vec![],
        execution_authority: "none".into(),
        automatic_restart: false,
    }
}

#[test]
fn legacy_generation_falls_back_to_shared_ioc_cap() {
    let mut app = config_app();
    app.active_tab = 8;
    app.backend.cohort.asset_configs[0].entry_slippage_cap_fraction = None;
    app.backend.cohort.asset_configs[0].market_slippage_cap_fraction = Some(0.002);
    app.backend.cohort_checkpoint.configuration_generation = Some(ioc_generation(None, 0.002));

    let screen = render_ioc_config(&app);

    assert!(
        screen.contains(
            "NEXT-RUN IOC CAPS BTC ENTRY 20.0bps // CLOSE 20.0bps // CURRENT // EFFECTIVE ENTRY 20.0bps / CLOSE 20.0bps"
        ),
        "{screen}"
    );
}

fn render_ioc_config(app: &App) -> String {
    let mut terminal = Terminal::new(TestBackend::new(180, 52)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("draw config");
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
