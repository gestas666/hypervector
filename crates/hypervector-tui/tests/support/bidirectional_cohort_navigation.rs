#[test]
fn hip3_symbols_remain_distinct_in_trade_and_research_tables_at_acceptance_width() {
    let symbols = [
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:GOLD",
        "xyz:BRENTOIL",
    ];
    let mut app = complete_portfolio_app();
    let asset = app.backend.cohort.assets[0].clone();
    app.backend.cohort.assets = symbols
        .iter()
        .map(|symbol| {
            let mut row = asset.clone();
            row.symbol = (*symbol).into();
            row
        })
        .collect();
    let fill = app.backend.cohort.fills[0].clone();
    app.backend.cohort.fills = symbols
        .iter()
        .map(|symbol| {
            let mut row = fill.clone();
            row.symbol = (*symbol).into();
            row
        })
        .collect();
    let mut checkpoint = trade_checkpoint();
    let trade = checkpoint.trade_reflections[0].clone();
    checkpoint.trade_reflections = symbols
        .iter()
        .map(|symbol| {
            let mut row = trade.clone();
            row.symbol = (*symbol).into();
            row
        })
        .collect();
    checkpoint.observer_provider_journal = symbols
        .iter()
        .enumerate()
        .map(|(index, symbol)| observer_journal_row(index, "provider", symbol))
        .collect();
    app.backend.cohort_checkpoint = checkpoint;

    let trades = render(&mut app, 4, 160, 60);
    let research = render(&mut app, 5, 160, 60);
    let closed_start = trades.find("COMPLETED TRADES").expect("closed journal");
    let fills_start = trades
        .find("VENUE FILL LEGS // NOT COMPLETED TRADES")
        .expect("fill journal");
    let controls_start = trades[fills_start..]
        .find("OPERATOR CONTROLS")
        .map(|offset| fills_start + offset)
        .expect("trade controls");
    let open_risk = &trades[..closed_start];
    let closed = &trades[closed_start..fills_start];
    let fills = &trades[fills_start..controls_start];

    for symbol in symbols {
        assert!(
            open_risk.contains(symbol),
            "open risk missing {symbol}\n{trades}"
        );
        assert!(
            closed.contains(symbol),
            "closed journal missing {symbol}\n{trades}"
        );
        assert!(
            fills.contains(symbol),
            "fill journal missing {symbol}\n{trades}"
        );
        assert!(research.contains(symbol), "missing {symbol}\n{research}");
    }
}

