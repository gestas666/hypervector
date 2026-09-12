#[test]
fn parses_report_only_trade_regime_reflection() {
    let checkpoint = r#"{
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-03T09:15:20+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"BTC":"OPEN","ETH":"FLAT","SOL":"FLAT","HYPE":"OPEN"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 10},
            "portfolio": {"status":"observed","initial_equity_usd":503.16,"final_equity_usd":504.20,"equity_change_usd":1.04,"maximum_equity_usd":504.28,"minimum_equity_usd":503.11,"maximum_drawdown_pct":0.23,"maximum_margin_used_usd":10.52,"maximum_notional_usd":49.99,"maximum_open_positions":2,"snapshot_count":1789},
            "execution": {"closed_trades": 1, "net_pnl_usd": 0.23},
            "trade_reflections": {
                "contract": {
                    "report_only": true,
                    "execution_authority": "none",
                    "runtime_strategy_changed": false,
                    "automatic_strategy_changes": false
                },
                "closed_trades": 1,
                "performance": {
                    "scope":"compatible_profile_history",
                    "return_basis":"net_pnl_divided_by_sum_entry_margin",
                    "total":{"closed_trades":1,"wins":1,"losses":0,"breakeven":0,"win_rate_pct":100.0,"net_pnl_usd":0.232488,"entry_margin_used_usd":5.0,"net_return_on_margin_pct":4.64976,"mean_trade_return_on_margin_pct":4.64976,"profit_factor":null,"fees_usd":0.021412,"funding_usd":0.00245},
                    "by_strategy":{"hype_breakout_onset_bidirectional_v1":{"closed_trades":1,"wins":1,"losses":0,"breakeven":0,"win_rate_pct":100.0,"net_pnl_usd":0.232488,"entry_margin_used_usd":5.0,"net_return_on_margin_pct":4.64976,"mean_trade_return_on_margin_pct":4.64976,"profit_factor":null,"fees_usd":0.021412,"funding_usd":0.00245}}
                },
                "context_coverage": {"complete": true},
                "maximum_hold_context_journal": {
                    "contract": {"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false},
                    "timer_exits": 1,
                    "non_timer_exits": 0,
                    "contexts": {
                        "still_directionally_supported":{"closed_trades":0},
                        "directionally_opposed":{"closed_trades":0},
                        "mixed_or_transition":{"closed_trades":1},
                        "unavailable":{"closed_trades":0}
                    },
                    "regime_aware_extension_challenger": {
                        "contract": {"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false},
                        "decisions":{"extend":0,"exit":1,"abstain":0},
                        "horizons": {
                            "5":{"eligible_extensions":0,"resolved":0,"positive":0,"negative":0,"unchanged":0,"protective_stop_hits":0,"censored":0,"missing_data":0,"missing_protection":0,"incremental_gross_pnl_usd":0.0}
                        }
                    },
                    "aligned_zero_opposition_extension_observer": {
                        "schema_version":1,
                        "mode":"aligned_zero_opposition_timer_extension_observer_v1",
                        "contract":{"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false,"performance_gate":false,"balance_gate":false},
                        "policy":{"horizon_minutes":5,"requires_15m_context_alignment":true,"requires_complete_zero_opposition":true,"retains_protective_stop":true},
                        "decisions":{"timer_exits":1,"eligible":1,"ineligible":0,"by_reason":{"eligible":1}},
                        "horizon":{"eligible_extensions":1,"resolved":1,"positive":1,"negative":0,"unchanged":0,"protective_stop_hits":0,"censored":0,"missing_data":0,"incremental_gross_pnl_usd":0.13493},
                        "latest_observations":[{"lifecycle_id":"HYPE:508524930617","strategy_id":"hype_breakout_onset_bidirectional_v1","symbol":"HYPE","side":"short","status":"resolved","completed_decisions":480,"opposed_decisions":0,"maximum_consecutive_opposed":0,"directional_close_return_bps":18.0,"protective_stop_hit":false,"incremental_gross_pnl_usd":0.13493}]
                    },
                    "provider_symbols": [{
                        "strategy_id":"hype_breakout_onset_bidirectional_v1",
                        "symbol":"HYPE",
                        "timer_exits":1,
                        "non_timer_exits":0,
                        "contexts":{
                            "still_directionally_supported":{"closed_trades":0},
                            "directionally_opposed":{"closed_trades":0},
                            "mixed_or_transition":{"closed_trades":1},
                            "unavailable":{"closed_trades":0}
                        },
                        "regime_aware_extension_challenger":{
                            "contract":{"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false},
                            "decisions":{"extend":0,"exit":1,"abstain":0},
                            "horizons":{"5":{"eligible_extensions":0,"resolved":0,"positive":0,"negative":0,"unchanged":0,"protective_stop_hits":0,"censored":0,"missing_data":0,"missing_protection":0,"incremental_gross_pnl_usd":0.0}}
                        }
                    }]
                },
                "trades": [{
                    "lifecycle_id": "HYPE:508524930617",
                    "source_run_id": "bidirectional-live-a",
                    "source_profile_fingerprint": "current-profile-fingerprint",
                    "symbol": "HYPE",
                    "strategy_id": "hype_breakout_onset_bidirectional_v1",
                    "entry_strategy_id": "hype_breakout_onset_bidirectional_v1",
                    "exit_controller_strategy_id": "cohort_maximum_hold",
                    "cross_provider_exit": true,
                    "side": "short",
                    "exit_reason": "maximum_hold_seconds",
                    "net_pnl_usd": 0.232488,
                    "entry":{"price":52.998,"venue_timestamp_ms":1785707110461},
                    "exit":{"price":52.463,"venue_timestamp_ms":1785735911458},
                    "protective_stop":{"oid":508524948153,"trigger_price":53.421984},
                    "holding_time_ms":28800997,
                    "fees_usd":0.021412,
                    "funding_usd":0.00245,
                    "entry_margin_used_usd":5.0,
                    "leverage":5.0,
                    "price_return_pct":1.0094720555,
                    "net_return_on_margin_pct":4.64976,
                    "entry_context": {
                        "signal_provider": {"status":"observed","primary_regime":"BREAKOUT","state_1m":"TREND_UP","state_5m":"BREAKOUT","context_15m":"TREND_UP","confidence":0.76},
                        "canonical_regime": {"status":"observed","primary_regime":"BREAKOUT","state_1m":"TREND_UP","state_5m":"BREAKOUT","context_15m":"TREND_UP","confidence":0.76}
                    },
                    "entry_regime_assessment": {
                        "contract": {"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false},
                        "structure_support_score":0.75,
                        "structure_stance":"directionally_supported",
                        "component_alignment_score":0.5,
                        "component_stance":"aligned_with_position",
                        "movement_strength":0.76,
                        "maximum_hold_context":"still_directionally_supported"
                    },
                    "exit_context": {
                        "signal_provider": {"status":"observed","primary_regime":"RANGE","state_1m":"RANGE","state_5m":"RANGE","context_15m":"RANGE","confidence":0.18},
                        "canonical_regime": {"status":"observed","primary_regime":"RANGE","state_1m":"RANGE","state_5m":"RANGE","context_15m":"RANGE","confidence":0.18},
                        "exit_controller": {"status":"unavailable","primary_regime":null,"state_1m":null,"state_5m":null,"context_15m":null,"confidence":null}
                    },
                    "exit_regime_assessment": {
                        "contract": {"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false},
                        "structure_support_score":0.0,
                        "structure_weight_observed":12.0,
                        "structure_stance":"mixed_or_transition",
                        "component_alignment_score":null,
                        "component_weight_observed":0.0,
                        "component_stance":"unavailable",
                        "movement_strength":0.18,
                        "maximum_hold_context":"mixed_or_transition"
                    },
                    "entry_followthrough_path": {
                        "240": {"status":"resolved","bars_observed":240,"bars_required":240,"completion_pct":100.0,"first_candle_timestamp_ms":1785707160000,"last_candle_timestamp_ms":1785721500000,"last_close_price":52.72,"lowest_price":52.41,"highest_price":53.06,"directional_close_return_bps":52.5,"favorable_excursion_bps":111.0,"adverse_excursion_bps":11.7,"interpretation":"continued_original_direction","protective_stop_trigger_price":53.421984,"protective_stop_price_crossed":false,"first_stop_price_cross_timestamp_ms":null},
                        "2880": {"status":"censored","bars_observed":305,"bars_required":2880,"completion_pct":10.5902777778,"first_candle_timestamp_ms":1785707160000,"last_candle_timestamp_ms":1785725400000,"last_close_price":52.80,"lowest_price":52.41,"highest_price":53.06,"directional_close_return_bps":37.4,"favorable_excursion_bps":111.0,"adverse_excursion_bps":11.7,"interpretation":"continued_original_direction","protective_stop_trigger_price":53.421984,"protective_stop_price_crossed":false,"first_stop_price_cross_timestamp_ms":null}
                    },
                    "ignored_provider_exit_outcome":{"schema_version":1,"mode":"closed_ignored_provider_recipe_exit_outcome_v1","status":"observed","provider_recipe_exit_policy":"ignore","contract":{"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_promotion":false,"actual_exit_is_authoritative":true},"first_signal":{"decision_time_ms":1785725400000,"reference_price":52.8,"entry_directional_return_bps":37.36,"exit_reason":"breakout_lost","decision_action":"close_short"},"ignored_signal_count":2,"path_from_first_signal_to_actual_exit":{"status":"observed","completed_bars":175,"first_timestamp_ms":1785725460000,"last_timestamp_ms":1785735900000,"highest_price":52.9,"lowest_price":52.41,"current_directional_return_bps":63.83,"maximum_favorable_excursion_bps":73.86,"maximum_adverse_excursion_bps":18.94,"peak_giveback_bps":10.03},"gross_continuation_from_signal_bps":63.83,"counterfactual_signal_exit_net_pnl_usd":null,"actual_exit":{"venue_timestamp_ms":1785735911458,"price":52.463,"net_pnl_usd":0.232488,"fees_usd":0.021412,"funding_usd":0.00245,"exit_reason":"maximum_hold_seconds","exit_controller_strategy_id":"cohort_maximum_hold"},"limitations":["report only"]},
                    "post_exit_path": {
                        "5": {"status":"resolved","directional_close_return_bps":-11.6,"favorable_excursion_bps":7.8,"adverse_excursion_bps":14.7,"interpretation":"reversed_against_original_direction"},
                        "60": {"status":"resolved","directional_close_return_bps":83.3,"favorable_excursion_bps":110.2,"adverse_excursion_bps":66.7,"interpretation":"continued_original_direction"}
                    }
                }]
            },
            "open_trade_reflections": {
                "as_of_timestamp_ms":1785619886090,
                "contract": {
                    "report_only": true,
                    "execution_authority": "none",
                    "runtime_strategy_changed": false,
                    "automatic_strategy_changes": false
                },
                "open_lifecycles": 1,
                "trades": [{
                    "lifecycle_id": "BTC:508726900000",
                    "source_run_id": "bidirectional-live-a",
                    "symbol": "BTC",
                    "strategy_id": "hypervelocity_source_follow_bidirectional_5m_v1",
                    "side": "short",
                    "protective_stop":{"oid":508726918963,"trigger_price":63418.32},
                    "profit_protection":{"status":"open_profit_unprotected","reported_marked_net_pnl_usd":0.103396,"estimated_exit_now_net_usd":0.092,"estimated_stop_net_usd":-0.210,"marked_to_stop_giveback_usd":0.302,"protected_profit_fraction":0.0,"stop_distance_from_mark_bps":124.08,"measured_entry_fee_rate_bps":4.32,"estimated_current_exit_fee_usd":0.011396,"estimated_stop_exit_fee_usd":0.0115,"method":"measured_entry_fee_rate_no_future_funding_or_slippage"},
                    "target_order":{"oid":508726919999,"limit_price":62200.0,"directional_distance_bps":70.4},
                    "holding_time_ms": 19886090,
                    "exit_plan":{"opened_at_ms":1785600000000,"timer_origin":"persisted_runtime_opened_at","maximum_hold_seconds":28800,"deadline_timestamp_ms":1785628800000,"remaining_time_ms":8913910,"expired":false,"source":"asset_runtime_default","controller":"cohort_maximum_hold","opposite_intent_exit_scope":"selected_opposite_from_any_executable_provider_same_symbol","opposite_intent_arbitration":"regime_then_priority"},
                    "path_since_entry":{"status":"observed","completed_bars":331,"first_timestamp_ms":1785600060000,"last_timestamp_ms":1785619920000,"highest_price":63402.0,"lowest_price":62590.0,"current_directional_return_bps":43.56,"maximum_favorable_excursion_bps":51.66,"maximum_adverse_excursion_bps":77.88,"peak_giveback_bps":8.10},
                    "path_since_soft_deadline":{"status":"observed","boundary_timestamp_ms":1785628800000,"baseline_timestamp_ms":1785628740000,"baseline_price":63200.0,"completed_bars":31,"first_timestamp_ms":1785628800000,"last_timestamp_ms":1785630660000,"highest_price":63500.0,"lowest_price":63150.0,"current_directional_return_bps":12.5,"maximum_favorable_excursion_bps":47.5,"maximum_adverse_excursion_bps":7.9,"peak_giveback_bps":35.0},
                    "post_soft_trail_challenger":{"schema_version":1,"mode":"cohort_open_post_soft_trail_challenger_v1","contract":{"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false,"performance_gate":false,"balance_gate":false},"status":"observed","soft_deadline_timestamp_ms":1785628800000,"as_of_timestamp_ms":1785630720000,"baseline_timestamp_ms":1785628740000,"baseline_price":63200.0,"completed_post_soft_bars":31,"policies":{"20bps":{"giveback_bps":20.0,"status":"triggered","trigger_timestamp_ms":1785629100000,"trigger_reference_price":63373.0,"best_completed_price_before_trigger":63500.0,"active_trail_price":63373.0},"30bps":{"giveback_bps":30.0,"status":"triggered","trigger_timestamp_ms":1785629400000,"trigger_reference_price":63309.5,"best_completed_price_before_trigger":63500.0,"active_trail_price":63309.5},"40bps":{"giveback_bps":40.0,"status":"armed_not_triggered","trigger_timestamp_ms":null,"trigger_reference_price":null,"best_completed_price":63500.0,"active_trail_price":63246.0}}},
                    "open_profit_lock_challenger":{"schema_version":1,"mode":"cohort_open_profit_lock_challenger_v1","contract":{"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false,"automatic_promotion":false},"status":"observed","entry_timestamp_ms":1785600030000,"as_of_timestamp_ms":1785619920000,"completed_bars_expected":331,"completed_bars_observed":331,"policy_origin":"existing_predeclared_hype_profit_research_v1","policies":{"a25_floor15_trail10":{"policy_id":"a25_floor15_trail10","activation_bps":25.0,"floor_bps":15.0,"trailing_giveback_bps":10.0,"status":"triggered_before_current_boundary","activation_timestamp_ms":1785606000000,"trigger_timestamp_ms":1785606120000,"trigger_reference_price":62652.59,"stop_price_before_trigger":62652.59,"best_completed_price_before_trigger":62590.0,"best_completed_price":null,"active_stop_price":null},"a40_floor15_trail20":{"policy_id":"a40_floor15_trail20","activation_bps":40.0,"floor_bps":15.0,"trailing_giveback_bps":20.0,"status":"armed_not_triggered","activation_timestamp_ms":1785607200000,"trigger_timestamp_ms":null,"trigger_reference_price":null,"stop_price_before_trigger":null,"best_completed_price_before_trigger":null,"best_completed_price":62590.0,"active_stop_price":62715.18},"a60_floor15_trail30":{"policy_id":"a60_floor15_trail30","activation_bps":60.0,"floor_bps":15.0,"trailing_giveback_bps":30.0,"status":"not_activated","activation_timestamp_ms":null,"trigger_timestamp_ms":null,"trigger_reference_price":null,"stop_price_before_trigger":null,"best_completed_price_before_trigger":null,"best_completed_price":62590.0,"active_stop_price":null}}},
                    "ignored_provider_exit_observer":{"schema_version":1,"mode":"ignored_provider_recipe_exit_observer_v1","status":"observed","provider_recipe_exit_policy":"ignore","ignored_signal_count":5,"contract":{"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_promotion":false},"first_signal":{"decision_time_ms":1785606000000,"reference_price":62950.0,"entry_directional_return_bps":-5.56,"exit_reason":"source_direction_lost","decision_action":"close_short","readiness":{"conditions_met":2,"conditions_required":4,"blockers":["source_not_short"]}},"path_since_first_signal":{"status":"observed","completed_bars":231,"first_timestamp_ms":1785606060000,"last_timestamp_ms":1785619920000,"highest_price":63402.0,"lowest_price":62590.0,"current_directional_return_bps":49.09,"maximum_favorable_excursion_bps":57.19,"maximum_adverse_excursion_bps":71.80,"peak_giveback_bps":8.10},"limitations":["report only"]},
                    "entry_context": {
                        "signal_provider": {"status":"observed","primary_regime":"TREND_DOWN","state_1m":null,"state_5m":"TREND_DOWN","context_15m":null,"confidence":0.90,"readiness":{"metrics":{"breakout_side":"short","structural_direction":"short","breakout_side_relation":"aligned"}}},
                        "canonical_regime": {"status":"observed","primary_regime":"TREND_DOWN","state_1m":"TREND_DOWN","state_5m":"TREND_DOWN","context_15m":"BREAKOUT","confidence":0.81}
                    },
                    "entry_regime_assessment": {
                        "contract": {"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false},
                        "structure_support_score":0.8333333333,
                        "structure_stance":"directionally_supported",
                        "component_alignment_score":0.5555555556,
                        "component_stance":"aligned_with_position",
                        "movement_strength":0.81,
                        "maximum_hold_context":"still_directionally_supported"
                    },
                    "current_context": {
                        "signal_provider": {"status":"observed","primary_regime":"TRANSITION","state_1m":null,"state_5m":"TRANSITION","context_15m":null,"confidence":0.53},
                        "canonical_regime": {"status":"observed","primary_regime":"TREND_DOWN","state_1m":"TREND_UP","state_5m":"TREND_DOWN","context_15m":"TREND_DOWN","confidence":0.82}
                    },
                    "regime_drift": {"signal_provider_changed":true,"canonical_regime_changed":false},
                    "regime_assessment": {
                        "contract": {"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false},
                        "structure_support_score":0.5833333333,
                        "structure_weight_observed":12.0,
                        "structure_stance":"directionally_supported",
                        "component_alignment_score":-0.7777777778,
                        "component_weight_observed":9.0,
                        "component_stance":"opposing_position",
                        "movement_strength":0.82,
                        "maximum_hold_context":"still_directionally_supported"
                    },
                    "regime_opposition_episode": {
                        "schema_version":1,
                        "mode":"causal_regime_opposition_persistence_v1",
                        "contract":{"report_only":true,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false},
                        "opposition_threshold":-0.5,
                        "persistence_decisions":[1,3,5],
                        "entry_timestamp_ms":1785600030000,
                        "end_timestamp_ms":1785619916090,
                        "completed_decisions":331,
                        "unavailable_decisions":0,
                        "coverage_gap_decisions":0,
                        "opposed_decisions":73,
                        "first_opposed_decision_ms":1785606000000,
                        "last_decision_ms":1785619860000,
                        "latest_structure_support_score":-0.5833333333,
                        "maximum_consecutive_opposed":73,
                        "current_consecutive_opposed":73,
                        "current_active":true,
                        "persistence_triggers":{"1":1785606000000,"3":1785606120000,"5":1785606240000}
                    },
                    "marked_economics": {"mark_price":62641.0,"active_lifecycle_marked_net_pnl_usd":0.103396}
                }]
            },
            "learning": {"evidence_state": "descriptive_trade_evidence"}
        }
    }"#;

    let parsed = parse_cohort_checkpoint(checkpoint).expect("valid reflection");

    assert_eq!(parsed.trade_reflection_context_complete, Some(true));
    let timer = parsed
        .timer_context_evidence
        .as_ref()
        .expect("timer context evidence");
    assert_eq!(timer.timer_exits, 1);
    assert_eq!(timer.mixed_or_transition, 1);
    assert_eq!(timer.still_directionally_supported, 0);
    assert_eq!(timer.challenger_extend, Some(0));
    assert_eq!(timer.challenger_exit, Some(1));
    assert_eq!(timer.challenger_abstain, Some(0));
    assert_eq!(timer.provider_symbols.len(), 1);
    assert_eq!(timer.provider_symbols[0].symbol, "HYPE");
    assert_eq!(timer.provider_symbols[0].challenger_exit, Some(1));
    let five = timer
        .challenger_five_minute
        .as_ref()
        .expect("five-minute extension challenger");
    assert_eq!(five.eligible_extensions, 0);
    assert_eq!(five.protective_stop_hits, 0);
    assert_eq!(five.missing_protection, 0);
    assert_eq!(five.incremental_gross_pnl_usd, 0.0);
    let aligned = timer
        .aligned_zero_opposition_five_minute
        .as_ref()
        .expect("aligned zero-opposition five-minute observer");
    assert_eq!(aligned.timer_exits, 1);
    assert_eq!(aligned.eligible, 1);
    assert_eq!(aligned.ineligible, 0);
    assert_eq!(aligned.resolved, 1);
    assert_eq!(aligned.positive, 1);
    assert_eq!(aligned.negative, 0);
    assert_eq!(aligned.protective_stop_hits, 0);
    assert_eq!(aligned.incremental_gross_pnl_usd, 0.13493);
    assert_eq!(parsed.trade_reflections.len(), 1);
    let reflection = &parsed.trade_reflections[0];
    assert_eq!(
        reflection.source_profile_fingerprint.as_deref(),
        Some("current-profile-fingerprint")
    );
    assert_eq!(reflection.symbol, "HYPE");
    assert_eq!(reflection.side, "short");
    assert_eq!(
        reflection.exit_controller_strategy_id,
        "cohort_maximum_hold"
    );
    assert!(reflection.cross_provider_exit);
    assert_eq!(reflection.entry_price, Some(52.998));
    assert_eq!(reflection.exit_price, Some(52.463));
    assert_eq!(reflection.protective_stop_oid, Some(508_524_948_153));
    assert_eq!(reflection.protective_stop_price, Some(53.421984));
    assert_eq!(reflection.net_return_on_margin_pct, Some(4.64976));
    let ignored = reflection
        .ignored_provider_exit_outcome
        .as_ref()
        .expect("closed ignored-exit outcome");
    assert_eq!(ignored.status, "observed");
    assert_eq!(ignored.ignored_signal_count, 2);
    assert_eq!(ignored.gross_continuation_from_signal_bps, Some(63.83));
    assert_eq!(ignored.actual_exit.net_pnl_usd, 0.232488);
    assert_eq!(ignored.actual_exit.fees_usd, 0.021412);
    assert_eq!(ignored.counterfactual_signal_exit_net_pnl_usd, None);
    let performance = parsed
        .trade_performance
        .as_ref()
        .expect("trade performance");
    assert_eq!(performance.total.wins, 1);
    assert_eq!(performance.total.losses, 0);
    assert_eq!(performance.total.win_rate_pct, Some(100.0));
    assert_eq!(performance.total.net_pnl_usd, 0.232488);
    assert_eq!(performance.total.net_return_on_margin_pct, Some(4.64976));
    assert_eq!(performance.total.profit_factor, None);
    assert_eq!(performance.by_strategy.len(), 1);
    let portfolio = parsed.portfolio.as_ref().expect("portfolio evidence");
    assert_eq!(portfolio.initial_equity_usd, 503.16);
    assert_eq!(portfolio.equity_change_usd, 1.04);
    assert_eq!(portfolio.maximum_drawdown_pct, 0.23);
    assert_eq!(portfolio.maximum_open_positions, 2);
    assert_eq!(
        reflection.entry_canonical.primary_regime.as_deref(),
        Some("BREAKOUT")
    );
    assert_eq!(
        reflection.exit_canonical.primary_regime.as_deref(),
        Some("RANGE")
    );
    assert_eq!(
        reflection.post_exit_paths[&5].interpretation.as_deref(),
        Some("reversed_against_original_direction")
    );
    let four_hours = &reflection.entry_followthrough_paths[&240];
    assert_eq!(four_hours.status, "resolved");
    assert_eq!(four_hours.bars_observed, 240);
    assert_eq!(four_hours.bars_required, 240);
    assert_eq!(four_hours.directional_close_return_bps, Some(52.5));
    assert_eq!(four_hours.protective_stop_price_crossed, Some(false));
    let forty_eight_hours = &reflection.entry_followthrough_paths[&2_880];
    assert_eq!(forty_eight_hours.status, "censored");
    assert_eq!(forty_eight_hours.bars_observed, 305);
    assert_eq!(reflection.exit_structure_support_score, Some(0.0));
    assert_eq!(reflection.entry_structure_support_score, Some(0.75));
    assert_eq!(reflection.entry_component_alignment_score, Some(0.5));
    assert_eq!(reflection.entry_component_stance, "aligned_with_position");
    assert_eq!(reflection.entry_movement_strength, Some(0.76));
    assert_eq!(
        reflection.entry_maximum_hold_context,
        "still_directionally_supported"
    );
    assert_eq!(reflection.exit_maximum_hold_context, "mixed_or_transition");
    assert_eq!(parsed.open_trade_reflections.len(), 1);
    let open = &parsed.open_trade_reflections[0];
    assert_eq!(open.exit_plan.as_of_timestamp_ms, Some(1_785_619_886_090));
    assert_eq!(open.exit_plan.opened_at_ms, Some(1_785_600_000_000));
    assert_eq!(open.exit_plan.timer_origin.as_deref(), Some("persisted_runtime_opened_at"));
    assert_eq!(open.symbol, "BTC");
    assert_eq!(open.protective_stop_oid, Some(508_726_918_963));
    assert_eq!(open.protective_stop_price, Some(63_418.32));
    let protection = open
        .profit_protection
        .as_ref()
        .expect("profit protection evidence");
    assert_eq!(protection.status, "open_profit_unprotected");
    assert_eq!(protection.estimated_exit_now_net_usd, 0.092);
    assert_eq!(protection.estimated_stop_net_usd, -0.210);
    assert_eq!(protection.marked_to_stop_giveback_usd, 0.302);
    assert_eq!(open.target_order_oid, Some(508_726_919_999));
    assert_eq!(open.target_order_price, Some(62_200.0));
    assert_eq!(open.target_directional_distance_bps, Some(70.4));
    assert_eq!(open.exit_plan.maximum_hold_seconds, 28_800);
    assert_eq!(open.exit_plan.provider_recipe_exit_policy, "ignore");
    assert_eq!(open.exit_plan.deadline_timestamp_ms, 1_785_628_800_000);
    assert_eq!(open.exit_plan.remaining_time_ms, 8_913_910);
    assert_eq!(open.exit_plan.source, "asset_runtime_default");
    assert_eq!(
        open.exit_plan.opposite_intent_exit_scope,
        "selected_opposite_from_any_executable_provider_same_symbol"
    );
    assert_eq!(
        open.exit_plan.opposite_intent_arbitration,
        "regime_then_priority"
    );
    assert_eq!(open.path_since_entry.completed_bars, 331);
    assert_eq!(
        open.path_since_entry.current_directional_return_bps,
        Some(43.56)
    );
    assert_eq!(
        open.path_since_entry.maximum_favorable_excursion_bps,
        Some(51.66)
    );
    assert_eq!(open.path_since_entry.peak_giveback_bps, Some(8.10));
    let extension = open
        .path_since_soft_deadline
        .as_ref()
        .expect("post-soft path");
    assert_eq!(extension.boundary_timestamp_ms, 1_785_628_800_000);
    assert_eq!(extension.baseline_timestamp_ms, Some(1_785_628_740_000));
    assert_eq!(extension.baseline_price, Some(63_200.0));
    assert_eq!(extension.completed_bars, 31);
    assert_eq!(extension.first_timestamp_ms, Some(1_785_628_800_000));
    assert_eq!(extension.current_directional_return_bps, Some(12.5));
    assert_eq!(extension.maximum_favorable_excursion_bps, Some(47.5));
    assert_eq!(extension.maximum_adverse_excursion_bps, Some(7.9));
    assert_eq!(extension.peak_giveback_bps, Some(35.0));
    let trail = open
        .post_soft_trail_challenger
        .as_ref()
        .expect("open post-soft trail");
    assert_eq!(trail.status, "observed");
    assert_eq!(trail.policies[&20].status, "triggered");
    assert_eq!(trail.policies[&40].status, "armed_not_triggered");
    let lock = open
        .open_profit_lock_challenger
        .as_ref()
        .expect("open profit-lock challenger");
    assert_eq!(lock.status, "observed");
    assert_eq!(lock.completed_bars_expected, 331);
    assert_eq!(lock.completed_bars_observed, 331);
    assert_eq!(
        lock.policies["a25_floor15_trail10"].status,
        "triggered_before_current_boundary"
    );
    assert_eq!(
        lock.policies["a40_floor15_trail20"].status,
        "armed_not_triggered"
    );
    assert_eq!(lock.policies["a60_floor15_trail30"].status, "not_activated");
    let ignored = open
        .ignored_provider_exit_observer
        .as_ref()
        .expect("ignored provider exit observer");
    assert_eq!(ignored.status, "observed");
    assert_eq!(ignored.provider_recipe_exit_policy, "ignore");
    assert_eq!(ignored.ignored_signal_count, 5);
    let signal = ignored.first_signal.as_ref().expect("first ignored signal");
    assert_eq!(signal.decision_time_ms, 1_785_606_000_000);
    assert_eq!(signal.exit_reason, "source_direction_lost");
    assert_eq!(signal.entry_directional_return_bps, -5.56);
    let path = ignored
        .path_since_first_signal
        .as_ref()
        .expect("ignored signal path");
    assert_eq!(path.current_directional_return_bps, Some(49.09));
    assert_eq!(
        open.entry_signal.primary_regime.as_deref(),
        Some("TREND_DOWN")
    );
    assert_eq!(open.entry_signal.breakout_side.as_deref(), Some("short"));
    assert_eq!(
        open.entry_signal.structural_direction.as_deref(),
        Some("short")
    );
    assert_eq!(
        open.entry_signal.breakout_side_relation.as_deref(),
        Some("aligned")
    );
    assert_eq!(
        open.current_signal.primary_regime.as_deref(),
        Some("TRANSITION")
    );
    assert_eq!(open.canonical_regime_changed, Some(false));
    assert_eq!(open.structure_stance, "directionally_supported");
    assert_eq!(open.entry_structure_support_score, Some(0.8333333333));
    assert_eq!(open.structure_support_score, Some(0.5833333333));
    let opposition = open.regime_opposition.as_ref().expect("opposition episode");
    assert_eq!(opposition.current_consecutive_opposed, 73);
    assert_eq!(opposition.maximum_consecutive_opposed, 73);
    assert_eq!(
        opposition.trigger_five_decisions_ms,
        Some(1_785_606_240_000)
    );
    assert_eq!(open.component_stance, "opposing_position");
    assert_eq!(open.maximum_hold_context, "still_directionally_supported");
    assert_eq!(open.active_lifecycle_marked_net_pnl_usd, 0.103396);
}
