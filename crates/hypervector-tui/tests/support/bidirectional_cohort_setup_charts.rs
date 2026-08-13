#[test]
fn every_complete_portfolio_setup_is_selectable_for_exact_details() {
    let mut app = cohort_app();
    let template = app.backend.cohort.evaluations[0].clone();
    let pairs = [
        ("hulk_expansion_bidirectional_tuned_v2", "BTC"),
        ("hulk_expansion_bidirectional_tuned_v2", "ETH"),
        ("hulk_expansion_bidirectional_tuned_v2", "SOL"),
        ("hulk_expansion_bidirectional_tuned_v2", "HYPE"),
        ("range_onset_bidirectional_v1", "BTC"),
        ("range_onset_bidirectional_v1", "ETH"),
        ("range_onset_bidirectional_v1", "SOL"),
        ("range_onset_bidirectional_v1", "HYPE"),
        ("hypervelocity_source_follow_bidirectional_5m_v1", "BTC"),
        ("hype_breakout_onset_bidirectional_v1", "BTC"),
        ("hype_breakout_onset_bidirectional_v1", "ETH"),
        ("hype_breakout_onset_bidirectional_v1", "SOL"),
        ("hype_breakout_onset_bidirectional_v1", "HYPE"),
        (
            "eth_breakout_precompression_pullback_bidirectional_v1",
            "ETH",
        ),
        ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SP500"),
        ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SPCX"),
        (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
            "xyz:SP500",
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
            "xyz:SPCX",
        ),
        ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:SNDK"),
        ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:GOLD"),
        (
            "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
            "xyz:BRENTOIL",
        ),
        (
            "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1",
            "xyz:SNDK",
        ),
        (
            "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1",
            "xyz:GOLD",
        ),
        (
            "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1",
            "xyz:BRENTOIL",
        ),
    ];
    app.backend.cohort.evaluations = pairs
        .into_iter()
        .map(|(strategy_id, symbol)| {
            let mut setup = template.clone();
            setup.strategy_id = strategy_id.into();
            setup.symbol = symbol.into();
            setup
        })
        .collect();
    for _ in 1..pairs.len() {
        app.select_next_cohort_setup();
    }
    app.toggle_cohort_setup_modal();

    let screen = render(&mut app, 1, 165, 46);

    assert_eq!(app.selected_cohort_setup_index, 23);
    assert!(screen.contains("HIP3 BK CMD"), "{screen}");
    assert!(screen.contains("xyz:BRENTOIL"), "{screen}");
    assert!(
        screen.contains("hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1"),
        "{screen}"
    );
}

#[test]
fn chart_detail_does_not_borrow_another_providers_evidence() {
    let mut app = cohort_app();
    app.selected_cohort_symbol_index = 0;
    app.selected_cohort_chart_provider_index = 0;
    app.show_cohort_chart_modal = true;

    let screen = render(&mut app, 2, 120, 36);

    assert!(
        screen.contains("HULK EXPANSION // DECISION TF 30M"),
        "{screen}"
    );
    assert!(screen.contains("LATEST DECISION UNAVAILABLE"), "{screen}");
    assert!(!screen.contains("CONF 85/70"), "{screen}");
}

#[test]
fn compact_chart_detail_retains_long_indicator_and_provenance_tail() {
    let mut app = cohort_app();
    let range = app
        .backend
        .cohort
        .evaluations
        .iter_mut()
        .find(|value| value.strategy_id == "range_onset_bidirectional_v1")
        .expect("range evaluation");
    range.readiness.indicators = [
        "SMA10 41.9",
        "SMA30 42.1",
        "SMA GAP -47.6bps",
        "RAW CROSS NONE",
        "5m REGIME BLOCKED",
        "STRUCT SHORT",
        "EMA21/55 +3.2bps",
        "SMA100/200 +7.8bps",
        "CIPHER A UP",
        "HARSI DOWN",
        "CHOP14 +41.2",
        "MTF BIAS 5M +3 / 15M +1",
        "TREND R2 +0.72",
        "TQI +0.61",
    ]
    .map(str::to_string)
    .to_vec();
    app.selected_cohort_symbol_index = 2;
    app.selected_cohort_chart_provider_index = 1;
    app.show_cohort_chart_modal = true;

    let screen = render(&mut app, 2, 120, 36);

    assert!(screen.contains("TQI +0.61"), "{screen}");
    assert!(screen.contains("5M REGIME BLOCKED"), "{screen}");
    assert!(
        screen.contains("SOURCE docs/reviews/evidence.md"),
        "{screen}"
    );
    assert!(screen.contains("EFFECT report_only"), "{screen}");
}

