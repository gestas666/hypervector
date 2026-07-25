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
    pub regime_reason: String,
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
    /// Index into the snapshot stream where this transition occurred
    /// (playhead-aware filtering and bar-walk simulation anchor).
    #[serde(default)]
    pub snapshot_index: usize,
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
    HypervelocityFixedTarget { target_margin_pct: f64 },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum RiskSizingMode {
    DynamicKellyPercent(f64),
    FixedUsdAmount(f64),
    EquityPercentage(f64),
    VolatilityParity,
    HypervelocityMarginParity { leverage: f64, target_pct: f64 },
}

/// Whether the hypervelocity execution engine uses maker-only or taker fills.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum FillMode {
    MakerOnly,
    TakerOk,
}

impl FillMode {
    pub fn label(&self) -> &'static str {
        match self {
            FillMode::MakerOnly => "maker",
            FillMode::TakerOk => "taker",
        }
    }
}

/// Controls how the split-position (two-target) partial exit behaves.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum SplitPositionMode {
    None,
    Active { tp1_ratio: f64 }, // e.g. 0.63 means 63% exits at TP1, 37% at TP2
}

impl SplitPositionMode {
    pub fn label(&self) -> &'static str {
        match self {
            SplitPositionMode::None => "OFF",
            SplitPositionMode::Active { .. } => "ACTIVE",
        }
    }

    pub fn tp1_ratio(&self) -> f64 {
        match self {
            SplitPositionMode::None => 1.0,
            SplitPositionMode::Active { tp1_ratio } => *tp1_ratio,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EngineConfig {
    pub leverage_mode: LeverageMode,
    pub static_leverage_value: f64,
    pub tpsl_strategy: TpSlStrategy,
    pub fixed_tp_pct: f64,
    pub fixed_sl_pct: f64,
    /// Margin-return target % for the hypervelocity strategy (e.g. 8.0%).
    pub margin_tp_pct: f64,
    /// Margin-return stop-loss % for the hypervelocity strategy (e.g. 2.0%).
    pub margin_sl_pct: f64,
    pub risk_sizing_mode: RiskSizingMode,
    pub fixed_risk_usd: f64,
    /// Fraction of equity risked per trade (e.g. 0.25 = 25%).
    pub equity_risk_frac: f64,
    pub fill_mode: FillMode,
    pub split_position_mode: SplitPositionMode,
    pub selected_option_index: usize,
}

impl Default for EngineConfig {
    fn default() -> Self {
        // Display fallback only. Effective values come from backend telemetry.
        Self {
            leverage_mode: LeverageMode::StaticMultiplier(40.0),
            static_leverage_value: 40.0,
            tpsl_strategy: TpSlStrategy::HypervelocityFixedTarget {
                target_margin_pct: 8.0,
            },
            fixed_tp_pct: 0.2,
            fixed_sl_pct: 0.0,
            margin_tp_pct: 8.0,
            margin_sl_pct: 0.0,
            risk_sizing_mode: RiskSizingMode::EquityPercentage(70.0),
            fixed_risk_usd: 7000.0,
            equity_risk_frac: 0.70,
            fill_mode: FillMode::MakerOnly,
            split_position_mode: SplitPositionMode::None,
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

/// Live position state tracked by the hypervelocity strategy.
#[derive(Debug, Clone)]
pub struct ActivePosition {
    pub direction: String, // "LONG" or "SHORT"
    pub entry_price: f64,
    pub size_btc: f64,
    pub leverage: f64,
    pub entry_equity: f64,
    pub peak_margin_pct: f64,
}

impl ActivePosition {
    pub fn flat() -> Self {
        Self {
            direction: "FLAT".to_string(),
            entry_price: 0.0,
            size_btc: 0.0,
            leverage: 0.0,
            entry_equity: 0.0,
            peak_margin_pct: 0.0,
        }
    }

    pub fn is_active(&self) -> bool {
        self.direction != "FLAT"
    }
}

// ---------------------------------------------------------------------------
// Live orderbook state for the hypervelocity depth ladder
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
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
            spread_bps: 0.0,
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
            gate_ok: false,
            gate_reason: "LIVE L2 UNAVAILABLE".to_string(),
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
