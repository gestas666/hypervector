fn open_regime_trade_reflection() -> CohortOpenTradeReflection {
    CohortOpenTradeReflection {
        lifecycle_id: "BTC:508726900000".into(),
        source_run_id: "bidirectional-live-a".into(),
        symbol: "BTC".into(),
        strategy_id: "hypervelocity_source_follow_bidirectional_5m_v1".into(),
        side: "short".into(),
        holding_time_ms: 19_886_090,
        protective_stop_oid: Some(508_726_918_963),
        protective_stop_price: Some(63_418.32),
        profit_protection: Some(CohortOpenProfitProtection {
            status: "open_profit_unprotected".into(),
            estimated_exit_now_net_usd: 0.092,
            estimated_stop_net_usd: -0.210,
            marked_to_stop_giveback_usd: 0.302,
            protected_profit_fraction: Some(0.0),
            stop_distance_from_mark_bps: 124.08,
        }),
        target_order_oid: Some(508_726_919_999),
        target_order_price: Some(62_200.0),
        target_directional_distance_bps: Some(70.4),
        exit_plan: CohortOpenExitPlan {
            opened_at_ms: None,
            timer_origin: None,
            as_of_timestamp_ms: None,
            maximum_hold_seconds: 28_800,
            maximum_hold_policy: "fixed".into(),
            provider_recipe_exit_policy: "ignore".into(),
            profit_lock_policy: "none".into(),
            profit_lock_activation_bps: None,
            profit_lock_floor_bps: None,
            profit_lock_giveback_bps: None,
            hard_maximum_hold_seconds: None,
            soft_deadline_timestamp_ms: 1_785_628_800_000,
            hard_deadline_timestamp_ms: None,
            deadline_timestamp_ms: 1_785_628_800_000,
            remaining_time_ms: 8_913_910,
            expired: false,
            extension_active: false,
            regime_context: "mixed_or_transition".into(),
            source: "bound_execution_plan".into(),
            controller: "cohort_maximum_hold".into(),
            opposite_intent_exit_scope:
                "selected_opposite_from_any_executable_provider_same_symbol".into(),
            opposite_intent_arbitration: "regime_then_priority".into(),
        },
        path_since_entry: CohortOpenPath {
            status: "observed".into(),
            completed_bars: 331,
            first_timestamp_ms: Some(1_785_600_060_000),
            last_timestamp_ms: Some(1_785_619_920_000),
            highest_price: Some(63_402.0),
            lowest_price: Some(62_590.0),
            current_directional_return_bps: Some(43.56),
            maximum_favorable_excursion_bps: Some(51.66),
            maximum_adverse_excursion_bps: Some(77.88),
            peak_giveback_bps: Some(8.10),
        },
        path_since_soft_deadline: Some(CohortOpenExtensionPath {
            status: "observed".into(),
            boundary_timestamp_ms: 1_785_628_800_000,
            baseline_timestamp_ms: Some(1_785_628_740_000),
            baseline_price: Some(63_200.0),
            completed_bars: 31,
            first_timestamp_ms: Some(1_785_628_860_000),
            last_timestamp_ms: Some(1_785_630_660_000),
            highest_price: Some(63_500.0),
            lowest_price: Some(63_150.0),
            current_directional_return_bps: Some(12.5),
            maximum_favorable_excursion_bps: Some(47.5),
            maximum_adverse_excursion_bps: Some(7.9),
            peak_giveback_bps: Some(35.0),
        }),
        post_soft_trail_challenger: Some(CohortOpenPostSoftTrail {
            status: "observed".into(),
            soft_deadline_timestamp_ms: 1_785_628_800_000,
            as_of_timestamp_ms: 1_785_630_720_000,
            completed_post_soft_bars: 31,
            policies: BTreeMap::from([
                (
                    20,
                    CohortOpenPostSoftTrailPolicy {
                        status: "triggered".into(),
                        ..CohortOpenPostSoftTrailPolicy::default()
                    },
                ),
                (
                    30,
                    CohortOpenPostSoftTrailPolicy {
                        status: "triggered".into(),
                        ..CohortOpenPostSoftTrailPolicy::default()
                    },
                ),
                (
                    40,
                    CohortOpenPostSoftTrailPolicy {
                        status: "armed_not_triggered".into(),
                        ..CohortOpenPostSoftTrailPolicy::default()
                    },
                ),
            ]),
        }),
        open_profit_lock_challenger: Some(CohortOpenProfitLock {
            status: "observed".into(),
            entry_timestamp_ms: 1_785_600_030_000,
            as_of_timestamp_ms: 1_785_619_920_000,
            completed_bars_expected: 331,
            completed_bars_observed: 331,
            policies: BTreeMap::from([
                (
                    "a25_floor15_trail10".into(),
                    CohortOpenProfitLockPolicy {
                        status: "triggered_before_current_boundary".into(),
                        trigger_reference_price: Some(62_652.59),
                        counterfactual_economics: Some(CohortOpenProfitLockEconomics {
                            status: "estimated_trigger_exit".into(),
                            reference_price: 62_652.59,
                            gross_return_bps: 31.0,
                            estimated_net_pnl_excluding_funding_usd: 1.20,
                            estimated_current_exit_net_excluding_funding_usd: 0.09,
                            estimated_minus_current_exit_net_excluding_funding_usd: 1.11,
                        }),
                        ..CohortOpenProfitLockPolicy::default()
                    },
                ),
                (
                    "a40_floor15_trail20".into(),
                    CohortOpenProfitLockPolicy {
                        status: "armed_not_triggered".into(),
                        active_stop_price: Some(62_715.18),
                        ..CohortOpenProfitLockPolicy::default()
                    },
                ),
                (
                    "a60_floor15_trail30".into(),
                    CohortOpenProfitLockPolicy {
                        status: "not_activated".into(),
                        ..CohortOpenProfitLockPolicy::default()
                    },
                ),
            ]),
        }),
        ignored_provider_exit_observer: Some(CohortIgnoredProviderExit {
            status: "observed".into(),
            provider_recipe_exit_policy: "ignore".into(),
            ignored_signal_count: 5,
            first_signal: Some(CohortIgnoredProviderExitSignal {
                decision_time_ms: 1_785_606_000_000,
                reference_price: 62_950.0,
                entry_directional_return_bps: -5.56,
                exit_reason: "source_direction_lost".into(),
                decision_action: Some("close_short".into()),
            }),
            path_since_first_signal: Some(CohortOpenPath {
                status: "observed".into(),
                completed_bars: 231,
                current_directional_return_bps: Some(49.09),
                ..CohortOpenPath::default()
            }),
        }),
        entry_signal: CohortTradeRegimeContext {
            breakout_side: Some("short".into()),
            structural_direction: Some("short".into()),
            breakout_side_relation: Some("aligned".into()),
            ..regime_context("TREND_DOWN")
        },
        entry_canonical: regime_context("TREND_DOWN"),
        entry_structure_support_score: Some(5.0 / 6.0),
        entry_structure_stance: "directionally_supported".into(),
        current_signal: regime_context("TRANSITION"),
        current_canonical: regime_context("TREND_DOWN"),
        signal_provider_changed: Some(true),
        canonical_regime_changed: Some(false),
        structure_support_score: Some(7.0 / 12.0),
        structure_stance: "directionally_supported".into(),
        component_alignment_score: Some(-7.0 / 9.0),
        component_stance: "opposing_position".into(),
        movement_strength: Some(0.82),
        maximum_hold_context: "still_directionally_supported".into(),
        regime_opposition: Some(CohortRegimeOppositionEpisode {
            completed_decisions: 331,
            opposed_decisions: 73,
            maximum_consecutive_opposed: 7,
            current_consecutive_opposed: 4,
            current_active: true,
            trigger_one_decision_ms: Some(1_785_606_000_000),
            trigger_three_decisions_ms: Some(1_785_606_120_000),
            trigger_five_decisions_ms: Some(1_785_606_240_000),
            ..CohortRegimeOppositionEpisode::default()
        }),
        mark_price: 62_641.0,
        active_lifecycle_marked_net_pnl_usd: 0.103396,
    }
}

