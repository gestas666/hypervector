//! Validation and projection for trade-performance evidence.

use super::*;

pub(crate) fn project_trade_performance(
    raw: Option<RawTradePerformance>,
    expected_closed_trades: usize,
) -> Result<Option<CohortTradePerformance>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    let total = validate_root(&value, expected_closed_trades)?;
    let by_strategy = project_strategy_map(value.by_strategy)?;
    validate_aggregate(&total, &by_strategy)?;
    let current_profile = value.current_profile.map(project_profile).transpose()?;
    let current_run = value.current_run.map(project_run).transpose()?;
    let all_time_live = value.all_time_live.map(project_all_time_live).transpose()?;
    let process_run_windows = project_process_run_windows(value.process_run_windows, &total)?;
    validate_subset_bounds(
        &total,
        current_profile.as_ref(),
        current_run.as_ref(),
        all_time_live.as_ref(),
    )?;
    Ok(Some(CohortTradePerformance {
        total,
        by_strategy,
        all_time_live,
        profile_fingerprint_count: value.profile_fingerprint_count,
        mixed_profile_history: value.mixed_profile_history,
        current_profile,
        current_run,
        process_run_windows,
    }))
}

fn validate_root(
    value: &RawTradePerformance,
    expected_closed_trades: usize,
) -> Result<CohortTradePerformanceSummary, String> {
    if value.scope != "compatible_profile_history" || value.return_basis != RETURN_BASIS {
        return Err("trade performance scope or return basis is unsupported".into());
    }
    let total = project_summary(&value.total)?;
    if total.closed_trades != expected_closed_trades {
        return Err("trade performance total disagrees with closed trades".into());
    }
    validate_profile_shape(value)?;
    Ok(total)
}

fn project_strategy_map(
    values: BTreeMap<String, RawTradePerformanceSummary>,
) -> Result<BTreeMap<String, CohortTradePerformanceSummary>, String> {
    values
        .into_iter()
        .map(|(strategy, summary)| {
            if strategy.trim().is_empty() {
                return Err("trade performance strategy id is empty".into());
            }
            Ok((strategy, project_summary(&summary)?))
        })
        .collect()
}

fn validate_subset_bounds(
    total: &CohortTradePerformanceSummary,
    profile: Option<&CohortProfileTradePerformance>,
    run: Option<&CohortRunTradePerformance>,
    all_time: Option<&CohortAllTimeTradePerformance>,
) -> Result<(), String> {
    let invalid = profile.is_some_and(|item| item.total.closed_trades > total.closed_trades)
        || run.is_some_and(|item| item.total.closed_trades > total.closed_trades)
        || all_time.is_some_and(|item| item.total.closed_trades < total.closed_trades);
    if invalid {
        return Err("current trade subset exceeds compatible history".into());
    }
    Ok(())
}

fn project_all_time_live(
    value: RawAllTimeTradePerformance,
) -> Result<CohortAllTimeTradePerformance, String> {
    if value.scope != "all_live_history" || value.return_basis != RETURN_BASIS {
        return Err("all-time live performance scope or return basis is unsupported".into());
    }
    let (total, by_strategy) = project_partition(value.total, value.by_strategy, "all-time live")?;
    Ok(CohortAllTimeTradePerformance { total, by_strategy })
}

fn validate_profile_shape(value: &RawTradePerformance) -> Result<(), String> {
    let count = value.profile_fingerprint_count;
    if value.current_profile.is_some() != count.is_some()
        || value.mixed_profile_history != count.is_some_and(|number| number > 1)
    {
        return Err("current-profile performance provenance is inconsistent".into());
    }
    Ok(())
}

fn project_profile(
    value: RawProfileTradePerformance,
) -> Result<CohortProfileTradePerformance, String> {
    if value.profile_fingerprint.trim().is_empty() {
        return Err("current-profile fingerprint is empty".into());
    }
    let (total, by_strategy) =
        project_partition(value.total, value.by_strategy, "current-profile")?;
    Ok(CohortProfileTradePerformance {
        profile_fingerprint: value.profile_fingerprint,
        total,
        by_strategy,
    })
}

fn project_run(value: RawRunTradePerformance) -> Result<CohortRunTradePerformance, String> {
    if value.run_id.trim().is_empty() {
        return Err("current-run id is empty".into());
    }
    let (total, by_strategy) = project_partition(value.total, value.by_strategy, "current-run")?;
    Ok(CohortRunTradePerformance {
        run_id: value.run_id,
        total,
        by_strategy,
    })
}

