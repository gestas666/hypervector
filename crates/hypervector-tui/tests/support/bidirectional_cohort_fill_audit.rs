#[test]
fn dashboard_never_success_shapes_an_unavailable_checkpoint() {
    let mut app = cohort_app();
    app.backend.cohort_checkpoint =
        CohortCheckpointTelemetry::unavailable("asset ledgers not ready");

    let screen = render(&mut app, 0, 120, 36);

    assert!(screen.contains("ANALYSIS UNAVAILABLE"), "{screen}");
    assert!(screen.contains("asset ledgers not ready"), "{screen}");
    assert!(!screen.contains("COVERAGE COMPLETE"), "{screen}");
}

#[test]
fn wide_dashboard_retains_exact_execution_audit_fields() {
    let mut app = cohort_app();
    let screen = render(&mut app, 4, 190, 52);
    if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
        println!("190x52 TRADES\n{screen}");
        println!("160x44 TRADES\n{}", render(&mut app, 4, 160, 44));
    }
    for expected in [
        "TRADE ID",
        "ORDER ID",
        "101",
        "11",
        "FILL GROSS",
        "SLIPPAGE",
        "ACK",
        "MARKOUT",
        "+9.91bps",
        "+5.20bps/6000ms",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}

#[test]
fn selected_fill_details_show_fee_and_cross_run_provenance() {
    let mut app = cohort_app();
    app.show_cohort_fill_modal = true;

    let screen = render(&mut app, 4, 160, 44);

    assert!(screen.contains("FEE $0.01 (1.98bps)"), "{screen}");
    assert!(
        screen.contains("ORIGIN RUN bidirectional-live-1785704911829"),
        "{screen}"
    );
    assert!(
        screen.contains("EXIT CONTROLLER cohort_maximum_hold"),
        "{screen}"
    );
    assert!(
        screen.contains("ENTRY 100.00000000 @ 11:43:20 EDT"),
        "{screen}"
    );
    assert!(screen.contains("NET PNL +$0.23"), "{screen}");
    assert!(screen.contains("LIFECYCLE FEES $0.02"), "{screen}");
    assert!(screen.contains("FUNDING +$0.00"), "{screen}");
    assert!(screen.contains("HOLD 28800000ms"), "{screen}");
}

#[test]
fn position_tracker_labels_profile_history_cost_scope() {
    let mut app = cohort_app();

    let screen = render(&mut app, 4, 160, 44);

    assert!(screen.contains("PROFILE-HISTORY COSTS"), "{screen}");
}

#[test]
fn operational_tables_do_not_silently_truncate_venue_order_ids() {
    let mut app = cohort_app();
    app.backend.cohort.assets[0].stop_oid = Some(508_799_445_939);
    app.backend.cohort.fills[0].trade_id = 5_009_675_159_415;
    app.backend.cohort.fills[0].oid = 2_374_094_964_372;

    let dashboard = render(&mut app, 0, 165, 46);
    assert!(dashboard.contains("S508799445939/T13"), "{dashboard}");

    let trades = render(&mut app, 4, 165, 46);
    assert!(trades.contains("ORDER ID"), "{trades}");
    assert!(trades.contains("2374094964372"), "{trades}");
    assert!(!trades.contains("TRADE ID"), "{trades}");

    let full_audit = render(&mut app, 4, 190, 52);
    assert!(full_audit.contains("TRADE ID"), "{full_audit}");
    assert!(full_audit.contains("5009675159415"), "{full_audit}");
    assert!(full_audit.contains("2374094964372"), "{full_audit}");
}

#[test]
fn full_fill_audit_does_not_truncate_sixteen_digit_trade_ids() {
    let mut app = cohort_app();
    app.backend.cohort.fills[0].trade_id = 8_422_107_300_835_599;

    let full_audit = render(&mut app, 4, 200, 52);

    assert!(full_audit.contains("8422107300835599"), "{full_audit}");
}

#[test]
fn fill_audit_explicitly_distinguishes_fill_legs_from_completed_trades() {
    let mut app = cohort_app();

    let full_audit = render(&mut app, 4, 200, 52);

    assert!(
        full_audit.contains("VENUE FILL LEGS // NOT COMPLETED TRADES"),
        "{full_audit}"
    );
    assert!(full_audit.contains("FILL GROSS"), "{full_audit}");
}

