#[test]
fn projects_a_distinct_sol_aligned_range_observer_at_source_size() {
    let mut value = checkpoint(matrix_contract());
    let mut sol = forward_challenger();
    sol["contract"]["execution"]["strategy_id"] = "range_onset_bidirectional_v1".into();
    sol["contract"]["execution"]["symbol"] = "SOL".into();
    sol["contract"]["execution"]["blocker"] = "awaiting_hourly_sma_cross".into();
    sol["contract"]["execution"]["opi_cohort"] = "aligned".into();
    sol["contract"]["execution"]["notional_usd"] = 75.0.into();
    sol["portfolio_journal"]["contract"]["source_strategy_id"] =
        "range_onset_bidirectional_v1".into();
    sol["portfolio_journal"]["contract"]["candidate_strategy_id"] =
        "sol_aligned_range_relaxed_fixed60_bidirectional_v1".into();
    sol["portfolio_journal"]["contract"]["symbol"] = "SOL".into();
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([sol]);

    let parsed = parse_cohort_checkpoint(&value.to_string()).expect("SOL aligned observer");
    let observer = &parsed
        .execution_opportunity_matrix
        .expect("matrix")
        .supplemental_forward_challengers[0];
    let journal = observer.portfolio_journal.as_ref().expect("SOL journal");

    assert_eq!(journal.symbol, "SOL");
    assert_eq!(
        journal.candidate_strategy_id,
        "sol_aligned_range_relaxed_fixed60_bidirectional_v1"
    );
}