pub(crate) fn project_partition(
    raw_total: RawTradePerformanceSummary,
    raw_by_strategy: BTreeMap<String, RawTradePerformanceSummary>,
    label: &str,
) -> Result<
    (
        CohortTradePerformanceSummary,
        BTreeMap<String, CohortTradePerformanceSummary>,
    ),
    String,
> {
    let total = project_summary(&raw_total)?;
    let values = raw_by_strategy
        .into_iter()
        .map(|(strategy, summary)| {
            if strategy.trim().is_empty() {
                return Err(format!("{label} strategy id is empty"));
            }
            Ok((strategy, project_summary(&summary)?))
        })
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    validate_aggregate(&total, &values)?;
    Ok((total, values))
}

pub(crate) fn project_summary(
    value: &RawTradePerformanceSummary,
) -> Result<CohortTradePerformanceSummary, String> {
    validate_summary(value)?;
    Ok(CohortTradePerformanceSummary {
        closed_trades: value.closed_trades,
        wins: value.wins,
        losses: value.losses,
        breakeven: value.breakeven,
        win_rate_pct: value.win_rate_pct,
        net_pnl_usd: value.net_pnl_usd,
        entry_margin_used_usd: value.entry_margin_used_usd,
        net_return_on_margin_pct: value.net_return_on_margin_pct,
        mean_trade_return_on_margin_pct: value.mean_trade_return_on_margin_pct,
        profit_factor: value.profit_factor,
        fees_usd: value.fees_usd,
        funding_usd: value.funding_usd,
    })
}

fn validate_summary(value: &RawTradePerformanceSummary) -> Result<(), String> {
    let numbers = [
        value.net_pnl_usd,
        value.entry_margin_used_usd,
        value.fees_usd,
        value.funding_usd,
    ];
    let invalid = value.wins + value.losses + value.breakeven != value.closed_trades
        || numbers.iter().any(|number| !number.is_finite())
        || value.entry_margin_used_usd < 0.0
        || value.fees_usd < 0.0
        || !valid_optional_pct(value.win_rate_pct)
        || !valid_optional_number(value.net_return_on_margin_pct)
        || !valid_optional_number(value.mean_trade_return_on_margin_pct)
        || !valid_optional_nonnegative(value.profit_factor)
        || (value.closed_trades == 0 && value.win_rate_pct.is_some())
        || (value.closed_trades > 0 && value.win_rate_pct.is_none())
        || (value.losses == 0) != value.profit_factor.is_none();
    if invalid {
        return Err("trade performance summary is inconsistent".into());
    }
    Ok(())
}

pub(crate) fn validate_aggregate(
    total: &CohortTradePerformanceSummary,
    values: &BTreeMap<String, CohortTradePerformanceSummary>,
) -> Result<(), String> {
    let counts = values
        .values()
        .map(|value| value.closed_trades)
        .sum::<usize>();
    let wins = values.values().map(|value| value.wins).sum::<usize>();
    let losses = values.values().map(|value| value.losses).sum::<usize>();
    let breakeven = values.values().map(|value| value.breakeven).sum::<usize>();
    let sums = aggregate_sums(values);
    let expected = [
        total.net_pnl_usd,
        total.entry_margin_used_usd,
        total.fees_usd,
        total.funding_usd,
    ];
    let counts_differ = (counts, wins, losses, breakeven)
        != (
            total.closed_trades,
            total.wins,
            total.losses,
            total.breakeven,
        );
    let sums_differ = sums
        .iter()
        .zip(expected)
        .any(|(actual, expected)| (actual - expected).abs() > 1e-9);
    if counts_differ || sums_differ {
        return Err("per-strategy performance does not sum to total".into());
    }
    Ok(())
}

fn aggregate_sums(values: &BTreeMap<String, CohortTradePerformanceSummary>) -> [f64; 4] {
    [
        values.values().map(|value| value.net_pnl_usd).sum(),
        values
            .values()
            .map(|value| value.entry_margin_used_usd)
            .sum(),
        values.values().map(|value| value.fees_usd).sum(),
        values.values().map(|value| value.funding_usd).sum(),
    ]
}

fn valid_optional_pct(value: Option<f64>) -> bool {
    value.is_none_or(|number| number.is_finite() && (0.0..=100.0).contains(&number))
}

fn valid_optional_number(value: Option<f64>) -> bool {
    value.is_none_or(f64::is_finite)
}

fn valid_optional_nonnegative(value: Option<f64>) -> bool {
    value.is_none_or(|number| number.is_finite() && number >= 0.0)
}
