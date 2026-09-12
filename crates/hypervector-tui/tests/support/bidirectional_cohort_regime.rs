#[test]
fn projects_shared_account_assets_costs_and_router_outcomes() {
    let backend = cohort_backend();
    assert!(backend.is_multi_asset_cohort());
    assert_eq!(backend.cohort.enabled_symbols, SYMBOLS);
    assert_eq!(
        backend.cohort.assets[0].position_side.as_deref(),
        Some("long")
    );
    assert_eq!(backend.cohort.assets[0].liquidation_price, Some(82.0));
    assert_eq!(backend.cohort.assets[0].target_oid, Some(13));
    assert_eq!(
        backend.cohort.assets[0]
            .execution_plan
            .as_ref()
            .map(|plan| plan.strategy_id.as_str()),
        Some("hulk_expansion_bidirectional_tuned_v2")
    );
    assert_eq!(
        backend.cohort.actions[0].strategy_id,
        "range_onset_bidirectional_v1"
    );
    assert_eq!(
        backend.cohort.actions[0].regime_alignment_score,
        Some(0.6666666667)
    );
    assert_eq!(
        backend.cohort.actions[0].regime_alignment_stance.as_deref(),
        Some("directionally_supported")
    );
    assert_eq!(
        backend.cohort.withheld[0].regime_alignment_score,
        Some(-0.6666666667)
    );
    assert_eq!(
        backend
            .cohort
            .routing_policy
            .as_ref()
            .map(|policy| policy.mode.as_str()),
        Some("same_symbol_conflict_preference_v1")
    );
    assert_eq!(
        backend.cohort.withheld[0].reason,
        "portfolio_position_capacity"
    );
    assert_eq!(backend.cohort.evaluations.len(), 4);
    assert_eq!(backend.cohort.regime_history.len(), 1);
    assert_eq!(backend.cohort.evaluations[0].reason, "no_trigger");
    assert_eq!(backend.cohort.maximum_concurrent_positions, 4);
    assert_eq!(
        backend.cohort.providers[0].execution_symbols,
        Some(SYMBOLS.map(str::to_string).to_vec())
    );
    assert_eq!(
        backend.cohort.providers[1].execution_symbols,
        Some(SYMBOLS.map(str::to_string).to_vec())
    );
    let sol_sizing = &backend.cohort.providers[1].sizing_overrides["SOL"];
    assert_eq!(sol_sizing.margin_fraction, 0.06);
    assert_eq!(sol_sizing.max_notional_usd, 20.0);
    assert_eq!(
        backend.cohort.providers[2].source_profile.as_deref(),
        Some(
            "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow.toml"
        )
    );
    assert_eq!(
        backend.cohort.providers[3].execution_symbols,
        Some(vec!["HYPE".to_string()])
    );
    assert_eq!(backend.cohort.strategy_evidence.len(), 10);
    assert_eq!(
        backend.cohort.strategy_evidence[6].research_state,
        "historical_candidate"
    );
    assert_eq!(backend.cohort.fills[0].trade_id, 101);
    assert_eq!(backend.cohort.books["BTC"].bids.len(), 2);
    let btc_candles = &backend.cohort.candle_history["BTC"];
    assert_eq!(btc_candles.len(), 3);
    assert_eq!(btc_candles[1].open, 101.0);
    assert_eq!(btc_candles[1].high, 103.0);
    assert_eq!(btc_candles[1].low, 98.0);
    assert_eq!(btc_candles[1].close, 99.0);
}

#[test]
fn incomplete_regime_routing_preference_is_rejected() {
    let mut event: Value = serde_json::from_str(&routing()).expect("routing row");
    event["payload"]["actions"][0]["regime_alignment_basis"] = Value::Null;
    let ledger = format!("{}\n{}\n", identity(), event);

    let error = parse_backend_telemetry(&ledger).expect_err("incomplete preference accepted");
    let message = error.to_string();

    assert!(
        message.contains("regime routing preference is incomplete"),
        "{message}"
    );
}

