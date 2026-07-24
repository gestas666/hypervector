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
