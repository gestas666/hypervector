//! Strict report-only process-run performance window projection.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::backend_cohort_trade_performance::{
    CohortTradePerformanceSummary, RawTradePerformanceSummary, project_partition,
    validate_aggregate,
};

const WINDOW_BASIS: &str = "backend_process_run_id";
const LIMITATIONS: [&str; 3] = [
    "a backend process restart creates a run window but not statistical independence",
    "profile changes remain visible and are not pooled as one policy generation",
    "run-window outcomes are descriptive and have no execution authority",
];

/// One backend process window with its exact profile and performance identity.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortProcessRunWindow {
    pub run_id: String,
    pub profile_fingerprint: String,
    pub total: CohortTradePerformanceSummary,
    pub by_strategy: BTreeMap<String, CohortTradePerformanceSummary>,
}

/// Descriptive positive/negative process-window counts for one scope.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortRunWindowOutcome {
    pub runs_with_closes: usize,
    pub positive_runs: usize,
    pub negative_runs: usize,
    pub breakeven_runs: usize,
    pub positive_run_rate_pct: Option<f64>,
    pub net_pnl_usd: f64,
}

/// Process-window outcome summary for one exact provider-symbol mapping.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortProviderRunWindows {
    pub runs_with_closes: usize,
    pub positive_runs: usize,
    pub negative_runs: usize,
    pub breakeven_runs: usize,
    pub positive_run_rate_pct: Option<f64>,
    pub net_pnl_usd: f64,
    pub by_side: BTreeMap<String, CohortRunWindowOutcome>,
}

/// Backend-authored process windows that explicitly make no independence claim.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortProcessRunWindows {
    pub run_count: usize,
    pub positive_runs: usize,
    pub negative_runs: usize,
    pub breakeven_runs: usize,
    pub positive_run_rate_pct: Option<f64>,
    pub net_pnl_usd: f64,
    pub statistical_independence_established: bool,
    pub by_run: BTreeMap<String, CohortProcessRunWindow>,
    pub by_provider_symbol: BTreeMap<String, CohortProviderRunWindows>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawProcessRunWindows {
    contract: RawContract,
    window_basis: String,
    statistical_independence_established: bool,
    run_count: usize,
    #[serde(flatten)]
    outcome: RawRunWindowOutcome,
    by_run: BTreeMap<String, RawProcessRunWindow>,
    by_provider_symbol: BTreeMap<String, RawProviderRunWindows>,
    limitations: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct RawContract {
    report_only: bool,
    performance_gate: bool,
    balance_gate: bool,
    automatic_strategy_changes: bool,
    execution_authority: String,
}

#[derive(Debug, Deserialize)]
struct RawProcessRunWindow {
    run_id: String,
    profile_fingerprint: String,
    total: RawTradePerformanceSummary,
    by_strategy: BTreeMap<String, RawTradePerformanceSummary>,
}

#[derive(Debug, Deserialize)]
struct RawProviderRunWindows {
    #[serde(flatten)]
    outcome: RawRunWindowOutcome,
    #[serde(default)]
    by_side: BTreeMap<String, RawRunWindowOutcome>,
}

#[derive(Debug, Deserialize)]
struct RawRunWindowOutcome {
    runs_with_closes: usize,
    positive_runs: usize,
    negative_runs: usize,
    breakeven_runs: usize,
    positive_run_rate_pct: Option<f64>,
    net_pnl_usd: f64,
}

pub(crate) fn project_process_run_windows(
    raw: Option<RawProcessRunWindows>,
    expected_total: &CohortTradePerformanceSummary,
) -> Result<Option<CohortProcessRunWindows>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    validate_contract(&value)?;
    let top = project_outcome(value.outcome)?;
    if value.run_count != top.runs_with_closes || value.by_run.len() != value.run_count {
        return Err("process run-window count is inconsistent".into());
    }
    let by_run = value
        .by_run
        .into_iter()
        .map(|(key, window)| project_run_window(key, window))
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    validate_run_totals(expected_total, &by_run)?;
    let by_provider_symbol = value
        .by_provider_symbol
        .into_iter()
        .map(|(key, window)| project_provider_window(key, window, value.run_count))
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    Ok(Some(CohortProcessRunWindows {
        run_count: value.run_count,
        positive_runs: top.positive_runs,
        negative_runs: top.negative_runs,
        breakeven_runs: top.breakeven_runs,
        positive_run_rate_pct: top.positive_run_rate_pct,
        net_pnl_usd: top.net_pnl_usd,
        statistical_independence_established: false,
        by_run,
        by_provider_symbol,
    }))
}