#[test]
fn dedicated_regime_screen_projects_backend_multitimeframe_and_range_evidence() {
    let mut app = cohort_app();
    app.selected_cohort_symbol_index = 2;
    app.backend.cohort_checkpoint = CohortCheckpointTelemetry {
        configured: true,
        available: true,
        forward_evaluations: Some(7),
        five_minute_paths_resolved: Some(4),
        five_minute_paths_independent: Some(2),
        forward_path_coverage_complete: Some(true),
        trade_reflection_context_complete: Some(true),
        timer_context_evidence: Some(CohortTimerContextEvidence {
            timer_exits: 1,
            non_timer_exits: 1,
            still_directionally_supported: 0,
            directionally_opposed: 0,
            mixed_or_transition: 1,
            unavailable: 0,
            challenger_extend: Some(0),
            challenger_exit: Some(1),
            challenger_abstain: Some(0),
            challenger_five_minute: None,
            aligned_zero_opposition_five_minute: Some(CohortAlignedTimerExtensionEvidence {
                timer_exits: 1,
                eligible: 1,
                ineligible: 0,
                resolved: 1,
                positive: 1,
                negative: 0,
                unchanged: 0,
                protective_stop_hits: 0,
                censored: 0,
                missing_data: 0,
                incremental_gross_pnl_usd: 0.13,
            }),
            provider_symbols: vec![CohortTimerProviderEvidence {
                strategy_id: "hype_breakout_onset_bidirectional_v1".into(),
                symbol: "HYPE".into(),
                timer_exits: 1,
                mixed_or_transition: 1,
                challenger_exit: Some(1),
                ..CohortTimerProviderEvidence::default()
            }],
        }),
        regime_conflicts: Some(CohortRegimeConflictEvidence {
            state: "active".into(),
            conflicts: 4,
            changed_static_choice: 3,
            directionally_comparable: 2,
            same_direction_provider_only: 1,
            five_minute: Some(CohortRegimeConflictHorizon {
                resolved: 2,
                independent: 2,
                censored: 1,
                missing_data: 0,
                regime_wins: 1,
                static_wins: 1,
                ties: 0,
                mean_advantage_bps: Some(1.5),
            }),
            evidence_state: "early_directional_evidence".into(),
        }),
        trade_reflections: vec![regime_trade_reflection()],
        open_trade_reflections: vec![open_regime_trade_reflection()],
        ..CohortCheckpointTelemetry::default()
    };
    let screen = render(&mut app, 7, 165, 46);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("165x46 REGIME\n{screen}");
        println!("120x36 REGIME\n{}", render(&mut app, 7, 120, 36));
        println!("100x28 REGIME\n{}", render(&mut app, 7, 100, 28));
    }

    assert!(screen.contains("[8] REGIME"), "{screen}");
    let thick_meter_rows = screen.lines().filter(|line| line.contains("████")).count();
    assert!(
        thick_meter_rows >= 8,
        "regime meters are still hairline\n{screen}"
    );
    assert!(screen.contains("REGIME COMMAND DECK"), "{screen}");
    assert!(screen.contains("MULTI-TIMEFRAME STATE MATRIX"), "{screen}");
    assert!(screen.contains("RANGE DETECTOR"), "{screen}");
    assert!(
        screen.contains("COMPRESSION + BREAKOUT ENGINE // SOL"),
        "{screen}"
    );
    assert!(screen.contains("5M VERDICT RANGE"), "{screen}");
    assert!(
        screen.contains("WHY RANGE BBWP COILING WEAK GAP"),
        "{screen}"
    );
    assert!(screen.contains("BBWP 12.0% < 25.0%"), "{screen}");
    assert!(screen.contains("EMA GAP +0.8bps < 5.0bps"), "{screen}");
    assert!(screen.contains("TREND STRENGTH 18%"), "{screen}");
    assert!(
        screen.contains("MOVE STRENGTH 62.0% // NOT PROBABILITY"),
        "{screen}"
    );
    assert!(screen.contains("STATE AGE 1 BAR(S)"), "{screen}");
    assert!(screen.contains("RG1 TU0 TD0 BK0 TR0"), "{screen}");
    assert!(
        screen.contains("TREND STACK // SOL // CONFLICT"),
        "{screen}"
    );
    assert!(screen.contains("DECISION"), "{screen}");
    assert!(
        screen.contains("BTC          PROVIDER ONLY READY=67%"),
        "{screen}"
    );
    assert!(!screen.contains("BTC   N/A          NON-RANGE"), "{screen}");
    assert!(screen.contains("1M"), "{screen}");
    assert!(screen.contains("5M"), "{screen}");
    assert!(screen.contains("15M"), "{screen}");
    assert!(screen.contains("SOL"), "{screen}");
    assert!(screen.contains("RANGE"), "{screen}");
    assert!(screen.contains("TREND_UP"), "{screen}");
    assert!(screen.contains("NEXT 5M REGIME NOT ADMITTED"), "{screen}");
    assert!(screen.contains("L2 OPI +0.20 BID"), "{screen}");
    assert!(screen.contains("EMA +12.4"), "{screen}");
    assert!(screen.contains("CIPHER +1.0"), "{screen}");
    assert!(screen.contains("HA-RSI -1.0"), "{screen}");
    assert!(screen.contains("CHOP 48.2"), "{screen}");
    assert!(screen.contains("MTF 5M +2.0"), "{screen}");
    assert!(screen.contains("R² 0.72"), "{screen}");
    assert!(screen.contains("TQI 0.61"), "{screen}");
    assert!(screen.contains("LABEL TAPE"), "{screen}");
    assert!(
        screen.contains("LAST CLOSED // REGIME REFLECTION"),
        "{screen}"
    );
    assert!(screen.contains("HYPE S +0.23 MAXH C:MIX"), "{screen}");
    assert!(screen.contains("ENTRY S:BREAKOUT C:BREAKOUT"), "{screen}");
    assert!(screen.contains("C:BREAKOUT A+0.75"), "{screen}");
    assert!(screen.contains("ENTRY COMPONENT +0.50 ALIGNED"), "{screen}");
    assert!(screen.contains("EXIT  S:RANGE C:RANGE"), "{screen}");
    assert!(screen.contains("5M -11.6bps REVERSED"), "{screen}");
    assert!(screen.contains("OPEN SNAP //"), "{screen}");
    assert!(screen.contains("BK:S STR:S ALIGNED"), "{screen}");
    assert!(screen.contains("BTC S 5.5h"), "{screen}");
    assert!(screen.contains("S#508726918963@63418.32"), "{screen}");
    assert!(
        screen.contains("RISK $0.30 NOW+$0.09 STOP-$0.21 LOCK0%"),
        "{screen}"
    );
    assert!(
        screen.contains("TGT#508726919999 @62200.00 70.4bps"),
        "{screen}"
    );
    assert!(screen.contains("RX:I PL:OFF FIX2."), "{screen}");
    assert!(screen.contains("RX:I"), "{screen}");
    assert!(screen.contains("XPROV"), "{screen}");
    assert!(
        screen.contains("BK:S STR:S ALIGNED | RX5 LOST +49.1"),
        "{screen}"
    );
    assert!(screen.contains("N+43.6 CMFE+51.7"), "{screen}");
    assert!(screen.contains("CMAE77.9 G8.1"), "{screen}");
    assert!(
        screen.contains("SOFT+12.5 MFE47.5 MAE7.9 G35.0"),
        "{screen}"
    );
    assert!(screen.contains("T20 HIT T30 HIT T40 ARMED"), "{screen}");
    assert!(
        screen.contains("LOCK H25@62652.59/+1.20 A40@62715.18 W60"),
        "{screen}"
    );
    assert!(screen.contains("OPP 4/7"), "{screen}");
    assert!(screen.contains("N+0.10"), "{screen}");
    assert!(screen.contains("E+0.83"), "{screen}");
    assert!(screen.contains("R+0.58"), "{screen}");
    assert!(screen.contains("ROUTING ARBITRATION"), "{screen}");
    assert!(
        screen.contains("CONFLICT 4  CHANGED 3  COMP 2  SAME 1"),
        "{screen}"
    );
    assert!(screen.contains("R/S/T 1/1/0  Δ +1.50bps"), "{screen}");
    assert!(screen.contains("REPORT ONLY // AUTHORITY NONE"), "{screen}");
    assert!(screen.contains("TMR1 P1 S0/O0/M1/U0"), "{screen}");
    assert!(screen.contains("K0/EXIT1/W0"), "{screen}");
    assert!(
        screen.contains("ALN0P 5M E1 R1 +1/-0 ST0 ΔG +0.13"),
        "{screen}"
    );
    assert!(screen.contains("FWD 7 // 5M 4/2 // COV OK"), "{screen}");
    let wide = render(&mut app, 7, 300, 60);
    assert!(wide.contains("TMR SUPPORT"), "{wide}");
    assert!(wide.contains("RECIPE EXIT IGNORE"), "{wide}");
    assert!(wide.contains("PROFIT LOCK OFF"), "{wide}");
    assert!(!wide.contains("8H SUPPORT"), "{wide}");
    let compact = render(&mut app, 7, 120, 36);
    assert!(compact.contains("LABEL TAPE"), "{compact}");
    assert!(compact.contains("ROUTING ARBITRATION"), "{compact}");
    assert!(compact.contains("R/S/T 1/1/0"), "{compact}");
    assert!(compact.contains("FWD 7 // 5M 4/2 // COV OK"), "{compact}");
    assert!(compact.contains("RX:I"), "{compact}");
    assert!(compact.contains("[←/→] Coin"), "{compact}");
    let minimum = render(&mut app, 7, 100, 28);
    assert!(minimum.contains("5M VERDICT RANGE"), "{minimum}");
    assert!(minimum.contains("WHY RANGE"), "{minimum}");
    assert!(
        minimum.contains("MOVE STRENGTH 62.0% // NOT PROBABILITY"),
        "{minimum}"
    );
    assert!(minimum.contains("[←/→] Coin"), "{minimum}");
    app.show_cohort_fill_modal = true;
    let detail = render(&mut app, 4, 165, 46);
    assert!(
        detail.contains("POST-ENTRY 4H  RESOLVED  240/240  RETURN +52.50bps  STOP PX CLEAR"),
        "{detail}"
    );
    assert!(
        detail
            .contains("POST-ENTRY 48H  CENSORED  305/2880  RETURN +37.40bps  STOP PX CLEAR SO FAR"),
        "{detail}"
    );
}