fn trade_checkpoint() -> CohortCheckpointTelemetry {
    let mut hype = regime_trade_reflection();
    hype.source_run_id = "cohort-test".into();
    hype.source_profile_fingerprint = Some("current-profile-fingerprint".into());
    let mut btc = hype.clone();
    btc.lifecycle_id = "BTC:508600000000".into();
    btc.source_run_id = "prior-run".into();
    btc.symbol = "BTC".into();
    btc.strategy_id = "hulk_expansion_bidirectional_tuned_v2".into();
    btc.source_profile_fingerprint = Some("prior-profile-fingerprint".into());
    btc.exit_controller_strategy_id = "hulk_expansion_bidirectional_tuned_v2".into();
    btc.cross_provider_exit = false;
    btc.side = "long".into();
    btc.exit_reason = Some("protective_stop".into());
    btc.net_pnl_usd = -0.732488;
    btc.entry_price = Some(64_100.0);
    btc.exit_price = Some(63_900.0);
    btc.entry_venue_timestamp_ms = Some(1_785_744_000_000);
    btc.exit_venue_timestamp_ms = Some(1_785_745_800_000);
    btc.holding_time_ms = Some(1_800_000);
    btc.fees_usd = Some(0.03);
    btc.funding_usd = Some(-0.001);
    btc.price_return_pct = Some(-0.312012);
    btc.net_return_on_margin_pct = Some(-14.64976);
    if let Some(outcome) = btc.ignored_provider_exit_outcome.as_mut() {
        outcome.ignored_signal_count = 1;
        outcome.first_signal = Some(CohortIgnoredProviderExitSignal {
            decision_time_ms: 1_785_745_200_000,
            reference_price: 64_020.0,
            entry_directional_return_bps: -12.48,
            exit_reason: "hulk_alignment_lost".into(),
            decision_action: Some("close_long".into()),
        });
        outcome.path_from_first_signal_to_actual_exit = Some(CohortOpenPath {
            status: "resolved".into(),
            completed_bars: 10,
            current_directional_return_bps: Some(-18.74),
            maximum_favorable_excursion_bps: Some(45.0),
            maximum_adverse_excursion_bps: Some(28.0),
            peak_giveback_bps: Some(63.74),
            ..CohortOpenPath::default()
        });
        outcome.gross_continuation_from_signal_bps = Some(-18.74);
        outcome.actual_exit = CohortIgnoredProviderActualExit {
            venue_timestamp_ms: 1_785_745_800_000,
            price: 63_900.0,
            net_pnl_usd: -0.732488,
            fees_usd: 0.03,
            funding_usd: -0.001,
            exit_reason: Some("protective_stop".into()),
            exit_controller_strategy_id: "hulk_expansion_bidirectional_tuned_v2".into(),
        };
    }
    btc.regime_opposition = Some(CohortRegimeOppositionEpisode {
        completed_decisions: 150,
        opposed_decisions: 126,
        maximum_consecutive_opposed: 126,
        current_consecutive_opposed: 126,
        current_active: true,
        ..CohortRegimeOppositionEpisode::default()
    });
    let hype_summary = performance_summary(1, 1, 0, 0.232488, 5.0, 4.64976);
    let btc_summary = performance_summary(1, 0, 1, -0.732488, 5.0, -14.64976);
    CohortCheckpointTelemetry {
        configured: true,
        available: true,
        venue_portfolio: Some(CohortVenuePortfolio {
            portfolio_value_usd: 507.08,
            execution_collateral_value_usd: 504.11,
            non_usdc_spot_value_usd: 2.97,
            vault_equity_usd: 0.0,
            valued_spot_assets: Vec::new(),
            observed_at_utc: "2026-08-04T09:00:00+00:00".into(),
            valuation_source: "spot_midpoints_plus_vault_equity".into(),
        }),
        portfolio: Some(CohortPortfolioEvidence {
            status: "observed".into(),
            initial_equity_usd: 503.16,
            final_equity_usd: 502.66,
            equity_change_usd: -0.50,
            maximum_equity_usd: 503.40,
            minimum_equity_usd: 502.50,
            maximum_drawdown_pct: 0.18,
            maximum_margin_used_usd: 10.0,
            maximum_notional_usd: 50.0,
            maximum_open_positions: 2,
            snapshot_count: 100,
        }),
        trade_reflections: vec![hype, btc],
        trade_performance: Some(CohortTradePerformance {
            all_time_live: None,
            total: CohortTradePerformanceSummary {
                closed_trades: 2,
                wins: 1,
                losses: 1,
                breakeven: 0,
                win_rate_pct: Some(50.0),
                net_pnl_usd: -0.5,
                entry_margin_used_usd: 10.0,
                net_return_on_margin_pct: Some(-5.0),
                mean_trade_return_on_margin_pct: Some(-3.25),
                profit_factor: Some(0.32),
                fees_usd: 0.051412,
                funding_usd: 0.00145,
            },
            by_strategy: BTreeMap::from([
                ("hulk_expansion_bidirectional_tuned_v2".into(), btc_summary),
                (
                    "hype_breakout_onset_bidirectional_v1".into(),
                    hype_summary.clone(),
                ),
            ]),
            profile_fingerprint_count: Some(2),
            mixed_profile_history: true,
            current_profile: Some(CohortProfileTradePerformance {
                profile_fingerprint: "current-profile-fingerprint".into(),
                total: hype_summary.clone(),
                by_strategy: BTreeMap::from([(
                    "hype_breakout_onset_bidirectional_v1".into(),
                    hype_summary.clone(),
                )]),
            }),
            current_run: Some(CohortRunTradePerformance {
                run_id: "cohort-test".into(),
                total: hype_summary.clone(),
                by_strategy: BTreeMap::from([(
                    "hype_breakout_onset_bidirectional_v1".into(),
                    hype_summary,
                )]),
            }),
            process_run_windows: Some(CohortProcessRunWindows {
                run_count: 2,
                positive_runs: 1,
                negative_runs: 1,
                statistical_independence_established: false,
                ..CohortProcessRunWindows::default()
            }),
        }),
        risk_utilization: Some(CohortRiskUtilization {
            account_value_usd: 503.16,
            configured_assets: 4,
            cap_bound_assets: 4,
            configured_maximum_positions: 4,
            provider_symbols: 0,
            provider_symbol_overrides: 0,
            maximum_effective_margin_fraction: 20.0 / 503.16,
            by_asset: SYMBOLS
                .into_iter()
                .map(|symbol| {
                    (
                        symbol.into(),
                        CohortAssetRiskUtilization {
                            configured_leverage: 5.0,
                            configured_margin_fraction: 0.03,
                            configured_max_notional_usd: 25.0,
                            uncapped_notional_usd: 503.16 * 0.03 * 5.0,
                            planned_notional_usd: 25.0,
                            planned_margin_usd: 5.0,
                            effective_margin_fraction: 5.0 / 503.16,
                            notional_fraction_of_equity: 25.0 / 503.16,
                            cap_utilization_ratio: 25.0 / (503.16 * 0.03 * 5.0),
                            cap_binding: true,
                        },
                    )
                })
                .collect(),
            by_provider_symbol: BTreeMap::new(),
        }),
        ..CohortCheckpointTelemetry::default()
    }
}

