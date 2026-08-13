#[test]
fn compact_dashboard_keeps_operational_truth_visible() {
    let mut app = cohort_app();
    let screen = render(&mut app, 0, 120, 36);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("120x36 DASHBOARD\n{screen}");
    }
    for expected in [
        "HYPERVECTOR // SHARED COHORT",
        "LIVE EXECUTION ARMED",
        "SYNC 12:00:00 EDT",
        "USDC COLL $503.16",
        "SOURCE UNIFIED SPOT",
        "MARGIN UTIL",
        "0.99%",
        "OPEN 1 / 4",
        "VENUE BRACKET",
        "S12/T13@103.00",
        "HK24H RX:I",
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "MARKET PULSE",
        "SETUP PROXIMITY",
        "NEXT BLOCKER",
        "Backend-authored telemetry",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(screen.contains('╭'), "rounded chrome missing\n{screen}");
    assert!(screen.contains('━'), "capital/risk meter missing\n{screen}");
    assert!(
        !screen.contains("███████POSITION"),
        "smashed gauge label\n{screen}"
    );
}

#[test]
fn compact_dashboard_stacks_every_complete_portfolio_position() {
    let mut app = complete_portfolio_app();

    let screen = render(&mut app, 0, 120, 36);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("120x36 COMPLETE PORTFOLIO\n{screen}");
    }

    assert!(
        screen.contains("LIVE POSITIONS // ASSETS 1-4 / 9"),
        "{screen}"
    );
    assert!(
        screen.contains("LIVE POSITIONS // ASSETS 5-9 / 9"),
        "{screen}"
    );
    for symbol in COMPLETE_SYMBOLS {
        assert!(screen.contains(symbol), "missing {symbol}\n{screen}");
    }
}

#[test]
fn wide_dashboard_prioritizes_two_live_position_panels_over_redundant_visuals() {
    let mut app = complete_portfolio_app();
    app.backend.cohort_checkpoint = trade_checkpoint();

    let screen = render(&mut app, 0, 190, 52);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("190x52 COMPLETE PORTFOLIO\n{screen}");
    }

    assert!(
        screen.contains("LIVE POSITIONS // ASSETS 1-4 / 9"),
        "{screen}"
    );
    assert!(
        screen.contains("LIVE POSITIONS // ASSETS 5-9 / 9"),
        "{screen}"
    );
    assert!(screen.contains("STRATEGY LEDGER"), "{screen}");
    assert!(
        !screen.contains("CURRENT RUN EQUITY // CLOSED LINE"),
        "{screen}"
    );
    assert!(!screen.contains("CURRENT RUN // LONG-SHORT"), "{screen}");
    assert!(
        !screen.contains("EXECUTION FRICTION // CURRENT RUN"),
        "{screen}"
    );
}

#[test]
fn stale_dashboard_does_not_claim_venue_authoritative_positions() {
    let mut app = complete_portfolio_app();
    app.backend.connection = BackendConnectionState::Stale;

    let screen = render(&mut app, 0, 190, 52);

    assert!(screen.contains("STALE BACKEND TELEMETRY"), "{screen}");
    assert!(screen.contains("LAST CHECKPOINT ARMED"), "{screen}");
    assert!(!screen.contains("LIVE EXECUTION ARMED"), "{screen}");
    assert!(!screen.contains("VENUE AUTHORITATIVE"), "{screen}");
}

#[test]
fn stale_control_screen_disables_requests_and_does_not_claim_auto_routing() {
    let mut app = complete_portfolio_app();
    app.backend.connection = BackendConnectionState::Stale;
    app.cohort_command_inbox = Some("data/live/bidirectional_cohort/operator_commands".into());

    app.prepare_cohort_confirmation();
    let screen = render(&mut app, 6, 190, 52);

    assert!(app.cohort_confirmation.is_none());
    assert_eq!(
        app.cohort_notice.as_deref(),
        Some("backend is not connected")
    );
    assert!(
        screen.contains("BACKEND STALE // MANUAL REQUESTS DISABLED"),
        "{screen}"
    );
    assert!(screen.contains("AUTOMATIC ROUTING NOT CLAIMED"), "{screen}");
    assert!(!screen.contains("REQUEST CHANNEL ENABLED"), "{screen}");
    assert!(!screen.contains("AUTO ROUTING CONTINUES"), "{screen}");
    assert!(
        !screen.contains("AUTOMATIC ENTRY + EXIT ROUTING ACTIVE"),
        "{screen}"
    );
}

