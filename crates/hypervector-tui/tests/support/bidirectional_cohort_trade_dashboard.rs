#[test]
fn trades_screen_projects_per_strategy_history_and_latest_btc_detail() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = trade_checkpoint();

    let screen = render(&mut app, 4, 165, 46);
    for expected in [
        "ALL-TIME",
        "CURRENT RUN",
        "SCOPE",
        "EXIT DATE ET",
        "ENTRY PX",
        "EXIT PX",
        "NET USD",
        "AVG PNL/TRD",
        "RUN WINDOWS 2 +1/-1 NOT INDEPENDENT",
        "FEES",
        "FUNDING",
        "$64100.0000",
        "$63900.0000",
        "RUN",
        "HISTORY",
        "HULK EXPANSION",
        "HT-Breakout",
        "2",
        "1/1/0",
        "50.00%",
        "$-0.50",
        "-5.00%",
        "-3.25%",
        "PF",
        "0.32",
        "XPROV EXITS 1/2",
        "COMPLETED TRADES // RUN 1 // PROFILE PRIOR 0 // HISTORY 1 // ARCHIVE 2",
        "BTC",
        "PROTECTIVE STOP",
        "FILL GROSS",
        "[←/→] Focus journal",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    let current = screen.find("CURRENT RUN").expect("current run row");
    let all_time = screen.find("ALL-TIME").expect("mixed-history row");
    assert!(
        current < all_time,
        "the current process-run ledger must lead all-time history\n{screen}",
    );
    assert_eq!(
        screen.matches('▸').count(),
        1,
        "only the active journal may display a selection cursor\n{screen}",
    );

    app.show_cohort_fill_modal = true;
    let detail = render(&mut app, 4, 165, 46);
    for expected in [
        "CLOSED TRADE INSPECTOR",
        "BTC LONG",
        "HULK EXPANSION",
        "ENTRY $64100.00000000",
        "EXIT  $63900.00000000",
        "HOLD 0h 30m",
        "PRICE MOVE -0.31%",
        "NET/MARGIN -14.65%",
        "NET $-0.73",
        "FEES $0.03",
        "FUNDING $-0.0010",
        "ENTRY SIGNAL",
        "EXIT CANON",
        "ENTRY ASSESS",
        "STRUCT +0.75 DIRECTIONALLY SUPPORTED",
        "COMP +0.50 ALIGNED WITH POSITION",
        "STRENGTH 76.0%",
        "ENTRY TIMER STILL DIRECTIONALLY SUPPORTED",
        "OPPOSITION 126/150 DECISIONS",
        "MAX RUN 126",
        "AT EXIT ACTIVE",
        "PROVIDER EXIT IGNORED // POLICY IGNORE // SIGNALS 1",
        "FIRST SIGNAL HULK ALIGNMENT LOST @ $64020.00000000",
        "SIGNAL→ACTUAL GROSS -18.74bps // 10 BARS",
        "PATH MFE +45.00bps // MAE 28.00bps // GIVEBACK 63.74bps",
        "ACTUAL NET $-0.73 // FEES $0.03 // FUNDING $-0.0010",
        "COUNTERFACTUAL NET UNAVAILABLE // SIGNAL REFERENCE IS NOT A VENUE FILL",
    ] {
        assert!(detail.contains(expected), "missing {expected}\n{detail}");
    }

    app.show_cohort_fill_modal = false;
    app.move_cohort_trade_focus(1);
    app.toggle_cohort_fill_modal();
    let fill_detail = render(&mut app, 4, 165, 46);
    for expected in [
        "FILL INSPECTOR",
        "BTC Open Long",
        "TRADE ID 101",
        "SCOPE HISTORY",
    ] {
        assert!(
            fill_detail.contains(expected),
            "missing {expected}\n{fill_detail}",
        );
    }
}

