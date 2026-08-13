//! Read-only projection of source-long forward outcome sidecar telemetry.

use serde::Deserialize;
use thiserror::Error;

/// Latest venue-resolved counterfactual for one observe-only source long.
#[derive(Debug, Clone, PartialEq)]
pub struct SourceLongOutcomeTelemetry {
    pub observation_id: String,
    pub recipe_id: String,
    pub status: String,
    pub evidence_complete: bool,
    pub last_event_time_utc: Option<String>,
    pub initial_equity_usd: f64,
    pub final_equity_usd: f64,
    pub submitted_entries: u64,
    pub entry_filled_quantity: f64,
    pub completed_trades: u64,
    pub open_positions: u64,
    pub maker_fees_usd: f64,
    pub taker_fees_usd: f64,
    pub funding_cashflow_usd: f64,
    pub liquidations: u64,
}

/// Structural sidecar error that prevents a truthful display projection.
#[derive(Debug, Error)]
pub enum SourceLongOutcomeError {
    #[error("invalid source-long outcome JSON at line {line}: {source}")]
    InvalidJson {
        line: usize,
        #[source]
        source: serde_json::Error,
    },
    #[error("invalid source-long outcome contract at line {line}: {message}")]
    InvalidContract { line: usize, message: String },
}

#[derive(Debug, Deserialize)]
struct OutcomeRow {
    event_type: String,
    execution_authority: String,
    payload: OutcomePayload,
}

#[derive(Debug, Deserialize)]
struct OutcomePayload {
    observation_id: String,
    recipe_id: String,
    status: String,
    evidence_complete: bool,
    last_event_time_utc: Option<String>,
    counterfactual_initial_equity_usd: f64,
    portfolio_interaction: String,
    report: OutcomeReport,
}

#[derive(Debug, Deserialize)]
struct OutcomeReport {
    final_equity: f64,
    submitted_entries: u64,
    entry_filled_quantity: f64,
    completed_trades: u64,
    open_positions: u64,
    maker_fees: f64,
    taker_fees: f64,
    funding_cashflow: f64,
    liquidations: u64,
}

/// Parse the latest strict observe-only outcome from an append-only JSONL sidecar.
pub fn parse_source_long_outcome(
    content: &str,
) -> Result<Option<SourceLongOutcomeTelemetry>, SourceLongOutcomeError> {
    let mut latest = None;
    let lines: Vec<&str> = content.lines().collect();
    for (index, line) in lines.iter().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let row: OutcomeRow = match serde_json::from_str(line) {
            Ok(row) => row,
            Err(_) if index + 1 == lines.len() && !content.ends_with('\n') => break,
            Err(source) => {
                return Err(SourceLongOutcomeError::InvalidJson {
                    line: index + 1,
                    source,
                });
            }
        };
        validate_row(&row, index + 1)?;
        latest = Some(project(row));
    }
    Ok(latest)
}

fn validate_row(row: &OutcomeRow, line: usize) -> Result<(), SourceLongOutcomeError> {
    if row.event_type != "source_long_forward_outcome" {
        return Err(contract_error(line, "unexpected event_type"));
    }
    if row.execution_authority != "none" {
        return Err(contract_error(line, "execution_authority must be none"));
    }
    if row.payload.portfolio_interaction != "independent_observer_not_shared_execution" {
        return Err(contract_error(
            line,
            "portfolio interaction is not observe-only",
        ));
    }
    if !matches!(
        row.payload.recipe_id.as_str(),
        "bk_up_asia_conf06"
            | "fade_td_eu"
            | "bk_up_24h_challenger"
            | "trend_up_24h_challenger"
            | "trend_down_24h_direction_challenger"
    ) {
        return Err(contract_error(line, "unsupported recipe_id"));
    }
    if !matches!(
        row.payload.status.as_str(),
        "awaiting_evidence"
            | "entry_pending"
            | "open"
            | "no_fill"
            | "target_completed"
            | "time_exited"
            | "liquidated"
    ) {
        return Err(contract_error(line, "unsupported status"));
    }
    Ok(())
}

fn project(row: OutcomeRow) -> SourceLongOutcomeTelemetry {
    let payload = row.payload;
    let report = payload.report;
    SourceLongOutcomeTelemetry {
        observation_id: payload.observation_id,
        recipe_id: payload.recipe_id,
        status: payload.status,
        evidence_complete: payload.evidence_complete,
        last_event_time_utc: payload.last_event_time_utc,
        initial_equity_usd: payload.counterfactual_initial_equity_usd,
        final_equity_usd: report.final_equity,
        submitted_entries: report.submitted_entries,
        entry_filled_quantity: report.entry_filled_quantity,
        completed_trades: report.completed_trades,
        open_positions: report.open_positions,
        maker_fees_usd: report.maker_fees,
        taker_fees_usd: report.taker_fees,
        funding_cashflow_usd: report.funding_cashflow,
        liquidations: report.liquidations,
    }
}

fn contract_error(line: usize, message: &str) -> SourceLongOutcomeError {
    SourceLongOutcomeError::InvalidContract {
        line,
        message: message.to_string(),
    }
}