#[test]
fn projects_exact_aligned_book_breakout_relaxation_observers() {
    let mut value = checkpoint(matrix_contract());
    let hype = aligned_book_breakout_relaxation(
        "HYPE",
        "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
    );
    let sol = aligned_book_breakout_relaxation(
        "SOL",
        "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
    );
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([hype, sol]);

    let parsed = parse_cohort_checkpoint(&value.to_string()).expect("aligned-book observers");
    let observers = parsed
        .execution_opportunity_matrix
        .expect("matrix")
        .supplemental_forward_challengers;

    assert_eq!(observers.len(), 2);
    let contract = &observers[0].execution_contract;
    assert_eq!(contract.symbol, "HYPE");
    assert_eq!(contract.opi_cohort, "aligned");
    assert_eq!(contract.horizon_minutes, 60);
    assert_eq!(contract.notional_usd, 75.0);
    assert_eq!(contract.taker_fee_rate, 0.000432);
    assert_eq!(contract.stop_proxy_bps, 80.0);
    assert_eq!(contract.maximum_context_age_ms, Some(30_000));
    assert_eq!(contract.maximum_entry_delay_ms, Some(60_000));
    assert_eq!(contract.maximum_exit_delay_ms, Some(30_000));
    assert_eq!(contract.cutoff_time_ms, 1_786_054_080_000);
    assert_eq!(contract.cutoff_utc, "2026-08-06T22:08:00+00:00");
    assert_eq!(contract.execution_authority, "none");
    let identities = observers
        .iter()
        .map(|observer| {
            let journal = observer.portfolio_journal.as_ref().expect("journal");
            (
                journal.symbol.as_str(),
                journal.candidate_strategy_id.as_str(),
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(
        identities,
        vec![
            (
                "HYPE",
                "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1"
            ),
            (
                "SOL",
                "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1"
            ),
        ]
    );
}

#[test]
fn rejects_aligned_book_breakout_relaxation_with_all_opi_cohort() {
    let mut value = checkpoint(matrix_contract());
    let mut hype = aligned_book_breakout_relaxation(
        "HYPE",
        "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
    );
    hype["contract"]["execution"]["opi_cohort"] = "all".into();
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([hype]);

    let error = parse_cohort_checkpoint(&value.to_string())
        .expect_err("aligned-book identity must remain OPI aligned");

    assert!(error.contains("forward opportunity challenger"), "{error}");
}

#[test]
fn rejects_aligned_book_breakout_relaxation_with_wrong_blocker() {
    let mut value = checkpoint(matrix_contract());
    let mut sol = aligned_book_breakout_relaxation(
        "SOL",
        "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
    );
    sol["contract"]["execution"]["blocker"] = "breakout_volume_below_minimum".into();
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([sol]);

    let error = parse_cohort_checkpoint(&value.to_string())
        .expect_err("aligned-book identity must preserve the exact blocker");

    assert!(error.contains("forward opportunity challenger"), "{error}");
}

#[test]
fn rejects_aligned_book_breakout_relaxation_with_crossed_asset_identity() {
    let mut value = checkpoint(matrix_contract());
    let hype_with_sol_candidate = aligned_book_breakout_relaxation(
        "HYPE",
        "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
    );
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([hype_with_sol_candidate]);

    let error = parse_cohort_checkpoint(&value.to_string())
        .expect_err("symbol and candidate identity must remain paired");

    assert!(error.contains("forward opportunity challenger"), "{error}");
}

#[test]
fn rejects_aligned_book_breakout_relaxation_with_changed_frozen_numbers() {
    for (field, changed_value) in [
        ("maximum_context_age_ms", serde_json::json!(30_001)),
        ("maximum_entry_delay_ms", serde_json::json!(60_001)),
        ("maximum_exit_delay_ms", serde_json::json!(30_001)),
        ("notional_usd", serde_json::json!(74.0)),
        ("taker_fee_rate", serde_json::json!(0.0005)),
        ("stop_proxy_bps", serde_json::json!(81.0)),
        ("target_proxy_bps", serde_json::json!(20.0)),
    ] {
        let mut value = checkpoint(matrix_contract());
        let mut hype = aligned_book_breakout_relaxation(
            "HYPE",
            "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
        );
        hype["contract"]["execution"][field] = changed_value;
        value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
            serde_json::json!([hype]);

        let error = parse_cohort_checkpoint(&value.to_string())
            .expect_err("changed frozen execution value must fail closed");

        assert!(
            error.contains("forward opportunity challenger"),
            "{field}: {error}"
        );
    }
}

#[test]
fn rejects_aligned_book_breakout_relaxation_with_shifted_cutoff() {
    let mut value = checkpoint(matrix_contract());
    let mut sol = aligned_book_breakout_relaxation(
        "SOL",
        "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1",
    );
    sol["contract"]["cutoff_time_ms"] = 1_786_140_480_000_u64.into();
    sol["contract"]["cutoff_utc"] = "2026-08-07T22:08:00+00:00".into();
    sol["contract"]["execution"]["minimum_available_time_ms"] = 1_786_140_480_000_u64.into();
    sol["generated_at_utc"] = "2026-08-07T22:09:00+00:00".into();
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([sol]);

    let error = parse_cohort_checkpoint(&value.to_string())
        .expect_err("frozen cutoff must not shift with an otherwise consistent envelope");

    assert!(error.contains("forward opportunity challenger"), "{error}");
}

#[test]
fn rejects_duplicate_forward_observer_candidate_identity() {
    let mut value = checkpoint(matrix_contract());
    value["audit"]["execution_opportunity_matrix"]["supplemental_forward_challengers"] =
        serde_json::json!([forward_challenger()]);

    let error = parse_cohort_checkpoint(&value.to_string())
        .expect_err("duplicate observer identity must fail closed");

    assert!(error.contains("duplicate candidate strategy"));
}

fn aligned_book_breakout_relaxation(symbol: &str, candidate: &str) -> serde_json::Value {
    let mut observer = forward_challenger();
    observer["generated_at_utc"] = "2026-08-06T22:09:00+00:00".into();
    observer["contract"]["cutoff_time_ms"] = 1_786_054_080_000_u64.into();
    observer["contract"]["cutoff_utc"] = "2026-08-06T22:08:00+00:00".into();
    observer["contract"]["execution"]["symbol"] = symbol.into();
    observer["contract"]["execution"]["opi_cohort"] = "aligned".into();
    observer["contract"]["execution"]["minimum_available_time_ms"] = 1_786_054_080_000_u64.into();
    observer["contract"]["execution"]["maximum_context_age_ms"] = 30_000.into();
    observer["contract"]["execution"]["maximum_entry_delay_ms"] = 60_000.into();
    observer["contract"]["execution"]["maximum_exit_delay_ms"] = 30_000.into();
    observer["contract"]["execution"]["notional_usd"] = 75.0.into();
    observer["portfolio_journal"]["contract"]["candidate_strategy_id"] = candidate.into();
    observer["portfolio_journal"]["contract"]["symbol"] = symbol.into();
    observer
}

include!("cohort_execution_opportunity_matrix_checkpoint_fixtures.rs");