#[test]
fn depth_screen_renders_only_exact_backend_levels() {
    let mut app = cohort_app();
    let screen = render(&mut app, 3, 120, 36);
    let wide = render(&mut app, 3, 165, 46);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("120x36 DEPTH\n{screen}");
        println!("165x46 DEPTH\n{}", render(&mut app, 3, 165, 46));
    }

    for expected in [
        "MID 101.00000000",
        "100.99000000",
        "101.01000000",
        "BID/ASK RATIO 1.500",
        "IMBALANCE CURVE // MULTI-LEVEL",
        "VISIBLE SWEEP COST // BOOK-LIMITED",
        "LIQUIDITY CONCENTRATION",
        "BUY +0.990bps",
        "TOP1 SHARE B60.0% / A50.0%",
        "L01",
        "L02",
        "MICROPRICE",
        "TOTAL ORDERS B3/A3",
        "PRESSURE IS TELEMETRY",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(!screen.contains("synthetic"), "{screen}");
    assert!(
        screen.lines().any(|line| line.contains("╮  ╭")),
        "compact lower analytics panels need two-column gutters\n{screen}"
    );
    for title in [
        "IMBALANCE CURVE // MULTI-LEVEL",
        "VISIBLE SWEEP COST // BOOK-LIMITED",
        "LIQUIDITY CONCENTRATION",
        "HIP-3 RESEARCH // REPORT ONLY",
    ] {
        assert!(
            wide.contains(title),
            "wide depth title clipped: {title}\n{wide}"
        );
    }
}

#[test]
fn wide_depth_screen_uses_two_balanced_analytics_rows() {
    let mut app = cohort_app();
    let screen = render(&mut app, 3, 165, 46);
    let lines = screen.lines().collect::<Vec<_>>();
    let panel_line = |title: &str| {
        lines
            .iter()
            .position(|line| line.contains(title))
            .unwrap_or_else(|| panic!("missing {title}\n{screen}"))
    };
    let imbalance = panel_line("IMBALANCE CURVE // MULTI-LEVEL");
    let sweep = panel_line("VISIBLE SWEEP COST // BOOK-LIMITED");
    let concentration = panel_line("LIQUIDITY CONCENTRATION");
    let hip3 = panel_line("HIP-3 RESEARCH // REPORT ONLY");

    assert_eq!(
        imbalance, sweep,
        "top analytics row is misaligned\n{screen}"
    );
    assert_eq!(
        concentration, hip3,
        "lower analytics row is misaligned\n{screen}"
    );
    assert!(
        concentration > imbalance,
        "wide analytics panels remain compressed into one row\n{screen}"
    );
    assert!(
        screen.lines().any(|line| line.contains("╮  ╭")),
        "wide analytics columns need a two-column gutter\n{screen}"
    );
    assert!(
        screen.lines().any(|line| line.trim() == ""),
        "wide analytics rows need a visible gutter\n{screen}"
    );
}

