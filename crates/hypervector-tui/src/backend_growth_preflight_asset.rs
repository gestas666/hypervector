//! Public projection model for staged growth-profile asset evidence.

/// Per-asset fee, sizing, and visible-depth readiness evidence.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct GrowthPreflightAssetTelemetry {
    pub symbol: String,
    pub effective_fee_status: String,
    pub one_way_taker_fee_bps: Option<f64>,
    pub margin_fraction: f64,
    pub leverage: f64,
    pub planned_margin_usd: f64,
    pub planned_notional_usd: f64,
    pub above_minimum_lot: bool,
    pub buy_complete: bool,
    pub buy_visible_cost_bps: Option<f64>,
    pub sell_complete: bool,
    pub sell_visible_cost_bps: Option<f64>,
    pub sizing_technically_ready: bool,
}