fn hulk_entry_quality_checkpoint() -> CohortHulkEntryQuality {
    let zero = hulk_quality_summary(0, 0, 0, 0, 0.0, None);
    let neither = hulk_quality_summary(2, 2, 0, 0, 0.343_915, Some(3.470_776_713_864_958));
    let summaries = BTreeMap::from([
        ("flow_and_volume".into(), zero.clone()),
        ("one_of_two".into(), zero.clone()),
        ("neither".into(), neither),
        ("unavailable".into(), zero.clone()),
    ]);
    CohortHulkEntryQuality {
        closed_trades: 2,
        attributable_closed_trades: 2,
        closed_by_quality: summaries.clone(),
        by_side: BTreeMap::from([
            (
                "long".into(),
                CohortHulkEntryQualitySide {
                    closed_trades: 2,
                    closed_by_quality: summaries,
                },
            ),
            (
                "short".into(),
                CohortHulkEntryQualitySide {
                    closed_trades: 0,
                    closed_by_quality: BTreeMap::from([
                        ("flow_and_volume".into(), zero.clone()),
                        ("one_of_two".into(), zero.clone()),
                        ("neither".into(), zero.clone()),
                        ("unavailable".into(), zero),
                    ]),
                },
            ),
        ]),
        open_observations: vec![CohortHulkEntryQualityOpen {
            symbol: "SOL".into(),
            side: "long".into(),
            quality: "neither".into(),
            flow_direction: Some(-1),
            volume_ratio: Some(0.090_442_280_452_784_21),
            marked_net_pnl_usd: Some(-0.003_39),
        }],
    }
}