#[test]
fn connection_loss_after_confirmation_prevents_operator_request_write() {
    let temporary = tempfile::tempdir().expect("tempdir");
    let inbox = temporary.path().join("operator_commands");
    fs::create_dir_all(inbox.join("pending")).expect("pending inbox");
    let mut app = cohort_app();
    app.cohort_command_inbox = Some(inbox.clone());
    app.cohort_control_focus = 1;

    app.prepare_cohort_confirmation();
    assert!(app.cohort_confirmation.is_some());
    app.backend.connection = BackendConnectionState::Stale;
    app.submit_cohort_confirmation();

    assert_eq!(
        app.cohort_notice.as_deref(),
        Some("REQUEST NOT SUBMITTED // backend is not connected")
    );
    assert_eq!(
        fs::read_dir(inbox.join("pending"))
            .expect("pending inbox")
            .count(),
        0
    );
}

#[test]
fn readiness_seed_is_not_rendered_as_an_unexplained_live_action() {
    let mut app = cohort_app();
    let evaluation = app
        .backend
        .cohort
        .evaluations
        .first_mut()
        .expect("provider evaluation");
    evaluation.eligible = true;
    evaluation.decision_action = "enter_long".into();
    evaluation.backend_non_action_reason = Some("pre_activation_readiness_seed".into());

    let screen = render(&mut app, 1, 190, 52);

    assert!(screen.contains("READINESS ONLY"), "{screen}");
    assert!(screen.contains("PRE ACTIVATION READINESS SEED"), "{screen}");
}

#[test]
fn tall_trade_workspace_retains_relocated_performance_visuals() {
    let mut app = complete_portfolio_app();
    app.backend.cohort_checkpoint = trade_checkpoint();

    let screen = render(&mut app, 4, 190, 52);

    for expected in [
        "CURRENT RUN EQUITY // CLOSED LINE",
        "CURRENT RUN // LONG-SHORT",
        "EXECUTION FRICTION // CURRENT RUN",
        "COMPLETED TRADES",
        "VENUE FILL LEGS",
        "xyz:GOLD",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

#[test]
fn dashboard_projects_authoritative_portfolio_trade_history() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = trade_checkpoint();

    let screen = render(&mut app, 0, 120, 36);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("120x36 PORTFOLIO HISTORY\n{screen}");
    }

    for expected in [
        "PORTFOLIO PERFORMANCE // LIVE LEDGER",
        "THIS RUN 1 CLOSED",
        "W1 L0 BE0",
        "WR 100.0%",
        "NET +$0.23",
        "ALL-TIME 2 CLOSED",
        "W1 L1 BE0",
        "WR 50.0%",
        "NET -$0.50",
        "PF 0.32",
        "PORTFOLIO $507.08",
        "USDC COLL $504.11",
        "OTHER SPOT $2.97",
        "MAX DD 0.18%",
        "SIZE CAP 4/4",
        "RESERVE 3.97%",
        "STRATEGY LEDGER // RUN | ALL-TIME MIXED PROFILES",
        "HULK EXPANSION",
        "HT-Breakout",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    let hulk = screen
        .lines()
        .find(|line| line.contains("HULK EXPANSION"))
        .expect("all-time Hulk row");
    for expected in ["N/A", "0/1", "-$0.73"] {
        assert!(hulk.contains(expected), "missing {expected}\n{hulk}");
    }
    let hype = screen
        .lines()
        .find(|line| line.contains("HT-Breakout"))
        .expect("run and all-time HT-Breakout row");
    assert_eq!(hype.matches("1/0").count(), 2, "{hype}");
    assert_eq!(hype.matches("+$0.23").count(), 2, "{hype}");
}

#[test]
fn dashboard_labels_hulk_entry_quality_as_annotation_only() {
    let mut app = complete_portfolio_app();
    let mut checkpoint = trade_checkpoint();
    checkpoint.hulk_entry_quality = Some(hulk_entry_quality_checkpoint());
    app.backend.cohort_checkpoint = checkpoint;

    let screen = render(&mut app, 0, 190, 52);

    assert!(
        screen.contains("HULK Q ANNOTATION ONLY"),
        "missing authority label\n{screen}"
    );
    assert!(screen.contains("BOTH 0"), "missing joint class\n{screen}");
    assert!(screen.contains("ONE 0"), "missing partial class\n{screen}");
    assert!(screen.contains("NEITHER 2 +$0.34"), "{screen}");
    assert!(screen.contains("OPEN SOL:NEITHER"), "{screen}");
}

#[test]
fn pooled_strategy_history_is_explicitly_labeled_mixed_profiles() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = trade_checkpoint();

    let dashboard = render(&mut app, 0, 120, 36);
    assert!(
        dashboard.contains("STRATEGY LEDGER // RUN | ALL-TIME MIXED PROFILES"),
        "{dashboard}"
    );

    let trades = render(&mut app, 4, 165, 46);
    assert!(trades.contains("ALL-TIME"), "{trades}");
    assert!(
        trades.contains("MIXED PROFILES // EXACT CONTRACT: SCREEN 6"),
        "{trades}"
    );
}

