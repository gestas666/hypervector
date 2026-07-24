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

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum LeverageMode {
    DynamicML,
    StaticMultiplier(f64),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum TpSlStrategy {
    PineCompositeVolatility,
    FixedPercentage { tp_pct: f64, sl_pct: f64 },
    ChandelierTrailing,
    ParabolicSarTrail,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum RiskSizingMode {
    DynamicKellyPercent(f64),
    FixedUsdAmount(f64),
    EquityPercentage(f64),
    VolatilityParity,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineConfig {
    pub leverage_mode: LeverageMode,
    pub static_leverage_value: f64,
    pub tpsl_strategy: TpSlStrategy,
    pub fixed_tp_pct: f64,
    pub fixed_sl_pct: f64,
    pub risk_sizing_mode: RiskSizingMode,
    pub fixed_risk_usd: f64,
    pub equity_risk_pct: f64,
    pub selected_option_index: usize,
}

impl Default for EngineConfig {
    fn default() -> Self {
        Self {
            leverage_mode: LeverageMode::DynamicML,
            static_leverage_value: 2.0,
            tpsl_strategy: TpSlStrategy::PineCompositeVolatility,
            fixed_tp_pct: 1.5,
            fixed_sl_pct: 0.75,
            risk_sizing_mode: RiskSizingMode::EquityPercentage(25.0),
            fixed_risk_usd: 250.0,
            equity_risk_pct: 25.0,
            selected_option_index: 0,
        }
    }
}

// ---------------------------------------------------------------------------
// Hypervelocity strategy trade record
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct HypervelocityTrade {
    pub index: u32,
    pub tick_closed: u64,
    pub direction: String,
    pub pnl_usd: f64,
    pub margin_pnl_pct: f64,
    pub exit_reason: String,
    pub fill_type: String,
}

// ---------------------------------------------------------------------------
// Live orderbook state for the hypervelocity depth ladder
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct BookLevel {
    pub price: f64,
    pub size: f64,
}

#[derive(Debug, Clone)]
pub struct HypervelocityBookState {
    pub spread_bps: f64,
    pub opi: f64,
    pub depth_ratio: f64,
    pub age_ms: f64,
    pub microprice_delta_bps: f64,
    pub touch_bid_sz: f64,
    pub touch_ask_sz: f64,
    pub bid_levels: Vec<BookLevel>,
    pub ask_levels: Vec<BookLevel>,
    pub bid_last_change: Vec<u64>,
    pub ask_last_change: Vec<u64>,
    pub gate_ok: bool,
    pub gate_reason: String,
}

impl Default for HypervelocityBookState {
    fn default() -> Self {
        Self {
            spread_bps: 1.8,
            opi: 0.0,
            depth_ratio: 1.0,
            age_ms: 0.0,
            microprice_delta_bps: 0.0,
            touch_bid_sz: 0.0,
            touch_ask_sz: 0.0,
            bid_levels: vec![],
            ask_levels: vec![],
            bid_last_change: vec![],
            ask_last_change: vec![],
            gate_ok: true,
            gate_reason: String::new(),
        }
    }
}

pub fn get_coin_max_leverage(symbol: &str) -> f64 {
    match symbol.to_uppercase().as_str() {
        "BTC" => 40.0,
        "ETH" => 25.0,
        "SOL" => 20.0,
        "AVAX" | "BNB" | "SUI" | "APT" | "DOGE" | "XRP" | "LINK" => 15.0,
        _ => 10.0,
    }
}