#[test]
fn accounting_epoch_trade_screen_separates_fresh_display_from_preserved_history() {
    let mut app = cohort_app();
    app.backend.cohort.providers = v86_provider_fixture();
    let mut checkpoint = trade_checkpoint();
    checkpoint.trade_reflections.clear();
    checkpoint.all_time_trade_reflections.clear();
    if let Some(performance) = checkpoint.trade_performance.as_mut() {
        performance.total = CohortTradePerformanceSummary::default();
        performance.by_strategy.clear();
        performance.current_run = Some(CohortRunTradePerformance {
            run_id: "cohort-test".into(),
            total: CohortTradePerformanceSummary::default(),
            by_strategy: BTreeMap::new(),
        });
    }
    let preserved = CohortAllTimeTradePerformance {
        total: CohortTradePerformanceSummary {
            closed_trades: 123,
            wins: 50,
            losses: 73,
            net_pnl_usd: -316.779764,
            ..CohortTradePerformanceSummary::default()
        },
        ..CohortAllTimeTradePerformance::default()
    };
    checkpoint.portfolio_archive = Some(CohortPortfolioArchive {
        symbols: Vec::new(),
        observed_through_utc: Some("2026-09-03T19:05:00+00:00".into()),
        performance: CohortAllTimeTradePerformance::default(),
        accounting_epoch: Some(CohortAccountingEpoch {
            epoch_id: "v86_failed_routes_retired".into(),
            profile_fingerprint: "a".repeat(64),
            start_venue_timestamp_ms: 1_788_420_946_615,
            included_profile_fingerprints: Vec::new(),
        }),
        preserved_history: Some(CohortPreservedHistory {
            symbols: SYMBOLS.map(str::to_string).to_vec(),
            observed_through_utc: Some("2026-09-03T19:05:00+00:00".into()),
            performance: preserved,
        }),
    });
    app.backend.cohort_checkpoint = checkpoint;

    let screen = render(&mut app, 4, 176, 65);

    for expected in [
        "DISPLAY EPOCH",
        "9 MONITORED / 6 EXEC / 3 OBS",
        "0/0/0",
        "PRESERVED DATA",
        "123",
        "50/73/0",
        "$-316.78",
        "BACKEND HISTORY PRESERVED",
        "DISPLAY EPOCH 0/0 // PRESERVED BACKEND 50/73/0 (123 CLOSED)",
        "BTC HULK SHORT [O/N0]",
        "HULK EXPANSION [O/N0]",
        "ZEC DONCHIAN L [O/N0]",
        "BTC SWEEP 60/60 [E/N0]",
        "SNDK BK15 SHORT [E/N0]",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(!screen.contains("CLOSED PERFORMANCE: MIXED PROFILES"), "{screen}");
    assert!(!screen.contains("ALL-TIME"), "{screen}");
}

fn v86_provider_fixture() -> Vec<CohortProvider> {
    [
        ("hulk_expansion_short_robust_v3", "BTC", false),
        ("hulk_expansion_short_tuned_v2", "BTC", false),
        ("liquidity_sweep_long_1h_stop60_target60_v2", "BTC", true),
        ("eth_range_onset_long_dual_mtf_v2", "ETH", true),
        ("sol_range_onset_short_dual_mtf_v2", "SOL", true),
        ("hype_breakout_compression_alignment_bidirectional_v2", "HYPE", true),
        ("zec_donchian_20_10_atr20_long_v1", "ZEC", false),
        ("hip3_spcx_cash_session_fresh15_long_v4", "xyz:SPCX", true),
        (
            "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3",
            "xyz:SNDK",
            true,
        ),
    ]
    .into_iter()
    .map(|(strategy_id, symbol, executable)| CohortProvider {
        strategy_id: strategy_id.into(),
        symbols: vec![symbol.into()],
        sides: vec!["long".into(), "short".into()],
        priority: 10,
        timeframe: "1m".into(),
        maximum_entry_delay_seconds: 60,
        execution_symbols: Some(executable.then(|| symbol.into()).into_iter().collect()),
        execution_side_overrides: BTreeMap::new(),
        entry_context_overrides: BTreeMap::new(),
        sizing_overrides: BTreeMap::new(),
        source_profile: None,
        execution: None,
    })
    .collect()
}

#[test]
fn observer_dashboard_is_explicitly_disarmed() {
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(disarmed_cohort_backend());

    let screen = render(&mut app, 0, 120, 36);

    assert!(screen.contains("EXECUTION DISARMED"), "{screen}");
    assert!(!screen.contains("LIVE EXECUTION ARMED"), "{screen}");
}

#[test]
fn attached_monitor_states_that_quit_leaves_backend_running() {
    let mut app = cohort_app();
    app.detached_lifecycle = true;
    let asset_count = app.backend.cohort.enabled_symbols.len();

    let screen = render(&mut app, 0, 120, 36);

    assert!(screen.contains("BACKEND PERSISTS ON QUIT"), "{screen}");
    assert!(screen.contains("Quit leaves backend running"), "{screen}");
    assert!(
        screen.contains(&format!("All {asset_count} configured assets visible")),
        "{screen}",
    );
    assert!(!screen.contains("All nine assets visible"), "{screen}");
    assert!(!screen.contains("Lifecycle follows launcher"), "{screen}");
}

#[test]
fn dashboard_exposes_rolling_analysis_freshness_and_evidence_limits() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = CohortCheckpointTelemetry {
        configured: true,
        available: true,
        generated_at_utc: Some("2026-08-01T16:00:00+00:00".into()),
        lifecycle_state: Some("running_consistent".into()),
        cohort_heartbeat_status: Some("running".into()),
        coverage_complete: Some(true),
        readiness_evaluations: Some(8),
        closed_trades: Some(2),
        net_pnl_usd: Some(1.25),
        evidence_state: Some("descriptive_trade_evidence".into()),
        ..CohortCheckpointTelemetry::default()
    };

    let screen = render(&mut app, 0, 120, 36);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("120x36 ROLLING ANALYSIS\n{screen}");
    }

    for expected in [
        "ROLLING ANALYSIS // ARCHIVE EVIDENCE // READ-ONLY",
        "RUNNING CONSISTENT",
        "COVERAGE COMPLETE",
        "EVAL 8",
        "RUN 2C NET +$1.25",
        "NET +$1.25",
        "DESCRIPTIVE TRADE EVIDENCE",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

#[test]
fn dashboard_distinguishes_pending_update_from_backend_health() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = CohortCheckpointTelemetry {
        configured: true,
        available: true,
        generated_at_utc: Some("2026-08-03T15:26:00+00:00".into()),
        lifecycle_state: Some("running_consistent".into()),
        coverage_complete: Some(true),
        configuration_generation: Some(CohortConfigurationGeneration {
            state: "stale_runtime_configuration".into(),
            matches_runtime: false,
            runtime_profile_fingerprint: "12e4d47e94d11767".into(),
            current_profile_fingerprint: "0919ed27ccb60fa7".into(),
            source_path: "configs/multi_asset_bidirectional_canary.toml".into(),
            source_modified_at_utc: "2026-08-03T11:16:04+00:00".into(),
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
            blocking_assets: vec!["BTC".into()],
            execution_authority: "none".into(),
            automatic_restart: false,
        }),
        ..CohortCheckpointTelemetry::default()
    };

    let screen = render(&mut app, 0, 120, 36);

    assert!(screen.contains("STAGED UPDATE PENDING"), "{screen}");
    assert!(!screen.contains("STALE RUNTIME CONFIG"), "{screen}");
    assert!(screen.contains("RESTART WHEN FLAT"), "{screen}");
    assert!(screen.contains("WAIT BTC OPEN/ORDER"), "{screen}");
    assert!(
        screen.contains("RUN 12e4d47e94d1 != CFG 0919ed27ccb6"),
        "{screen}"
    );
    assert!(screen.contains("COVERAGE COMPLETE"), "{screen}");
}