#[test]
fn selected_setup_opens_full_backend_evidence_modal() {
    let mut app = cohort_app();
    app.selected_cohort_setup_index = 2;
    app.show_cohort_setup_modal = true;

    let screen = render(&mut app, 1, 120, 36);

    for expected in [
        "SETUP INSPECTOR // EXACT DECISION EVIDENCE",
        "hypervelocity_source_follow_bidirectional_5m_v1",
        "ARRIVAL ET 12:00:00 EDT",
        "DECISION ET 08-01 11:59:59 EDT",
        "READINESS 66.7%",
        "PRIMARY 5M TREND_UP",
        "WAITING 5M PRIMARY ONSET",
        "RESEARCH STATE MIXED NONMATCHING RISK",
        "175 events / 90 days (~1.9/day)",
        "ROUTE LIVE EXECUTABLE // RESEARCH REPORT ONLY",
        "DOES NOT GATE EXECUTION",
        "BACKEND EVIDENCE ONLY",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

#[test]
fn ht_breakout_setup_inspector_uses_only_the_operator_name() {
    let mut app = cohort_app();
    app.selected_cohort_setup_index = 3;
    app.show_cohort_setup_modal = true;

    let screen = render(&mut app, 1, 120, 36);

    assert!(screen.contains("HT-Breakout"), "{screen}");
    assert!(!screen.contains("hype_breakout"), "{screen}");
}

#[test]
fn missing_setup_coverage_is_a_visible_router_alarm() {
    let mut routing_row: Value = serde_json::from_str(&routing()).expect("routing row");
    routing_row["payload"]["setup_coverage"] = json!({
        "expected_provider_symbols": 10,
        "observed_provider_symbols": 3,
        "missing_provider_symbols": [
            "hulk_expansion_bidirectional_tuned_v2|BTC",
            "hulk_expansion_bidirectional_tuned_v2|SOL",
            "hulk_expansion_bidirectional_tuned_v2|HYPE",
            "range_onset_bidirectional_v1|BTC",
            "range_onset_bidirectional_v1|ETH",
            "range_onset_bidirectional_v1|HYPE",
            "hype_breakout_onset_bidirectional_v1|HYPE"
        ],
        "complete": false
    });
    let ledger = [identity(), routing_row.to_string()].join("\n");
    let backend = parse_backend_telemetry(&format!("{ledger}\n")).expect("coverage");
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);

    let screen = render(&mut app, 1, 120, 36);

    assert!(screen.contains("SETUPS 3/10 // MISSING 7"), "{screen}");
}

#[test]
fn eligible_hulk_setup_reports_satisfied_exact_entry_contract() {
    let mut app = cohort_app();
    let hulk = &mut app.backend.cohort.evaluations[0];
    hulk.eligible = true;
    hulk.decision_action = "enter_long".into();
    hulk.reason = "eligible".into();
    hulk.score = Some(11);
    hulk.minimum_score = Some(8);
    hulk.readiness.conditions_met = 4;
    hulk.readiness.conditions_required = 4;
    hulk.readiness.readiness_fraction = 1.0;
    hulk.readiness.blockers.clear();
    hulk.readiness.metrics.insert(
        "entry_contract".into(),
        serde_json::Value::String("hulk_expansion_moderate_adx_v1".into()),
    );
    app.selected_cohort_setup_index = 0;
    app.show_cohort_setup_modal = true;

    let screen = render(&mut app, 1, 120, 36);

    for expected in [
        "ENTRY CONTRACT 100.0%",
        "EXACT CONDITIONS 4/4",
        "SIGNAL SCORE 11/8",
        "ENTRY CONTRACT SATISFIED",
        "NONE REPORTED",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(!screen.contains("MISSING SUPPORT"), "{screen}");
}

#[test]
fn legacy_hulk_readiness_remains_labeled_as_support_coverage() {
    let mut app = cohort_app();
    let hulk = &mut app.backend.cohort.evaluations[0];
    hulk.eligible = true;
    hulk.decision_action = "enter_long".into();
    hulk.reason = "eligible".into();
    hulk.score = Some(11);
    hulk.minimum_score = Some(8);
    hulk.readiness.conditions_met = 5;
    hulk.readiness.conditions_required = 6;
    hulk.readiness.readiness_fraction = 5.0 / 6.0;
    hulk.readiness.blockers = vec!["volume_not_above_1x".into()];
    app.selected_cohort_setup_index = 0;
    app.show_cohort_setup_modal = true;

    let screen = render(&mut app, 1, 120, 36);

    for expected in [
        "SUPPORT COVERAGE 83.3%",
        "CONTEXT CONDITIONS 5/6",
        "SIGNAL SCORE 11/8",
        "MISSING SUPPORT",
        "VOLUME <= 1X",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(!screen.contains("ENTRY CONTRACT 83.3%"), "{screen}");
}

#[test]
fn eligible_hulk_router_calls_absent_bonus_conditions_support_gaps() {
    let mut app = cohort_app();
    let hulk = &mut app.backend.cohort.evaluations[0];
    hulk.eligible = true;
    hulk.decision_action = "enter_long".into();
    hulk.reason = "eligible".into();
    hulk.score = Some(11);
    hulk.minimum_score = Some(8);
    hulk.readiness.blockers = vec![
        "volume_not_above_1x".into(),
        "money_flow_not_aligned".into(),
    ];

    let screen = render(&mut app, 1, 190, 52);

    assert!(screen.contains("NEXT GAPS"), "{screen}");
    assert!(screen.contains("SUPPORT ONLY"), "{screen}");
    assert!(!screen.contains("NEXT BLOCKERS"), "{screen}");
}

#[test]
fn selected_chart_opens_strategy_and_multitimeframe_detail() {
    let mut app = cohort_app();
    app.selected_cohort_symbol_index = 0;
    app.toggle_cohort_chart_modal();

    assert_eq!(app.selected_cohort_chart_provider_index, 2);

    let screen = render(&mut app, 2, 165, 46);

    for expected in [
        "BTC STRATEGY CHART // BACKEND EVIDENCE",
        "VIEW 5M // AGGREGATED FROM BACKEND COMPLETED 1M",
        "HV SOURCE 5M // DECISION TF 5M",
        "DECISION HOLD // ELIGIBLE NO",
        "REGIME 1M N/A // 5M TREND_UP // 15M N/A",
        "READINESS 66.7% // 2/3",
        "5M TREND_UP",
        "WAITING 5M PRIMARY ONSET",
        "SOURCE docs/reviews/evidence.md",
        "EFFECT report_only",
        "[Enter/Esc] CLOSE",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

#[test]
fn ht_breakout_chart_inspector_hides_the_legacy_backend_identity() {
    let mut app = cohort_app();
    app.backend
        .cohort
        .evaluations
        .retain(|value| value.strategy_id != "hype_breakout_onset_bidirectional_v1");
    app.selected_cohort_symbol_index = 3;
    app.selected_cohort_chart_provider_index = 3;
    app.show_cohort_chart_modal = true;

    let screen = render(&mut app, 2, 120, 36);

    assert!(screen.contains("HT-Breakout"), "{screen}");
    assert!(!screen.contains("hype_breakout"), "{screen}");
}

#[test]
fn selected_strategy_chart_uses_its_completed_decision_timeframe() {
    let mut app = cohort_app();
    let bucket_start_ms = 1_785_585_600_000_u64;
    app.backend.cohort.candle_history.insert(
        "BTC".into(),
        (0..6)
            .map(|minute| CohortCandle {
                timestamp_ms: bucket_start_ms + minute * 60_000,
                open: 100.0 + minute as f64,
                high: 101.5 + minute as f64,
                low: 99.5 + minute as f64,
                close: 101.0 + minute as f64,
                volume: 10.0 + minute as f64,
            })
            .collect(),
    );
    app.selected_cohort_symbol_index = 0;
    app.toggle_cohort_chart_modal();

    let screen = render(&mut app, 2, 165, 46);

    for expected in [
        "VIEW 5M // AGGREGATED FROM BACKEND COMPLETED 1M",
        "BTC 5M CANDLES",
        "1 bar",
        "INCOMPLETE 5M EXCLUDED",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

#[test]
fn chart_selection_highlights_each_backend_coin() {
    let mut app = cohort_app();
    for (index, symbol) in SYMBOLS.iter().enumerate() {
        app.selected_cohort_symbol_index = index;
        let screen = render(&mut app, 2, 120, 36);
        assert!(
            screen.contains(&format!("▸ {symbol} 1M CANDLES")),
            "selected chart missing for {symbol}\n{screen}"
        );
    }
}

#[test]
fn chart_pages_through_every_complete_portfolio_asset() {
    let mut app = cohort_app();
    let candles = app
        .backend
        .cohort
        .candle_history
        .get("BTC")
        .cloned()
        .expect("BTC candle history");
    app.backend.cohort.enabled_symbols = COMPLETE_SYMBOLS.map(str::to_string).to_vec();
    for symbol in COMPLETE_SYMBOLS {
        app.backend
            .cohort
            .candle_history
            .insert(symbol.into(), candles.clone());
    }
    app.selected_cohort_symbol_index = COMPLETE_SYMBOLS.len() - 1;

    let screen = render(&mut app, 2, 120, 36);

    assert!(screen.contains("ASSETS 9-9 / 9"), "{screen}");
    assert!(screen.contains("▸ xyz:BRENTOIL 1M CANDLES"), "{screen}");
}

#[test]
fn depth_tabs_page_to_the_selected_complete_portfolio_asset() {
    let mut app = cohort_app();
    app.backend.cohort.enabled_symbols = COMPLETE_SYMBOLS.map(str::to_string).to_vec();
    app.selected_cohort_symbol_index = COMPLETE_SYMBOLS.len() - 1;

    let screen = render(&mut app, 3, 120, 36);

    assert!(screen.contains("MARKETS 9-9 / 9"), "{screen}");
    assert!(screen.contains("xyz:BRENTOIL"), "{screen}");
}

#[test]
fn namespaced_assets_remain_visible_on_portfolio_and_regime_pages() {
    let mut app = cohort_app();
    let template = app.backend.cohort.assets[0].clone();
    app.backend.cohort.enabled_symbols = COMPLETE_SYMBOLS.map(str::to_string).to_vec();
    app.backend.cohort.assets = COMPLETE_SYMBOLS
        .into_iter()
        .map(|symbol| {
            let mut asset = template.clone();
            asset.symbol = symbol.into();
            asset
        })
        .collect();
    let mut hip3 = app.backend.cohort.evaluations[0].clone();
    hip3.strategy_id = "hip3_swing_ha_sndk_gold_brent_bidirectional_v1".into();
    hip3.symbol = "xyz:BRENTOIL".into();
    hip3.decision_action = "hold".into();
    hip3.reason = "hip3_swing_ha_flip".into();
    hip3.primary_regime = None;
    hip3.state_1m = None;
    hip3.state_5m = None;
    hip3.context_15m = None;
    hip3.confidence = Some(0.75);
    hip3.readiness.indicators = vec![
        "HA RED".into(),
        "EMA9 68.3 / EMA21 69.1".into(),
        "ORDER BLOCK BEAR".into(),
    ];
    hip3.readiness.metrics = serde_json::from_value(json!({
        "source_timeframe": "15m",
        "ha_color": "red",
        "ema_fast": 68.3,
        "ema_slow": 69.1,
        "active_order_block_direction": "bear"
    }))
    .expect("HIP-3 metrics");
    app.backend.cohort.evaluations.push(hip3);
    app.selected_cohort_symbol_index = COMPLETE_SYMBOLS.len() - 1;

    let portfolio = render(&mut app, 0, 120, 36);
    let regime = render(&mut app, 7, 120, 36);

    assert!(portfolio.contains("ASSETS 5-9 / 9"), "{portfolio}");
    assert!(portfolio.contains("xyz:BRENTOIL"), "{portfolio}");
    assert!(regime.contains("ASSETS 9-9 / 9"), "{regime}");
    assert!(regime.contains("xyz:BRENTOIL"), "{regime}");
    assert!(regime.contains("PROVIDER ONLY"), "{regime}");
    assert!(
        regime.contains("CANONICAL REGIME NOT CLASSIFIED"),
        "{regime}"
    );
    assert!(regime.contains("HIP3 SWING CMD"), "{regime}");
    assert!(regime.contains("HA RED"), "{regime}");
    assert!(regime.contains("EMA9 68.3 / EMA21 69.1"), "{regime}");
    assert!(
        regime.contains("xyz:BRENTOIL PROVIDER ONLY"),
        "selected-page provider pulse missing\n{regime}"
    );
    assert!(regime.contains("READY=67%"), "{regime}");
    let matrix_row = regime
        .lines()
        .find(|line| line.contains("xyz:BRENTOIL") && line.contains("NOT CLASS"))
        .expect("selected HIP-3 matrix row");
    assert!(matrix_row.contains("PROV HOLD"), "{matrix_row}");
    assert!(matrix_row.contains("R67%"), "{matrix_row}");
    assert!(regime.contains("WHY HIP3 SWING HA FLIP"), "{regime}");
    assert!(
        regime.contains("PROV-ONLY REG N/A"),
        "provider telemetry is mislabeled as missing\n{regime}"
    );
}