#[test]
fn compact_depth_screen_uses_spaced_two_by_two_analytics_grid() {
    let mut app = cohort_app();
    let screen = render(&mut app, 3, 120, 36);
    let lines = screen.lines().collect::<Vec<_>>();
    let panel_line = |title: &str| {
        lines
            .iter()
            .position(|line| line.contains(title))
            .unwrap_or_else(|| panic!("missing {title}\n{screen}"))
    };
    let imbalance = panel_line("IMBALANCE CURVE // MULTI-LEVEL");
    let sweep = panel_line("VISIBLE SWEEP COST // BOOK-LIMITED");
    let concentration = panel_line("LIQUIDITY CONCENTRATION");
    let hip3 = panel_line("HIP-3 RESEARCH // REPORT ONLY");

    assert_eq!(imbalance, sweep, "top panels are misaligned\n{screen}");
    assert_eq!(
        concentration, hip3,
        "bottom panels are misaligned\n{screen}"
    );
    assert!(
        concentration > imbalance,
        "compact lower deck is still one crushed row\n{screen}"
    );
    assert!(
        screen.lines().any(|line| line.contains("╮  ╭")),
        "compact analytics columns need a visible gutter\n{screen}"
    );
}

#[test]
fn cohort_projection_accepts_venue_maximum_twenty_levels_per_side() {
    let mut event: Value = serde_json::from_str(&snapshot(4, 100.0, false)).expect("snapshot");
    for book in event["payload"]["books"]
        .as_array_mut()
        .expect("book array")
    {
        let mid = book["mid_px"].as_f64().expect("mid");
        let step = mid / 10_000.0;
        book["bids"] = json!(
            (1..=20)
                .map(|level| json!({
                    "price": mid - step * f64::from(level),
                    "size": 21.0 - f64::from(level),
                    "orders": level,
                }))
                .collect::<Vec<_>>()
        );
        book["asks"] = json!(
            (1..=20)
                .map(|level| json!({
                    "price": mid + step * f64::from(level),
                    "size": 21.0 - f64::from(level),
                    "orders": level,
                }))
                .collect::<Vec<_>>()
        );
    }
    let ledger = format!("{}\n{}\n", identity(), event);

    let backend = parse_backend_telemetry(&ledger).expect("twenty-level venue book");

    assert_eq!(backend.cohort.books["BTC"].bids.len(), 20);
    assert_eq!(backend.cohort.books["BTC"].asks.len(), 20);

    let mut app = cohort_app();
    app.apply_backend_telemetry(backend);
    let screen = render(&mut app, 3, 165, 46);
    let lower_start = screen
        .lines()
        .position(|line| line.contains("IMBALANCE CURVE // MULTI-LEVEL"))
        .expect("lower depth deck");
    let controls = screen
        .lines()
        .position(|line| line.contains("OPERATOR CONTROLS"))
        .expect("operator controls");

    assert!(
        controls.saturating_sub(lower_start) >= 12,
        "wide 20-level book leaves the lower analytics deck compressed\n{screen}"
    );
}

#[test]
fn strategy_readiness_cockpit_exposes_proximity_indicators_and_blockers() {
    let mut app = cohort_app();
    let screen = render(&mut app, 1, 190, 52);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("190x52 READINESS COCKPIT\n{screen}");
        println!("120x36 READINESS COCKPIT\n{}", render(&mut app, 1, 120, 36));
    }
    for expected in [
        "SETUP READINESS // DIAGNOSTIC, NOT WIN PROBABILITY",
        "ARRIVAL ET",
        "DECISION ET",
        "HULK EXPANSION",
        "RANGE ONSET",
        "HV SOURCE 5M",
        "HT-Breakout",
        "67%",
        "4/6",
        "SMA GAP -1.8bps",
        "WAITING SQUEEZE RELEASE",
        "5M REGIME BLOCKED",
        "NO TRIGGER",
        "REGIME BLOCKED",
        "WAITING 5M PRIMARY ONSET",
        "WAITING 5M BREAKOUT",
        "REGIME BIAS +0.67 SUPPORT",
        "REGIME BIAS -0.67 OPPOSE",
        "CONFLICT REGIME PREF // LONE UNGATED // FORCED EXIT OFF",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
    assert!(screen.contains('█'), "readiness bars missing\n{screen}");
}

