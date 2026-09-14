//! Venue-backed lifecycle and partial protective execution facts.

use crate::backend_cohort::CohortExecutionPlan;
use serde::Deserialize;

/// Venue-backed position and lifecycle state for one coin.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortAssetSnapshot {
    pub symbol: String,
    pub state: String,
    pub direction_capability: Vec<String>,
    pub position_size_signed: f64,
    pub position_side: Option<String>,
    pub entry_oid: Option<u64>,
    pub stop_oid: Option<u64>,
    pub target_oid: Option<u64>,
    pub target_price: Option<f64>,
    pub execution_plan: Option<CohortExecutionPlan>,
    pub last_fault: Option<String>,
    pub mark_price: Option<f64>,
    #[serde(default)]
    pub market_reference_price: Option<f64>,
    #[serde(default)]
    pub mark_price_source: Option<String>,
    pub entry_price: Option<f64>,
    pub liquidation_price: Option<f64>,
    pub liquidation_distance_pct: Option<f64>,
    pub margin_used_usd: f64,
    pub position_value_usd: f64,
    pub unrealized_pnl_usd: f64,
    pub leverage: Option<u64>,
    pub fees_net_usd: Option<f64>,
    pub funding_net_usd: Option<f64>,
    pub realized_pnl_usd: Option<f64>,
    pub fill_count: Option<usize>,
    #[serde(default)]
    pub cost_scope: Option<String>,
    pub opened_at_ms: Option<i64>,
    pub protective_exit_pending: Option<bool>,
    pub partial_exit_fill_count: Option<usize>,
    pub partial_exit_size: Option<f64>,
    pub stop_protection: Option<String>,
}

impl CohortAssetSnapshot {
    /// Align position economics to the venue account snapshot timestamp.
    pub fn reconcile_position_mark(&mut self) -> Result<(), String> {
        self.validate_protective_progress()?;
        let market_reference = self.market_reference_price.or(self.mark_price);
        self.market_reference_price = market_reference;
        if self.position_size_signed == 0.0 {
            self.mark_price_source = Some("market_reference".into());
            return Ok(());
        }
        let mark = self.position_value_usd / self.position_size_signed.abs();
        if !mark.is_finite() || mark <= 0.0 {
            return Err(format!(
                "{} open position has invalid venue-implied mark",
                self.symbol
            ));
        }
        self.mark_price = Some(mark);
        self.mark_price_source = Some("venue_position_value_div_size".into());
        self.liquidation_distance_pct = self
            .liquidation_price
            .map(|liquidation| (liquidation - mark).abs() / mark * 100.0);
        Ok(())
    }

    fn validate_protective_progress(&self) -> Result<(), String> {
        let evidence = (
            self.protective_exit_pending,
            self.partial_exit_fill_count,
            self.partial_exit_size,
            self.stop_protection.as_deref(),
        );
        if evidence == (None, None, None, None) && self.opened_at_ms.is_none() {
            return Ok(());
        }
        let (Some(pending), Some(count), Some(size), Some(coverage)) = evidence else {
            return Err(format!(
                "{} incomplete partial protective evidence",
                self.symbol
            ));
        };
        let flat = self.position_size_signed == 0.0;
        let clock_valid = self.opened_at_ms.is_none_or(|value| value >= 0)
            && (flat || self.opened_at_ms.is_some());
        let receipts_valid = size.is_finite() && size >= 0.0 && (count == 0) == (size == 0.0);
        let coverage_valid = if flat {
            coverage == "flat" && !pending && count == 0
        } else {
            matches!(coverage, "covering" | "missing")
                && (coverage != "covering" || self.stop_oid.is_some())
                && (!pending || count > 0)
        };
        if !clock_valid || !receipts_valid || !coverage_valid {
            return Err(format!(
                "{} inconsistent partial protective evidence",
                self.symbol
            ));
        }
        Ok(())
    }
}