#[test]
fn dashboard_does_not_erase_all_time_live_history_after_profile_change() {
    let mut app = cohort_app();
    let mut checkpoint = trade_checkpoint();
    checkpoint.all_time_trade_reflections = checkpoint.trade_reflections.clone();
    checkpoint.trade_reflections.clear();
    let performance = checkpoint
        .trade_performance
        .as_mut()
        .expect("performance fixture");
    performance.all_time_live = Some(CohortAllTimeTradePerformance {
        total: performance.total.clone(),
        by_strategy: performance.by_strategy.clone(),
    });
    performance.total = CohortTradePerformanceSummary::default();
    performance.by_strategy.clear();
    performance.current_profile = None;
    performance.current_run = Some(CohortRunTradePerformance {
        run_id: "cohort-test".into(),
        total: CohortTradePerformanceSummary::default(),
        by_strategy: BTreeMap::new(),
    });
    app.backend.cohort_checkpoint = checkpoint;

    let screen = render(&mut app, 0, 120, 36);

    for expected in [
        "THIS RUN 0 CLOSED",
        "ALL-TIME 2 CLOSED",
        "HULK EXPANSION",
        "HT-Breakout",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }

    let trades = render(&mut app, 4, 165, 46);
    for expected in [
        "ARCHIVE 2",
        "PROFILE WINDOW 0T/2CFG",
        "HULK EXPANSION",
        "HT-Breakout",
        "$64100.0000",
        "$63900.0000",
    ] {
        assert!(trades.contains(expected), "missing {expected}\n{trades}");
    }

    let regime = render(&mut app, 7, 165, 46);
    assert!(!regime.contains("AWAITING CLOSED LIFECYCLE"), "{regime}");
    assert!(regime.contains("BTC L -0.73 STOP"), "{regime}");
}

