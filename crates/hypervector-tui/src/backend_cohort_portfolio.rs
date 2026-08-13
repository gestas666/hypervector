//! Strict projection of rolling portfolio path evidence.

use serde::Deserialize;

/// Backend-authored capital path and peak exposure summary.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortPortfolioEvidence {
    pub status: String,
    pub initial_equity_usd: f64,
    pub final_equity_usd: f64,
    pub equity_change_usd: f64,
    pub maximum_equity_usd: f64,
    pub minimum_equity_usd: f64,
    pub maximum_drawdown_pct: f64,
    pub maximum_margin_used_usd: f64,
    pub maximum_notional_usd: f64,
    pub maximum_open_positions: usize,
    pub snapshot_count: usize,
}

pub(crate) fn project_portfolio(
    value: Option<CohortPortfolioEvidence>,
) -> Result<Option<CohortPortfolioEvidence>, String> {
    let Some(portfolio) = value else {
        return Ok(None);
    };
    let equities = [
        portfolio.initial_equity_usd,
        portfolio.final_equity_usd,
        portfolio.maximum_equity_usd,
        portfolio.minimum_equity_usd,
    ];
    let exposure = [
        portfolio.maximum_margin_used_usd,
        portfolio.maximum_notional_usd,
    ];
    let expected_change = portfolio.final_equity_usd - portfolio.initial_equity_usd;
    if portfolio.status != "observed"
        || portfolio.snapshot_count == 0
        || equities
            .iter()
            .any(|value| !value.is_finite() || *value <= 0.0)
        || exposure
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
        || !portfolio.equity_change_usd.is_finite()
        || (portfolio.equity_change_usd - expected_change).abs() > 1e-6
        || !(0.0..=100.0).contains(&portfolio.maximum_drawdown_pct)
        || portfolio.maximum_equity_usd < portfolio.minimum_equity_usd
    {
        return Err("portfolio path evidence is invalid".into());
    }
    Ok(Some(portfolio))
}