fn validate_contract(value: &RawProcessRunWindows) -> Result<(), String> {
    let contract = &value.contract;
    let limitations = value
        .limitations
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    if value.window_basis != WINDOW_BASIS
        || value.statistical_independence_established
        || !contract.report_only
        || contract.performance_gate
        || contract.balance_gate
        || contract.automatic_strategy_changes
        || contract.execution_authority != "none"
        || limitations != LIMITATIONS
    {
        return Err("process run-window contract is invalid".into());
    }
    Ok(())
}

fn project_run_window(
    key: String,
    value: RawProcessRunWindow,
) -> Result<(String, CohortProcessRunWindow), String> {
    if key.trim().is_empty() || value.run_id != key || value.profile_fingerprint.trim().is_empty() {
        return Err("process run-window identity is invalid".into());
    }
    let (total, by_strategy) =
        project_partition(value.total, value.by_strategy, "process run-window")?;
    Ok((
        key,
        CohortProcessRunWindow {
            run_id: value.run_id,
            profile_fingerprint: value.profile_fingerprint,
            total,
            by_strategy,
        },
    ))
}

fn validate_run_totals(
    expected: &CohortTradePerformanceSummary,
    windows: &BTreeMap<String, CohortProcessRunWindow>,
) -> Result<(), String> {
    let summaries = windows
        .iter()
        .map(|(run_id, window)| (run_id.clone(), window.total.clone()))
        .collect::<BTreeMap<_, _>>();
    validate_aggregate(expected, &summaries)
        .map_err(|_| "process run-window totals disagree with lifecycle history".into())
}

fn project_provider_window(
    key: String,
    value: RawProviderRunWindows,
    total_runs: usize,
) -> Result<(String, CohortProviderRunWindows), String> {
    let Some((strategy, symbol)) = key.split_once('|') else {
        return Err("process provider run-window identity is invalid".into());
    };
    if strategy.trim().is_empty() || symbol.trim().is_empty() {
        return Err("process provider run-window identity is invalid".into());
    }
    let outcome = project_outcome(value.outcome)?;
    if outcome.runs_with_closes > total_runs {
        return Err("provider run-window count exceeds process windows".into());
    }
    let by_side = value
        .by_side
        .into_iter()
        .map(|(side, raw)| project_side_window(side, raw, &outcome))
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    validate_side_net(&outcome, &by_side)?;
    Ok((
        key,
        CohortProviderRunWindows {
            runs_with_closes: outcome.runs_with_closes,
            positive_runs: outcome.positive_runs,
            negative_runs: outcome.negative_runs,
            breakeven_runs: outcome.breakeven_runs,
            positive_run_rate_pct: outcome.positive_run_rate_pct,
            net_pnl_usd: outcome.net_pnl_usd,
            by_side,
        },
    ))
}

fn project_side_window(
    side: String,
    value: RawRunWindowOutcome,
    provider: &CohortRunWindowOutcome,
) -> Result<(String, CohortRunWindowOutcome), String> {
    if !matches!(side.as_str(), "long" | "short") {
        return Err("process run-window side must be long or short".into());
    }
    let outcome = project_outcome(value)?;
    if outcome.runs_with_closes > provider.runs_with_closes {
        return Err("side run-window count exceeds provider windows".into());
    }
    Ok((side, outcome))
}

fn project_outcome(value: RawRunWindowOutcome) -> Result<CohortRunWindowOutcome, String> {
    let classified = value.positive_runs + value.negative_runs + value.breakeven_runs;
    let expected_rate = (value.runs_with_closes > 0)
        .then(|| value.positive_runs as f64 / value.runs_with_closes as f64 * 100.0);
    if classified != value.runs_with_closes
        || !value.net_pnl_usd.is_finite()
        || value
            .positive_run_rate_pct
            .is_some_and(|number| !number.is_finite())
        || !_same_optional(value.positive_run_rate_pct, expected_rate)
    {
        return Err("process run-window outcome is inconsistent".into());
    }
    Ok(CohortRunWindowOutcome {
        runs_with_closes: value.runs_with_closes,
        positive_runs: value.positive_runs,
        negative_runs: value.negative_runs,
        breakeven_runs: value.breakeven_runs,
        positive_run_rate_pct: value.positive_run_rate_pct,
        net_pnl_usd: value.net_pnl_usd,
    })
}

fn validate_side_net(
    provider: &CohortRunWindowOutcome,
    sides: &BTreeMap<String, CohortRunWindowOutcome>,
) -> Result<(), String> {
    if sides.is_empty() {
        return Ok(());
    }
    let side_net = sides.values().map(|value| value.net_pnl_usd).sum::<f64>();
    if (side_net - provider.net_pnl_usd).abs() > 1e-9 {
        return Err("side run-window net PnL disagrees with provider".into());
    }
    Ok(())
}

fn _same_optional(left: Option<f64>, right: Option<f64>) -> bool {
    match (left, right) {
        (None, None) => true,
        (Some(left), Some(right)) => (left - right).abs() <= 1e-9,
        _ => false,
    }
}
