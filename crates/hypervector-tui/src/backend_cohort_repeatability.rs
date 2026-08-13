//! Strict projection of descriptive live-trade repeatability evidence.

use std::collections::BTreeMap;

use serde::Deserialize;
use serde_json::Value;

use crate::backend_cohort_trade_performance::CohortTradePerformanceSummary;

const HOUR_MS: f64 = 3_600_000.0;
const HOURS_PER_DAY: f64 = 24.0;

/// Descriptive concentration and cadence summary for resolved lifecycles.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortRepeatabilitySummary {
    pub closed_trades: usize,
    pub evidence_state: String,
    pub first_entry_timestamp_ms: u64,
    pub last_exit_timestamp_ms: u64,
    pub observation_span_hours: f64,
    pub trades_per_24h_observed: Option<f64>,
    pub net_pnl_usd: f64,
    pub mean_net_pnl_usd: f64,
    pub median_net_pnl_usd: f64,
    pub sample_stddev_net_pnl_usd: Option<f64>,
    pub gross_profit_usd: f64,
    pub gross_loss_usd: f64,
    pub profit_factor: Option<f64>,
    pub largest_winner_usd: Option<f64>,
    pub largest_winner_share_of_gross_profit_pct: Option<f64>,
    pub net_pnl_excluding_largest_winner_usd: Option<f64>,
}

/// Exact provider-symbol repeatability record from the backend scorecard.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortRepeatabilityEvidence {
    pub strategy_id: String,
    pub symbol: String,
    pub summary: CohortRepeatabilitySummary,
    pub by_side: BTreeMap<String, CohortRepeatabilitySummary>,
}

impl CohortRepeatabilityEvidence {
    /// Number of resolved provider-symbol lifecycles.
    pub fn closed_trades(&self) -> usize {
        self.summary.closed_trades
    }

    /// Backend evidence-state label for the observed sample.
    pub fn evidence_state(&self) -> &str {
        &self.summary.evidence_state
    }

    /// Elapsed hours from earliest entry through latest exit.
    pub fn observation_span_hours(&self) -> f64 {
        self.summary.observation_span_hours
    }

    /// Descriptive trades per 24 hours, unavailable for one trade.
    pub fn trades_per_24h_observed(&self) -> Option<f64> {
        self.summary.trades_per_24h_observed
    }

    /// Net result after removing the largest winner, when a winner exists.
    pub fn net_pnl_excluding_largest_winner_usd(&self) -> Option<f64> {
        self.summary.net_pnl_excluding_largest_winner_usd
    }
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawRepeatabilityEvidence {
    strategy_id: String,
    symbol: String,
    #[serde(flatten)]
    summary: RawRepeatabilitySummary,
    by_side: BTreeMap<String, RawRepeatabilitySummary>,
    profit_forecast: Option<Value>,
}

#[derive(Debug, Deserialize)]
struct RawRepeatabilitySummary {
    closed_trades: usize,
    evidence_state: String,
    first_entry_timestamp_ms: u64,
    last_exit_timestamp_ms: u64,
    observation_span_hours: f64,
    trades_per_24h_observed: Option<f64>,
    net_pnl_usd: f64,
    mean_net_pnl_usd: f64,
    median_net_pnl_usd: f64,
    sample_stddev_net_pnl_usd: Option<f64>,
    gross_profit_usd: f64,
    gross_loss_usd: f64,
    profit_factor: Option<f64>,
    largest_winner_usd: Option<f64>,
    largest_winner_share_of_gross_profit_pct: Option<f64>,
    net_pnl_excluding_largest_winner_usd: Option<f64>,
}

pub(crate) fn project_repeatability(
    raw: Option<&RawRepeatabilityEvidence>,
    performance: Option<&CohortTradePerformanceSummary>,
    strategy_id: &str,
    symbol: &str,
) -> Result<Option<CohortRepeatabilityEvidence>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    let performance = performance
        .ok_or_else(|| "repeatability evidence requires execution performance".to_string())?;
    if value.strategy_id != strategy_id || value.symbol != symbol || value.profit_forecast.is_some()
    {
        return Err("repeatability identity or forecast is invalid".into());
    }
    let summary = project_summary(&value.summary)?;
    if summary.closed_trades != performance.closed_trades
        || !near(summary.net_pnl_usd, performance.net_pnl_usd)
    {
        return Err("repeatability evidence disagrees with execution performance".into());
    }
    let by_side = project_sides(&value.by_side, &summary)?;
    Ok(Some(CohortRepeatabilityEvidence {
        strategy_id: value.strategy_id.clone(),
        symbol: value.symbol.clone(),
        summary,
        by_side,
    }))
}

fn project_summary(value: &RawRepeatabilitySummary) -> Result<CohortRepeatabilitySummary, String> {
    validate_core(value)?;
    validate_economics(value)?;
    Ok(CohortRepeatabilitySummary {
        closed_trades: value.closed_trades,
        evidence_state: value.evidence_state.clone(),
        first_entry_timestamp_ms: value.first_entry_timestamp_ms,
        last_exit_timestamp_ms: value.last_exit_timestamp_ms,
        observation_span_hours: value.observation_span_hours,
        trades_per_24h_observed: value.trades_per_24h_observed,
        net_pnl_usd: value.net_pnl_usd,
        mean_net_pnl_usd: value.mean_net_pnl_usd,
        median_net_pnl_usd: value.median_net_pnl_usd,
        sample_stddev_net_pnl_usd: value.sample_stddev_net_pnl_usd,
        gross_profit_usd: value.gross_profit_usd,
        gross_loss_usd: value.gross_loss_usd,
        profit_factor: value.profit_factor,
        largest_winner_usd: value.largest_winner_usd,
        largest_winner_share_of_gross_profit_pct: value.largest_winner_share_of_gross_profit_pct,
        net_pnl_excluding_largest_winner_usd: value.net_pnl_excluding_largest_winner_usd,
    })
}