#[test]
fn dashboard_labels_forward_observer_without_fake_trade_results() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = CohortCheckpointTelemetry {
        configured: true,
        available: true,
        analysis_mode: Some("forward_observer".into()),
        generated_at_utc: Some("2026-08-01T16:00:00+00:00".into()),
        lifecycle_state: Some("setup_process_observation".into()),
        coverage_complete: Some(true),
        readiness_evaluations: Some(18),
        strategy_intents: Some(1),
        forward_evaluations: Some(14),
        eligible_signals: Some(1),
        five_minute_paths_resolved: Some(13),
        five_minute_paths_independent: Some(5),
        forward_path_coverage_complete: Some(true),
        evidence_state: Some("setup_and_signal_paths_only_no_execution_outcomes".into()),
        ..CohortCheckpointTelemetry::default()
    };

    let screen = render(&mut app, 0, 120, 36);

    for expected in [
        "FORWARD OBSERVER",
        "COVERAGE COMPLETE",
        "FWD EVAL 14",
        "FIRE 1",
        "5M PATH 13/5 INDEP",
        "NO FILLS/PNL",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(!screen.contains("CLOSED 0"), "{screen}");
    assert!(!screen.contains("NET +$0.00"), "{screen}");
}

#[test]
fn observer_dashboard_projects_setup_and_path_journal() {
    let mut app = cohort_app();
    app.backend.live_armed = Some(false);
    app.backend.cohort_checkpoint = observer_checkpoint_with_journal();

    let screen = render(&mut app, 0, 120, 36);

    for expected in [
        "MARKET PULSE // SETUP PROXIMITY",
        "CAUSAL FORWARD PATH JOURNAL",
        "ANNOTATIONS, NOT FILLS OR PNL",
        "HULK EXPANSION",
        "RANGE ONSET",
        "HV SOURCE 5M",
        "HT-Breakout",
        "R9/I3 +4.2 67%",
        "R4/I1 -2.0 25%",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(!screen.contains("ACCOUNT RECONCILIATION"), "{screen}");
    assert!(!screen.contains("LIVE POSITIONS"), "{screen}");
    assert!(!screen.contains("EXACT FILL JOURNAL"), "{screen}");
}

fn observer_checkpoint_with_journal() -> CohortCheckpointTelemetry {
    let providers = [
        ("hulk_expansion_bidirectional_tuned_v2", "BTC"),
        ("hulk_expansion_bidirectional_tuned_v2", "ETH"),
        ("hulk_expansion_bidirectional_tuned_v2", "SOL"),
        ("hulk_expansion_bidirectional_tuned_v2", "HYPE"),
        ("range_onset_bidirectional_v1", "BTC"),
        ("range_onset_bidirectional_v1", "ETH"),
        ("range_onset_bidirectional_v1", "SOL"),
        ("range_onset_bidirectional_v1", "HYPE"),
        ("hypervelocity_source_follow_bidirectional_5m_v1", "BTC"),
        ("hype_breakout_onset_bidirectional_v1", "HYPE"),
    ];
    let journal = providers
        .into_iter()
        .enumerate()
        .map(|(index, (strategy, symbol))| observer_journal_row(index, strategy, symbol))
        .collect();
    CohortCheckpointTelemetry {
        configured: true,
        available: true,
        analysis_mode: Some("forward_observer".into()),
        generated_at_utc: Some("2026-08-01T16:00:00+00:00".into()),
        lifecycle_state: Some("setup_process_observation".into()),
        coverage_complete: Some(true),
        readiness_evaluations: Some(50),
        forward_evaluations: Some(40),
        eligible_signals: Some(1),
        five_minute_paths_resolved: Some(13),
        five_minute_paths_independent: Some(5),
        forward_path_coverage_complete: Some(true),
        evidence_state: Some("setup_and_signal_paths_only_no_execution_outcomes".into()),
        observer_provider_journal: journal,
        ..CohortCheckpointTelemetry::default()
    }
}

fn observer_journal_row(
    index: usize,
    strategy: &str,
    symbol: &str,
) -> CohortObserverProviderEvidence {
    let paths = if index == 0 {
        BTreeMap::from([
            (5, observer_path(9, 3, 4.25, 2.0 / 3.0)),
            (15, observer_path(4, 1, -2.0, 0.25)),
        ])
    } else {
        BTreeMap::new()
    };
    let eligible_paths = match index {
        0 => BTreeMap::from([(5, observer_path(1, 1, 12.0, 1.0))]),
        1 => BTreeMap::from([(5, observer_unresolved_path(1))]),
        _ => BTreeMap::new(),
    };
    let readiness_paths = if index == 0 {
        BTreeMap::from([
            (5, observer_path(8, 2, 3.28, 0.625)),
            (15, observer_path(4, 1, -2.0, 0.25)),
        ])
    } else {
        BTreeMap::new()
    };
    CohortObserverProviderEvidence {
        strategy_id: strategy.into(),
        symbol: symbol.into(),
        research_state: Some("forward_observer".into()),
        confidence: Some("low".into()),
        historical_cadence: Some("not established; measuring each onset".into()),
        historical_summary: Some("No stable after-friction evidence is bound.".into()),
        evidence_source: Some("docs/reviews/provider.md".into()),
        directional_research: BTreeMap::new(),
        forward_assessment: Some(
            if index == 0 {
                "descriptive_adverse_paths"
            } else {
                "no_eligible_signal_evidence"
            }
            .into(),
        ),
        execution_performance_scope: None,
        execution_performance: None,
        execution_performance_by_side: BTreeMap::new(),
        repeatability_evidence: None,
        latest_side: Some(if symbol == "HYPE" { "short" } else { "long" }.into()),
        readiness_fraction: Some(if index == 3 { 5.0 / 6.0 } else { 1.0 / 3.0 }),
        latest_reason: Some(
            if index == 9 {
                "5m_not_breakout"
            } else {
                "no_trigger"
            }
            .into(),
        ),
        latest_blockers: vec![
            if index == 9 {
                "5m_not_breakout"
            } else {
                "squeeze_not_armed"
            }
            .into(),
        ],
        readiness_evaluations: 5,
        eligible_signals: usize::from(index == 0),
        paths,
        eligible_paths,
        readiness_paths,
        one_blocker_near_misses: None,
        orderbook_opportunity: None,
    }
}