#[test]
fn dashboard_prefers_durable_archive_and_labels_observation_only_assets() {
    let mut app = cohort_app();
    for provider in &mut app.backend.cohort.providers {
        provider.execution_symbols = Some(match provider.strategy_id.as_str() {
            "eth_breakout_precompression_pullback_bidirectional_v1" => vec!["ETH".into()],
            "range_onset_bidirectional_v1" => vec!["SOL".into()],
            _ => Vec::new(),
        });
    }
    let mut checkpoint = trade_checkpoint();
    let performance = checkpoint
        .trade_performance
        .as_mut()
        .expect("performance fixture");
    performance.current_run = Some(CohortRunTradePerformance {
        run_id: "cohort-test".into(),
        total: CohortTradePerformanceSummary::default(),
        by_strategy: BTreeMap::new(),
    });
    checkpoint.portfolio_archive = Some(CohortPortfolioArchive {
        symbols: SYMBOLS.map(str::to_string).to_vec(),
        observed_through_utc: Some("2026-08-07T17:00:00+00:00".into()),
        performance: CohortAllTimeTradePerformance {
            total: CohortTradePerformanceSummary {
                closed_trades: 26,
                wins: 13,
                losses: 13,
                breakeven: 0,
                win_rate_pct: Some(50.0),
                net_pnl_usd: -1.695979,
                entry_margin_used_usd: 198.277796,
                net_return_on_margin_pct: Some(-0.855355),
                mean_trade_return_on_margin_pct: Some(-0.24),
                profit_factor: Some(0.654718),
                fees_usd: 0.837811,
                funding_usd: 0.002582,
            },
            by_strategy: performance.by_strategy.clone(),
        },
        accounting_epoch: None,
    });
    app.backend.cohort_checkpoint = checkpoint;

    let dashboard = render(&mut app, 0, 190, 52);
    assert!(dashboard.contains("ALL-TIME 26 CLOSED"), "{dashboard}");
    assert!(dashboard.contains("AUTH"), "{dashboard}");
    assert!(dashboard.contains("LIVE"), "{dashboard}");
    assert!(dashboard.contains("OBSERVE"), "{dashboard}");
}

#[test]
fn tall_trade_workspace_renders_a_scaled_closed_equity_instrument() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = trade_checkpoint();

    let screen = render(&mut app, 4, 160, 48);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("160x48 CLOSED EQUITY\n{screen}");
    }

    for expected in [
        "CURRENT RUN EQUITY // CLOSED LINE",
        "LIVE $502.66",
        "CLOSED EQ $503.39",
        "+$0.23 / +0.05%",
        "MARK GAP -$0.73",
        "RUN 1T  W1 L0 BE0",
        "WR 100.0%",
        "PF ∞",
        "CLOSED DD 0.00%",
        "HIST 2T -$0.50",
        "CURRENT RUN // LONG-SHORT",
        "EXECUTION FRICTION // CURRENT RUN",
        "CURRENT RUN FILL LEGS",
        "FILL FEES $0.01",
        "▲ LONG   0T  W0-L0",
        "▼ SHORT  1T  W1-L0",
        "TRADE 0",
        "TRADE 1",
        "L $503.16",
        "[01 HYPE ▲ +$0.23]",
        "╱",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(
        !screen.contains('▓'),
        "equity line must not render a solid fill\n{screen}"
    );
    assert!(
        !screen.contains('░'),
        "equity line must not render a drawdown fill\n{screen}"
    );
}

#[test]
fn closed_equity_instrument_does_not_invent_a_zero_dollar_baseline() {
    let mut app = cohort_app();
    let mut checkpoint = trade_checkpoint();
    checkpoint.portfolio = None;
    app.backend.cohort_checkpoint = checkpoint;

    let screen = render(&mut app, 4, 160, 48);

    assert!(
        screen.contains("CURRENT RUN PATH UNAVAILABLE // BASELINE OR IDENTITY MISMATCH"),
        "{screen}"
    );
    assert!(!screen.contains("B $0.00"), "{screen}");
}

#[test]
fn mixed_history_without_run_identity_does_not_invent_an_equity_path() {
    let mut app = cohort_app();
    let mut checkpoint = trade_checkpoint();
    checkpoint
        .trade_performance
        .as_mut()
        .expect("performance")
        .current_run = None;
    app.backend.cohort_checkpoint = checkpoint;

    let screen = render(&mut app, 4, 160, 48);

    assert!(
        screen.contains("CURRENT RUN PATH UNAVAILABLE // BASELINE OR IDENTITY MISMATCH"),
        "{screen}"
    );
    assert!(!screen.contains("TRADE 2"), "{screen}");
}