fn hulk_quality_summary(
    trades: usize,
    wins: usize,
    losses: usize,
    breakeven: usize,
    net_pnl_usd: f64,
    mean_net_return_on_margin_pct: Option<f64>,
) -> CohortHulkEntryQualitySummary {
    CohortHulkEntryQualitySummary {
        trades,
        wins,
        losses,
        breakeven,
        net_pnl_usd,
        mean_net_return_on_margin_pct,
        normalized_profit_factor: None,
    }
}

fn performance_summary(
    closed_trades: usize,
    wins: usize,
    losses: usize,
    net_pnl_usd: f64,
    margin: f64,
    return_pct: f64,
) -> CohortTradePerformanceSummary {
    CohortTradePerformanceSummary {
        closed_trades,
        wins,
        losses,
        breakeven: 0,
        win_rate_pct: Some(wins as f64 / closed_trades as f64 * 100.0),
        net_pnl_usd,
        entry_margin_used_usd: margin,
        net_return_on_margin_pct: Some(return_pct),
        mean_trade_return_on_margin_pct: Some(return_pct),
        profit_factor: (losses > 0).then_some(if wins > 0 { 0.32 } else { 0.0 }),
        fees_usd: 0.025706,
        funding_usd: 0.000725,
    }
}

fn regime_context(state: &str) -> CohortTradeRegimeContext {
    CohortTradeRegimeContext {
        status: "observed".into(),
        primary_regime: Some(state.into()),
        ..CohortTradeRegimeContext::default()
    }
}