fn validate_core(value: &RawRepeatabilitySummary) -> Result<(), String> {
    let expected_state = if value.closed_trades > 1 {
        "descriptive_multi_trade_sample"
    } else {
        "single_trade_only"
    };
    let span_ms = value
        .last_exit_timestamp_ms
        .checked_sub(value.first_entry_timestamp_ms)
        .filter(|span| *span > 0)
        .ok_or_else(|| "repeatability exit must follow entry".to_string())?;
    let expected_span = span_ms as f64 / HOUR_MS;
    let expected_cadence = value.closed_trades as f64 * HOURS_PER_DAY / expected_span;
    if value.closed_trades == 0
        || value.evidence_state != expected_state
        || !positive(value.observation_span_hours)
        || !near(value.observation_span_hours, expected_span)
        || (value.closed_trades == 1 && value.trades_per_24h_observed.is_some())
        || (value.closed_trades > 1
            && !value
                .trades_per_24h_observed
                .is_some_and(|cadence| positive(cadence) && near(cadence, expected_cadence)))
        || (value.closed_trades == 1 && value.sample_stddev_net_pnl_usd.is_some())
        || (value.closed_trades > 1 && !value.sample_stddev_net_pnl_usd.is_some_and(nonnegative))
    {
        return Err("repeatability timing or sample state is inconsistent".into());
    }
    Ok(())
}

fn validate_economics(value: &RawRepeatabilitySummary) -> Result<(), String> {
    let finite = [
        value.net_pnl_usd,
        value.mean_net_pnl_usd,
        value.median_net_pnl_usd,
        value.gross_profit_usd,
        value.gross_loss_usd,
    ]
    .into_iter()
    .all(f64::is_finite);
    let base_valid = finite
        && nonnegative(value.gross_profit_usd)
        && nonnegative(value.gross_loss_usd)
        && near(
            value.net_pnl_usd,
            value.gross_profit_usd - value.gross_loss_usd,
        )
        && near(
            value.net_pnl_usd,
            value.mean_net_pnl_usd * value.closed_trades as f64,
        );
    if !base_valid || !valid_profit_factor(value) || !valid_largest_winner(value) {
        return Err("repeatability economics are inconsistent".into());
    }
    Ok(())
}

fn valid_profit_factor(value: &RawRepeatabilitySummary) -> bool {
    if value.gross_loss_usd == 0.0 {
        return value.profit_factor.is_none();
    }
    value.profit_factor.is_some_and(|factor| {
        nonnegative(factor) && near(factor, value.gross_profit_usd / value.gross_loss_usd)
    })
}

fn valid_largest_winner(value: &RawRepeatabilitySummary) -> bool {
    match value.largest_winner_usd {
        None => {
            value.gross_profit_usd == 0.0
                && value.largest_winner_share_of_gross_profit_pct.is_none()
                && value.net_pnl_excluding_largest_winner_usd.is_none()
        }
        Some(winner) => {
            let share = winner / value.gross_profit_usd * 100.0;
            positive(winner)
                && winner <= value.gross_profit_usd
                && value
                    .largest_winner_share_of_gross_profit_pct
                    .is_some_and(|actual| nonnegative(actual) && near(actual, share))
                && value
                    .net_pnl_excluding_largest_winner_usd
                    .is_some_and(|actual| near(actual, value.net_pnl_usd - winner))
        }
    }
}

fn project_sides(
    values: &BTreeMap<String, RawRepeatabilitySummary>,
    total: &CohortRepeatabilitySummary,
) -> Result<BTreeMap<String, CohortRepeatabilitySummary>, String> {
    if values.is_empty()
        || !values
            .keys()
            .all(|side| matches!(side.as_str(), "long" | "short"))
    {
        return Err("repeatability side coverage is invalid".into());
    }
    let sides = values
        .iter()
        .map(|(side, value)| Ok((side.clone(), project_summary(value)?)))
        .collect::<Result<BTreeMap<_, _>, String>>()?;
    let count = sides
        .values()
        .map(|value| value.closed_trades)
        .sum::<usize>();
    let net = sides.values().map(|value| value.net_pnl_usd).sum::<f64>();
    let gross_profit = sides
        .values()
        .map(|value| value.gross_profit_usd)
        .sum::<f64>();
    let gross_loss = sides
        .values()
        .map(|value| value.gross_loss_usd)
        .sum::<f64>();
    if count != total.closed_trades
        || !near(net, total.net_pnl_usd)
        || !near(gross_profit, total.gross_profit_usd)
        || !near(gross_loss, total.gross_loss_usd)
    {
        return Err("repeatability side evidence does not sum to pair total".into());
    }
    Ok(sides)
}

fn near(left: f64, right: f64) -> bool {
    let scale = left.abs().max(right.abs()).max(1.0);
    (left - right).abs() <= 1e-8 * scale
}

fn positive(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn nonnegative(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}