#[test]
fn ht_breakout_legacy_identity_never_leaks_into_operator_routing_views() {
    let mut app = cohort_app();
    app.backend.cohort.actions[0].strategy_id = "hype_breakout_onset_bidirectional_v1".into();
    app.backend.cohort.withheld[0].strategy_id = "hype_breakout_onset_bidirectional_v1".into();

    let screen = render(&mut app, 1, 190, 52);

    assert!(
        screen.matches("HT-Breakout").count() >= 3,
        "every setup/action/withheld surface must use the operator name\n{screen}"
    );
    assert!(
        !screen.contains("hype_breakout"),
        "legacy backend identity leaked into the operator view\n{screen}"
    );
}

#[test]
fn hip3_symbols_remain_exact_in_router_outcome_tables_at_160_columns() {
    let mut app = cohort_app();
    app.backend.cohort.actions[0].symbol = "xyz:BRENTOIL".into();
    app.backend.cohort.withheld[0].symbol = "xyz:SP500".into();

    let screen = render(&mut app, 1, 160, 50);

    assert!(
        screen.contains("xyz:BRENTOIL"),
        "selected action symbol truncated\n{screen}"
    );
    assert!(
        screen.contains("xyz:SP500"),
        "withheld symbol truncated\n{screen}"
    );
}

#[test]
fn compact_readiness_cockpit_preserves_complete_leading_setup_evidence() {
    let mut app = cohort_app();
    let screen = render(&mut app, 1, 120, 36);

    for expected in [
        "LEADING SETUP",
        "SQUEEZE ARMED",
        "awaiting_squeeze_release",
        "volume_not_above_1x",
        "NO TRIGGER",
        "REGIME BLOCKED",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

#[test]
fn readiness_cockpit_labels_observe_only_setup_authority() {
    let mut app = cohort_app();
    for provider in &mut app.backend.cohort.providers {
        provider.execution_symbols = Some(Vec::new());
    }

    let screen = render(&mut app, 1, 190, 52);

    assert!(screen.contains("[OBS]"), "{screen}");
    assert!(screen.contains("ROUTE OBSERVE ONLY"), "{screen}");
}

#[test]
fn compact_readiness_cockpit_shows_all_ten_asset_provider_evaluations() {
    let mut app = cohort_app();
    let hulk = app.backend.cohort.evaluations[0].clone();
    let range = app.backend.cohort.evaluations[1].clone();
    let source = app.backend.cohort.evaluations[2].clone();
    let hype = app.backend.cohort.evaluations[3].clone();
    app.backend.cohort.evaluations = SYMBOLS
        .iter()
        .flat_map(|symbol| {
            let mut hulk_evaluation = hulk.clone();
            hulk_evaluation.symbol = (*symbol).into();
            let mut range_evaluation = range.clone();
            range_evaluation.symbol = (*symbol).into();
            [hulk_evaluation, range_evaluation]
        })
        .collect();
    app.backend.cohort.evaluations.push(source);
    app.backend.cohort.evaluations.push(hype);

    let screen = render(&mut app, 1, 120, 36);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("120x36 TEN-SETUP COCKPIT\n{screen}");
    }

    assert!(screen.contains("EVALUATED 10"), "{screen}");
    assert!(screen.contains("HOLD · TREND_UP · 85%"), "{screen}");
    assert!(screen.contains("HOLD · RANGE · 61%"), "{screen}");
    let readiness_table = screen
        .split("LEADING SETUP")
        .next()
        .expect("readiness table");
    assert_eq!(
        readiness_table.matches("HULK EXPANSION").count(),
        4,
        "{screen}"
    );
    assert_eq!(
        readiness_table.matches("RANGE ONSET").count(),
        4,
        "{screen}"
    );
    assert_eq!(
        readiness_table.matches("HV SOURCE 5M").count(),
        1,
        "{screen}"
    );
    assert_eq!(
        readiness_table.matches("HT-Breakout").count(),
        1,
        "{screen}"
    );
    assert!(screen.contains("LEADING SETUP"), "{screen}");
}