fn regime_trade_reflection() -> CohortTradeReflection {
    let entry = CohortTradeRegimeContext {
        status: "observed".into(),
        primary_regime: Some("BREAKOUT".into()),
        state_1m: Some("TREND_UP".into()),
        state_5m: Some("BREAKOUT".into()),
        context_15m: Some("TREND_UP".into()),
        confidence: Some(0.76),
        breakout_side: None,
        structural_direction: None,
        breakout_side_relation: None,
    };
    let exit = CohortTradeRegimeContext {
        status: "observed".into(),
        primary_regime: Some("RANGE".into()),
        state_1m: Some("RANGE".into()),
        state_5m: Some("RANGE".into()),
        context_15m: Some("RANGE".into()),
        confidence: Some(0.18),
        breakout_side: None,
        structural_direction: None,
        breakout_side_relation: None,
    };
    CohortTradeReflection {
        lifecycle_id: "HYPE:508524930617".into(),
        source_run_id: "bidirectional-live-a".into(),
        source_profile_fingerprint: None,
        symbol: "HYPE".into(),
        strategy_id: "hype_breakout_onset_bidirectional_v1".into(),
        exit_controller_strategy_id: "cohort_maximum_hold".into(),
        cross_provider_exit: true,
        side: "short".into(),
        exit_reason: Some("maximum_hold_seconds".into()),
        net_pnl_usd: 0.232488,
        entry_price: Some(52.998),
        exit_price: Some(52.463),
        entry_venue_timestamp_ms: Some(1_785_707_110_461),
        exit_venue_timestamp_ms: Some(1_785_735_911_458),
        protective_stop_oid: Some(508_524_948_153),
        protective_stop_price: Some(53.421984),
        holding_time_ms: Some(28_800_997),
        fees_usd: Some(0.021412),
        funding_usd: Some(0.00245),
        entry_margin_used_usd: Some(5.0),
        leverage: Some(5.0),
        price_return_pct: Some(1.00947),
        net_return_on_margin_pct: Some(4.64976),
        entry_signal: entry.clone(),
        entry_canonical: entry,
        entry_structure_support_score: Some(0.75),
        entry_structure_stance: "directionally_supported".into(),
        entry_component_alignment_score: Some(0.5),
        entry_component_stance: "aligned_with_position".into(),
        entry_movement_strength: Some(0.76),
        entry_maximum_hold_context: "still_directionally_supported".into(),
        exit_signal: exit.clone(),
        exit_canonical: exit.clone(),
        exit_controller: exit,
        exit_structure_support_score: Some(0.0),
        exit_structure_stance: "mixed_or_transition".into(),
        exit_component_alignment_score: None,
        exit_component_stance: "unavailable".into(),
        exit_movement_strength: Some(0.18),
        exit_maximum_hold_context: "mixed_or_transition".into(),
        regime_opposition: None,
        entry_followthrough_paths: BTreeMap::from([
            (
                240,
                CohortTradeEntryFollowthroughPath {
                    status: "resolved".into(),
                    bars_observed: 240,
                    bars_required: 240,
                    completion_pct: 100.0,
                    directional_close_return_bps: Some(52.5),
                    favorable_excursion_bps: Some(111.0),
                    adverse_excursion_bps: Some(11.7),
                    protective_stop_price_crossed: Some(false),
                    first_stop_price_cross_timestamp_ms: None,
                },
            ),
            (
                2_880,
                CohortTradeEntryFollowthroughPath {
                    status: "censored".into(),
                    bars_observed: 305,
                    bars_required: 2_880,
                    completion_pct: 10.5902777778,
                    directional_close_return_bps: Some(37.4),
                    favorable_excursion_bps: Some(111.0),
                    adverse_excursion_bps: Some(11.7),
                    protective_stop_price_crossed: Some(false),
                    first_stop_price_cross_timestamp_ms: None,
                },
            ),
        ]),
        completed_hold_capture: None,
        ignored_provider_exit_outcome: Some(CohortClosedIgnoredProviderExit {
            status: "observed".into(),
            provider_recipe_exit_policy: Some("ignore".into()),
            ignored_signal_count: 3,
            first_signal: Some(CohortIgnoredProviderExitSignal {
                decision_time_ms: 1_785_727_200_000,
                reference_price: 52.8,
                entry_directional_return_bps: 37.36,
                exit_reason: "source_direction_lost".into(),
                decision_action: Some("close_short".into()),
            }),
            path_from_first_signal_to_actual_exit: Some(CohortOpenPath {
                status: "resolved".into(),
                completed_bars: 145,
                current_directional_return_bps: Some(63.83),
                ..CohortOpenPath::default()
            }),
            gross_continuation_from_signal_bps: Some(63.83),
            counterfactual_signal_exit_net_pnl_usd: None,
            actual_exit: CohortIgnoredProviderActualExit {
                venue_timestamp_ms: 1_785_735_911_458,
                price: 52.463,
                net_pnl_usd: 0.232488,
                fees_usd: 0.021412,
                funding_usd: 0.00245,
                exit_reason: Some("maximum_hold_seconds".into()),
                exit_controller_strategy_id: "cohort_maximum_hold".into(),
            },
        }),
        post_exit_paths: BTreeMap::from([
            (
                5,
                CohortTradeExitPath {
                    status: "resolved".into(),
                    directional_close_return_bps: Some(-11.6),
                    favorable_excursion_bps: Some(7.8),
                    adverse_excursion_bps: Some(14.7),
                    interpretation: Some("reversed_against_original_direction".into()),
                },
            ),
            (
                60,
                CohortTradeExitPath {
                    status: "resolved".into(),
                    directional_close_return_bps: Some(83.3),
                    favorable_excursion_bps: Some(110.2),
                    adverse_excursion_bps: Some(66.7),
                    interpretation: Some("continued_original_direction".into()),
                },
            ),
        ]),
    }
}