#[test]
fn full_fill_audit_includes_the_eastern_date_for_multiday_history() {
    let mut app = cohort_app();

    let full_audit = render(&mut app, 4, 200, 52);

    assert!(full_audit.contains("DATE/TIME ET"), "{full_audit}");
    assert!(full_audit.contains("08-01 11:59 EDT"), "{full_audit}");
}

const SECONDARY_SCREEN_CONTRACTS: [(usize, &[&str]); 8] = [
    (
        1,
        &[
            "ROUTED 1",
            "WITHHELD 1",
            "SLOTS 1 / 4",
            "SETUP READINESS",
            "11:59:59 EDT",
        ],
    ),
    (
        2,
        &[
            "BACKEND 1M OVERVIEW",
            "DETAIL USES PROVIDER TF + INDICATORS",
            "BTC 1M CANDLES",
            "3 bars",
            "PRICE",
        ],
    ),
    (
        3,
        &[
            "BACKEND L2 SNAPSHOT",
            "BOOK AGE",
            "BID DEPTH",
            "ASK DEPTH",
            "ORDER PRESSURE",
            "hyperliquid_mainnet_l2_rest",
        ],
    ),
    (
        4,
        &[
            "VENUE FILL LEGS",
            "Open Long",
            "RANGE ONSET",
            "MARGIN/NOTIONAL",
            "LIQ PX / DIST",
            "FEES / FUND",
        ],
    ),
    (
        5,
        &["RESEARCH JOURNAL", "No rolling checkpoint is available"],
    ),
    (
        6,
        &[
            "MANUAL STRATEGY ENTRY",
            "MANUAL POSITION CLOSE",
            "TRANSITION DRAIN",
            "LIVE BACKEND ARMED // REQUEST CHANNEL UNAVAILABLE",
            "DRAIN UNKNOWN // BACKEND STATUS UNAVAILABLE",
            "STATE UNAVAILABLE // DO NOT INFER INACTIVE",
            "NO BACKEND DRAIN STATUS WAS REPORTED",
            "NO DRAIN REQUEST STATUS CLAIMED",
        ],
    ),
    (
        7,
        &[
            "REGIME COMMAND DECK",
            "RANGE DETECTOR",
            "COMPRESSION + BREAKOUT ENGINE",
            "TREND STACK",
            "ROUTING ARBITRATION",
        ],
    ),
    (
        8,
        &[
            "RESTART PROFILE EDITOR",
            "EFFECTIVE BACKEND",
            "DRAFT CLEAN",
            "SELECTED COIN BTC",
            "RESEARCH CONTRADICTORY // CONF HIGH",
            "POSITION SLOTS",
            "1 PER ASSET",
            "POLL INTERVAL",
            "LEVERAGE",
            "MARGIN FRACTION",
            "EXEC TAKER IOC | STOP STRUCT 20-75bps | TARGET 3.0R | HOLD 24H",
            "PROVIDER / COIN SCOPE",
            "VALIDATE & STAGE NEW PROFILE",
            "DISCARD DRAFT",
            "PRESTART BACKUP UNAVAILABLE",
        ],
    ),
];

#[test]
fn secondary_screens_are_practical_at_acceptance_width() {
    let mut app = cohort_app();
    for (tab, expected_values) in SECONDARY_SCREEN_CONTRACTS {
        let screen = render(&mut app, tab, 120, 36);
        if std::env::var_os("HYPERVECTOR_VISUAL_SNAPSHOT").is_some() {
            println!("120x36 TAB {}\n{screen}", tab + 1);
            if tab == 2 {
                println!("160x44 CHART\n{}", render(&mut app, tab, 160, 44));
                println!("190x52 CHART\n{}", render(&mut app, tab, 190, 52));
            }
        }
        for expected in expected_values {
            assert!(screen.contains(expected), "missing {expected}\n{screen}");
        }
        if tab == 2 {
            assert!(!screen.contains("REFERENCE PRICE"), "{screen}");
            assert!(screen.contains('█'), "candle bodies missing\n{screen}");
            assert!(screen.contains('│'), "candle wicks missing\n{screen}");
        }
    }
}
