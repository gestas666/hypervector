//! Data models for Quant TA & Microstructure Regime Detector Cockpit.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RegimeState {
    BullMomentum,
    BearMomentum,
    VolatilityCoiling,
    FundingCarry,
    RangeChop,
}

impl RegimeState {
    pub fn display_name(&self) -> &'static str {
        match self {
            RegimeState::BullMomentum => "TREND_UP (BULL MOMENTUM EXPANSION)",
            RegimeState::BearMomentum => "TREND_DOWN (BEAR MOMENTUM EXPANSION)",
            RegimeState::VolatilityCoiling => "BREAKOUT (VOLATILITY COILING COMPRESSION)",
            RegimeState::FundingCarry => "TRANSITION (FUNDING CARRY REVERSAL)",
            RegimeState::RangeChop => "RANGE (RANGE CHOP / HIGH FRICTION)",
        }
    }

    pub fn primary_label(&self) -> &'static str {
        match self {
            RegimeState::BullMomentum => "TREND_UP",
            RegimeState::BearMomentum => "TREND_DOWN",
            RegimeState::VolatilityCoiling => "BREAKOUT",
            RegimeState::FundingCarry => "TRANSITION",
            RegimeState::RangeChop => "RANGE",
        }
    }

    pub fn icon(&self) -> &'static str {
        match self {
            RegimeState::BullMomentum => "🔥",
            RegimeState::BearMomentum => "🔻",
            RegimeState::VolatilityCoiling => "⚡",
            RegimeState::FundingCarry => "💰",
            RegimeState::RangeChop => "🛡️",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegimeSnapshot {
    pub timestamp_str: String,
    pub timestamp_ms: u64,
    pub price: f64,
    pub high: f64,
    pub low: f64,
    pub volume: f64,
    pub state: RegimeState,
    pub confidence: f64,
    pub opi: f64,
    pub spread_bps: f64,
    pub bid_depth_ratio: f64,
    pub bbwp_percentile: f64,
    pub rsi: f64,
    pub funding_zscore: f64,
    pub trend_1m: String,
    pub trend_5m: String,
    pub trend_15m: String,
    pub long_weight: f64,
    pub short_weight: f64,
    pub max_leverage: f64,
    pub dynamic_leverage: f64,
    pub taker_allowed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegimeEvent {
    pub timestamp_str: String,
    pub from_state: RegimeState,
    pub to_state: RegimeState,
    pub trigger_reason: String,
    pub price: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaperTradeRecord {
    pub trade_id: String,
    pub timestamp_str: String,
    pub symbol: String,
    pub direction: String, // "LONG" or "SHORT"
    pub entry_price: f64,
    pub exit_price: f64,
    pub size_btc: f64,
    pub leverage: f64,
    pub pnl_usd: f64,
    pub pnl_pct: f64,
    pub exit_reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivePaperStats {
    pub initial_capital: f64,
    pub current_equity: f64,
    pub realized_pnl: f64,
    pub unrealized_pnl: f64,
    pub total_trades: usize,
    pub wins: usize,
    pub losses: usize,
    pub win_rate_pct: f64,
    pub profit_factor: f64,
    pub max_drawdown_pct: f64,
    pub avg_win_usd: f64,
    pub avg_loss_usd: f64,
}
