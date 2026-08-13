#[test]
fn research_journal_separates_fired_signals_from_readiness_annotations() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = observer_checkpoint_with_journal();

    let screen = render(&mut app, 5, 160, 44);

    for expected in [
        "EVIDENCE-CLASS JOURNAL",
        "FIRED-SIGNAL EVIDENCE DESCRIPTIVE ONLY",
        "SIGNAL 5M",
        "FORWARD STATE",
        "DESCRIPTIVE ADVERSE",
        "R1/I1 +12.0 100%",
        "R0/I0 C1",
        "NOT FILLS, PNL, OR WIN PROBABILITY",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

#[test]
fn research_screen_exposes_ranked_route_side_frontier() {
    let mut app = cohort_app();
    let mut checkpoint = observer_checkpoint_with_journal();
    checkpoint.side_composition = Some(side_composition_fixture());
    app.backend.cohort_checkpoint = checkpoint;

    let screen = render(&mut app, 5, 160, 48);

    for expected in [
        "ROUTE-SIDE FRONTIER // REPORT ONLY",
        "MIXED PROFILE // NOT CURRENT EDGE // NO AUTO SIZE",
        "LONG HT-Breakout HYPE",
        "8 TRADES",
        "NET +$0.50",
        "USD PF 1.30",
        "NORM PF 3.08",
        "TENSION",
        "SHORT HV SOURCE 5M BTC",
        "1 TRADE",
        "NET +$0.14",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

fn side_composition_fixture() -> CohortSideComposition {
    CohortSideComposition {
        source_run_id: "cohort-test".into(),
        as_of_utc: "2026-08-01T16:00:00+00:00".into(),
        components: 25,
        long_frontier: vec![CohortSideComponent {
            component: "hype_breakout_onset_bidirectional_v1|HYPE|long".into(),
            priority: 4,
            evidence_tier: "repeated_positive_mixed_profile".into(),
            evidence_tension: true,
            trades: 8,
            net_pnl_usd: 0.502458,
            usd_profit_factor: Some(1.30454),
            normalized_profit_factor: Some(3.07913),
        }],
        short_frontier: vec![CohortSideComponent {
            component: "hypervelocity_source_follow_bidirectional_5m_v1|BTC|short".into(),
            priority: 3,
            evidence_tier: "positive_sparse_mixed_profile".into(),
            evidence_tension: true,
            trades: 1,
            net_pnl_usd: 0.135163,
            usd_profit_factor: None,
            normalized_profit_factor: None,
        }],
    }
}

#[test]
fn live_research_journal_exposes_execution_contract_parity_and_cost_delta() {
    let mut app = cohort_app();
    let mut checkpoint = observer_checkpoint_with_journal();
    checkpoint.analysis_mode = Some("live_execution".into());
    checkpoint.friction_parity = Some(friction_parity_fixture());
    app.backend.cohort_checkpoint = checkpoint;
    app.selected_cohort_journal_index = 8;

    let journal = render(&mut app, 5, 160, 48);

    for expected in [
        "EXECUTION PARITY 1/2 ALIGNED // 1 MISMATCH // ENTRY FILLS 2",
        "EXEC",
        "MISMATCH",
    ] {
        assert!(journal.contains(expected), "missing {expected}\n{journal}");
    }
    app.show_cohort_journal_modal = true;

    let screen = render(&mut app, 5, 160, 48);

    for expected in [
        "CONTRACT MISMATCH",
        "EXECUTION CONTRACT PARITY // REPORT ONLY",
        "ENTRY MODEL MAKER / LIVE TAKER MARKET IOC",
        "FEE MODEL 1.50bps / OBS 4.32bps / DELTA +2.82bps",
        "SLIP MODEL 0.00bps / OBS 1.59bps / DELTA +1.59bps",
        "EXIT MODEL STOP N/A HOLD FIXED 86400s TARGET MAKER 26.67bps",
        "LIVE STOP FIXED 80.00bps HOLD FIXED 28800s TARGET NONE RECIPE EXIT IGNORE",
        "MODEL SOURCE configs/source.toml // RUNTIME SOURCE PROVIDER EXECUTION",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

fn friction_parity_fixture() -> CohortFrictionParity {
    CohortFrictionParity {
        provider_symbols: 2,
        runtime_shape_aligned: 1,
        contract_mismatch: 1,
        unsupported_contract: 0,
        runtime_contract_missing: 0,
        provider_symbols_with_entry_fills: 2,
        by_provider_symbol: BTreeMap::from([
            (
                "hypervelocity_source_follow_bidirectional_5m_v1|BTC".into(),
                source_friction_fixture(),
            ),
            (
                "hype_breakout_onset_bidirectional_v1|HYPE".into(),
                aligned_friction_fixture(),
            ),
        ]),
    }
}

fn source_friction_fixture() -> CohortProviderFrictionParity {
    CohortProviderFrictionParity {
        parity_state: "contract_mismatch".into(),
        mismatches: vec!["entry_liquidity".into(), "target_policy".into()],
        modeled_entry_liquidity: Some("maker".into()),
        modeled_entry_fee_bps: Some(1.5),
        modeled_entry_slippage_bps: Some(0.0),
        modeled_stop_bps: None,
        modeled_maximum_hold_seconds: Some(86_400),
        modeled_target_policy: Some("maker_target_26.6667bps".into()),
        modeled_evidence_source: Some("configs/source.toml".into()),
        runtime_entry_liquidity: Some("taker".into()),
        runtime_entry_order: Some("market_ioc".into()),
        runtime_stop_bps: Some(80.0),
        runtime_maximum_hold_seconds: Some(28_800),
        runtime_target_policy: Some("none".into()),
        runtime_provider_recipe_exit_policy: "ignore".into(),
        entry_fills: 1,
        observed_fee_mean_bps: Some(4.32),
        observed_slippage_mean_bps: Some(1.59),
        observed_latency_mean_ms: Some(1_223.0),
        fee_mean_minus_modeled_bps: Some(2.82),
        slippage_mean_minus_modeled_bps: Some(1.59),
        runtime_contract_source: Some("provider_execution".into()),
        modeled_stop_description: None,
        modeled_hold_description: Some("FIXED 86400s".into()),
        modeled_target_description: Some("MAKER 26.67bps".into()),
        runtime_stop_description: Some("FIXED 80.00bps".into()),
        runtime_hold_description: Some("FIXED 28800s".into()),
        runtime_target_description: Some("NONE".into()),
    }
}

fn aligned_friction_fixture() -> CohortProviderFrictionParity {
    CohortProviderFrictionParity {
        parity_state: "runtime_shape_aligned".into(),
        mismatches: Vec::new(),
        modeled_entry_liquidity: Some("taker".into()),
        modeled_entry_fee_bps: Some(4.5),
        modeled_entry_slippage_bps: Some(2.0),
        modeled_stop_bps: Some(80.0),
        modeled_maximum_hold_seconds: Some(28_800),
        modeled_target_policy: Some("none".into()),
        modeled_evidence_source: Some("research/hype.py".into()),
        runtime_entry_liquidity: Some("taker".into()),
        runtime_entry_order: Some("market_ioc".into()),
        runtime_stop_bps: Some(80.0),
        runtime_maximum_hold_seconds: Some(28_800),
        runtime_target_policy: Some("none".into()),
        runtime_provider_recipe_exit_policy: "ignore".into(),
        entry_fills: 1,
        observed_fee_mean_bps: Some(4.32),
        observed_slippage_mean_bps: Some(0.70),
        observed_latency_mean_ms: Some(1_268.0),
        fee_mean_minus_modeled_bps: Some(-0.18),
        slippage_mean_minus_modeled_bps: Some(-1.30),
        runtime_contract_source: Some("asset_default".into()),
        modeled_stop_description: Some("FIXED 80.00bps".into()),
        modeled_hold_description: Some("FIXED 28800s".into()),
        modeled_target_description: Some("NONE".into()),
        runtime_stop_description: Some("FIXED 80.00bps".into()),
        runtime_hold_description: Some("FIXED 28800s".into()),
        runtime_target_description: Some("NONE".into()),
    }
}

#[test]
fn selected_research_row_opens_all_horizon_evidence() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint = observer_checkpoint_with_journal();
    app.selected_cohort_journal_index = 0;
    app.show_cohort_journal_modal = true;

    let screen = render(&mut app, 5, 160, 44);

    for expected in [
        "RESEARCH EVIDENCE INSPECTOR",
        "ELIGIBLE SIGNAL PATHS",
        "READINESS-ONLY PATHS",
        "5M  R1/I1",
        "15M  R4/I1",
        "SQUEEZE NOT ARMED",
        "COUNTERFACTUAL CANDLE PATHS",
        "RESEARCH FORWARD OBSERVER // CONFIDENCE LOW",
        "CADENCE not established; measuring each onset",
        "ROUTE LIVE EXECUTABLE // RESEARCH REPORT ONLY",
        "NO AUTO FILTER OR SIZE",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

#[test]
fn selected_live_research_row_shows_exact_execution_performance() {
    let mut app = cohort_app();
    let mut checkpoint = observer_checkpoint_with_journal();
    checkpoint.analysis_mode = Some("live_execution".into());
    checkpoint.observer_provider_journal[9].execution_performance =
        Some(CohortTradePerformanceSummary {
            closed_trades: 4,
            wins: 3,
            losses: 1,
            breakeven: 0,
            win_rate_pct: Some(75.0),
            net_pnl_usd: 1.004659,
            entry_margin_used_usd: 20.0,
            net_return_on_margin_pct: Some(5.023295),
            mean_trade_return_on_margin_pct: Some(5.1),
            profit_factor: Some(5.48675),
            fees_usd: 0.08,
            funding_usd: -0.001,
        });
    checkpoint.observer_provider_journal[9].execution_performance_scope =
        Some("provider_execution_contract_history".into());
    checkpoint.observer_provider_journal[9].execution_performance_by_side = BTreeMap::from([
        (
            "long".into(),
            CohortTradePerformanceSummary {
                closed_trades: 3,
                wins: 2,
                losses: 1,
                breakeven: 0,
                win_rate_pct: Some(66.6667),
                net_pnl_usd: 0.772171,
                entry_margin_used_usd: 15.0,
                net_return_on_margin_pct: Some(5.147807),
                mean_trade_return_on_margin_pct: Some(4.8),
                profit_factor: Some(4.0),
                fees_usd: 0.06,
                funding_usd: -0.0008,
            },
        ),
        (
            "short".into(),
            CohortTradePerformanceSummary {
                closed_trades: 1,
                wins: 1,
                losses: 0,
                breakeven: 0,
                win_rate_pct: Some(100.0),
                net_pnl_usd: 0.232488,
                entry_margin_used_usd: 5.0,
                net_return_on_margin_pct: Some(4.64976),
                mean_trade_return_on_margin_pct: Some(4.64976),
                profit_factor: None,
                fees_usd: 0.02,
                funding_usd: -0.0002,
            },
        ),
    ]);
    checkpoint.observer_provider_journal[9].repeatability_evidence = Some(repeatability_evidence());
    checkpoint.allocation_challenger = Some(allocation_challenger());
    app.backend.cohort_checkpoint = checkpoint;
    app.selected_cohort_journal_index = 9;
    app.show_cohort_journal_modal = true;

    let screen = render(&mut app, 5, 160, 48);

    for expected in [
        "LIVE CONFIG-CONTRACT SAMPLE // RESOLVED VENUE LIFECYCLES",
        "CLOSED 4 // W/L/BE 3/1/0 // WR 75.0%",
        "NET +$1.00 // RETURN +5.02% // PF 5.49",
        "FEES $0.08 // FUNDING -$0.00 // DESCRIPTIVE ONLY",
        "LONG 3  2W/1L/0BE  NET +$0.77  PF 4.00",
        "SHORT 1  1W/0L/0BE  NET +$0.23  PF N/A",
        "REPEATABILITY // 4 CLOSED OVER 32.9H // 2.92/DAY OBSERVED",
        "MEAN +$0.25 // MEDIAN +$0.16 // LEAVE-BEST +$0.11",
        "LARGEST WINNER 73.2% OF GROSS PROFIT // DESCRIPTIVE",
        "NO FORECAST // NO TRADE-COUNT OR BALANCE GATE",
        "ALLOCATION CHALLENGER // CANDIDATE NOT ACTIVE",
        "CAP $25.00 -> $75.00 // MARGIN $5.00 -> $15.00",
        "PORTFOLIO MAX MARGIN 5.95% -> 7.93% (+1.98pp)",
        "LIVE L2 240 SNAP // $75 IOC LONG 100.0% BBO 99.6% P95 0.02bp",
        "SHORT 100.0% BBO 99.2% P95 0.03bp // MIN BBO $510/$490",
        "ACCOUNT $504.23 IS A SIZING INPUT // NOT A BALANCE GATE",
        "NO PROFIT FORECAST // EXPLICIT CONFIG RESTART REQUIRED",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(screen.contains("HT-Breakout"), "{screen}");
    assert!(!screen.contains("hype_breakout"), "{screen}");
}

fn repeatability_evidence() -> CohortRepeatabilityEvidence {
    CohortRepeatabilityEvidence {
        strategy_id: "hype_breakout_onset_bidirectional_v1".into(),
        symbol: "HYPE".into(),
        summary: CohortRepeatabilitySummary {
            closed_trades: 4,
            evidence_state: "descriptive_multi_trade_sample".into(),
            first_entry_timestamp_ms: 1_700_000_000_000,
            last_exit_timestamp_ms: 1_700_118_512_000,
            observation_span_hours: 32.92,
            trades_per_24h_observed: Some(2.916),
            net_pnl_usd: 1.004659,
            mean_net_pnl_usd: 0.25116475,
            median_net_pnl_usd: 0.164544,
            sample_stddev_net_pnl_usd: Some(0.4726749371),
            gross_profit_usd: 1.228576,
            gross_loss_usd: 0.223917,
            profit_factor: Some(5.48675),
            largest_winner_usd: Some(0.899488),
            largest_winner_share_of_gross_profit_pct: Some(73.21386711),
            net_pnl_excluding_largest_winner_usd: Some(0.105171),
        },
        by_side: BTreeMap::new(),
    }
}

fn allocation_challenger() -> CohortAllocationChallenger {
    CohortAllocationChallenger {
        status: "candidate_not_active".into(),
        target_provider_symbol: "hype_breakout_onset_bidirectional_v1|HYPE".into(),
        account_value_usd: 504.23,
        current: allocation_projection(25.0, 25.0),
        candidate: allocation_projection(75.0, 75.0),
        effective_change: true,
        portfolio: CohortAllocationPortfolio {
            current_maximum_margin_fraction: 0.0595,
            candidate_maximum_margin_fraction: 0.0793,
            change_percentage_points: 1.98,
        },
        execution_sample: CohortAllocationExecutionSample {
            status: "resolved_live_sample".into(),
            closed_trades: Some(4),
            net_pnl_usd: Some(1.004659),
            profit_factor: Some(5.486747),
        },
        visible_depth_capacity: Some(CohortAllocationCapacity {
            snapshot_count: 240,
            candidate_notional_usd: 75.0,
            long: CohortAllocationCapacitySide {
                complete_rate: 1.0,
                bbo_fill_rate: 0.996,
                median_impact_bps: Some(0.0),
                p95_impact_bps: Some(0.02),
                maximum_impact_bps: Some(0.08),
                minimum_bbo_notional_usd: 510.0,
            },
            short: CohortAllocationCapacitySide {
                complete_rate: 1.0,
                bbo_fill_rate: 0.992,
                median_impact_bps: Some(0.0),
                p95_impact_bps: Some(0.03),
                maximum_impact_bps: Some(0.10),
                minimum_bbo_notional_usd: 490.0,
            },
        }),
    }
}

fn allocation_projection(cap: f64, planned: f64) -> CohortAllocationProjection {
    CohortAllocationProjection {
        configured_leverage: 5.0,
        configured_margin_fraction: 0.03,
        configured_max_notional_usd: cap,
        uncapped_notional_usd: 75.6345,
        planned_notional_usd: planned,
        planned_margin_usd: planned / 5.0,
        effective_margin_fraction: planned / 5.0 / 504.23,
        cap_binding: 75.6345 > cap,
    }
}

fn observer_path(
    resolved: usize,
    independent: usize,
    mean_bps: f64,
    positive_rate: f64,
) -> CohortObserverPathEvidence {
    CohortObserverPathEvidence {
        resolved,
        independent,
        censored: 0,
        missing_data: 0,
        mean_directional_return_bps: Some(mean_bps),
        positive_directional_rate: Some(positive_rate),
        opportunity_capture: None,
    }
}

fn observer_unresolved_path(censored: usize) -> CohortObserverPathEvidence {
    CohortObserverPathEvidence {
        resolved: 0,
        independent: 0,
        censored,
        missing_data: 0,
        mean_directional_return_bps: None,
        positive_directional_rate: None,
        opportunity_capture: None,
    }
}
