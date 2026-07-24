//! Application state and event loop controller for Quant TA Regime Cockpit.

use crate::model::{EngineConfig, LeverageMode, LivePaperStats, PaperTradeRecord, RegimeEvent, RegimeSnapshot, RegimeState, RiskSizingMode, TpSlStrategy};
use crate::theme::CockpitTheme;

pub struct App {
    pub symbol: String,
    pub timeframe: String,
    pub snapshots: Vec<RegimeSnapshot>,
    pub current_index: usize,
    pub is_playing: bool,
    pub is_live: bool,
    pub is_synthetic: bool,
    pub playback_speed: f64,
    pub events: Vec<RegimeEvent>,
    pub paper_trades: Vec<PaperTradeRecord>,
    pub paper_stats: LivePaperStats,
    pub config: EngineConfig,
    pub theme: CockpitTheme,
    pub tick_count: u64,
    pub should_quit: bool,
    pub show_help_overlay: bool,
    pub selected_event_index: usize,
    pub show_event_detail_modal: bool,
    pub theme_mode: usize,
    pub active_tab: usize, // 0 = Regime Engine, 1 = Strategy Policy, 2 = Live Shadow Dashboard, 3 = Engine & Risk Config
}

impl App {
    pub fn new(symbol: String, timeframe: String, snapshots: Vec<RegimeSnapshot>, is_live: bool, is_synthetic: bool) -> Self {
        let mut app = Self {
            symbol,
            timeframe,
            snapshots,
            current_index: 0,
            is_playing: true,
            is_live,
            is_synthetic,
            playback_speed: 1.0,
            events: Vec::new(),
            paper_trades: Vec::new(),
            paper_stats: LivePaperStats {
                initial_capital: 10000.0,
                current_equity: 10000.0,
                realized_pnl: 0.0,
                unrealized_pnl: 0.0,
                total_trades: 0,
                wins: 0,
                losses: 0,
                win_rate_pct: 0.0,
                profit_factor: 0.0,
                max_drawdown_pct: 0.0,
                avg_win_usd: 0.0,
                avg_loss_usd: 0.0,
            },
            config: EngineConfig::default(),
            theme: CockpitTheme::default(),
            tick_count: 0,
            should_quit: false,
            show_help_overlay: false,
            selected_event_index: 0,
            show_event_detail_modal: false,
            theme_mode: 0,
            active_tab: 0,
        };
        app.rebuild_events();
        app.rebuild_paper_trades();
        app
    }

    pub fn toggle_tab(&mut self) {
        self.active_tab = (self.active_tab + 1) % 4;
    }

    pub fn select_next_event(&mut self) {
        if !self.events.is_empty() && self.selected_event_index + 1 < self.events.len() {
            self.selected_event_index += 1;
        }
    }

    pub fn select_prev_event(&mut self) {
        if self.selected_event_index > 0 {
            self.selected_event_index -= 1;
        }
    }

    pub fn toggle_event_modal(&mut self) {
        if !self.events.is_empty() {
            self.show_event_detail_modal = !self.show_event_detail_modal;
        }
    }

    pub fn toggle_help_overlay(&mut self) {
        self.show_help_overlay = !self.show_help_overlay;
    }

    pub fn current_snapshot(&self) -> &RegimeSnapshot {
        if self.snapshots.is_empty() {
            panic!("Snapshots cannot be empty");
        }
        let idx = self.current_index.min(self.snapshots.len() - 1);
        &self.snapshots[idx]
    }

    pub fn sparkline_price_data(&self) -> Vec<u64> {
        let start = if self.current_index > 60 { self.current_index - 60 } else { 0 };
        let end = (self.current_index + 1).min(self.snapshots.len());
        let window = &self.snapshots[start..end];
        let (min, max) = window.iter().fold((f64::MAX, f64::MIN), |(mn, mx), s| (mn.min(s.price), mx.max(s.price)));
        let range = (max - min).max(0.01);
        window.iter().map(|s| (((s.price - min) / range) * 100.0) as u64).collect()
    }

    pub fn sparkline_bbwp_data(&self) -> Vec<u64> {
        let start = if self.current_index > 60 { self.current_index - 60 } else { 0 };
        let end = (self.current_index + 1).min(self.snapshots.len());
        self.snapshots[start..end]
            .iter()
            .map(|s| (s.bbwp_percentile * 10.0) as u64)
            .collect()
    }

    pub fn toggle_play_pause(&mut self) {
        self.is_playing = !self.is_playing;
    }

    pub fn step_forward(&mut self) {
        if self.current_index + 1 < self.snapshots.len() {
            self.current_index += 1;
        }
    }

    pub fn step_backward(&mut self) {
        if self.current_index > 0 {
            self.current_index -= 1;
        }
    }

    pub fn cycle_speed(&mut self) {
        self.playback_speed = match self.playback_speed {
            1.0 => 2.0,
            2.0 => 5.0,
            5.0 => 10.0,
            _ => 1.0,
        };
    }

    pub fn cycle_timeframe(&mut self) {
        self.timeframe = match self.timeframe.as_str() {
            "1m" => "5m".into(),
            "5m" => "15m".into(),
            _ => "1m".into(),
        };
    }

    pub fn on_tick(&mut self) {
        self.tick_count += 1;
        if self.is_playing {
            if self.current_index + 1 < self.snapshots.len() {
                self.current_index += 1;
            } else if !self.snapshots.is_empty() {
                // Continuous live playback loop so live telemetry never freezes
                self.current_index = 0;
            }
        }
    }

    fn rebuild_events(&mut self) {
        self.events.clear();
        if self.snapshots.len() < 2 {
            return;
        }
        for i in 1..self.snapshots.len() {
            let prev = &self.snapshots[i - 1];
            let curr = &self.snapshots[i];
            if prev.state != curr.state {
                let reason = match curr.state {
                    RegimeState::BullMomentum => "15m/5m MTF Bullish + OPI >= 0.0",
                    RegimeState::BearMomentum => "15m/5m MTF Bearish + OPI <= 0.0",
                    RegimeState::VolatilityCoiling => "BBWP Percentile < 20.0 (Coiling)",
                    RegimeState::FundingCarry => "Funding Rate Z-Score |Z| >= 1.8",
                    RegimeState::RangeChop => "Spread > 6.0bps / Choppiness > 55",
                };
                self.events.push(RegimeEvent {
                    timestamp_str: curr.timestamp_str.clone(),
                    from_state: prev.state,
                    to_state: curr.state,
                    trigger_reason: reason.into(),
                    price: curr.price,
                });
            }
        }
    }

    pub fn rebuild_paper_trades(&mut self) {
        self.paper_trades.clear();
        let initial_cap = 10000.0;
        let mut equity = initial_cap;
        let mut realized_pnl = 0.0;
        let mut wins = 0;
        let mut losses = 0;
        let mut gross_win = 0.0;
        let mut gross_loss = 0.0;
        let mut max_eq = initial_cap;
        let mut max_dd_pct = 0.0;

        for (idx, ev) in self.events.iter().enumerate() {
            let direction = match ev.to_state {
                RegimeState::BullMomentum => "LONG",
                RegimeState::BearMomentum => "SHORT",
                _ => continue,
            };

            let entry_p = ev.price;
            let exit_p = if idx + 1 < self.events.len() {
                self.events[idx + 1].price
            } else {
                self.current_snapshot().price
            };

            let lev = 2.0;
            let pos_val = equity * 0.25 * lev;
            let size_btc = pos_val / entry_p;

            let pnl_usd = if direction == "LONG" {
                (exit_p - entry_p) * size_btc
            } else {
                (entry_p - exit_p) * size_btc
            };

            let pnl_pct = (pnl_usd / pos_val) * 100.0;

            realized_pnl += pnl_usd;
            equity += pnl_usd;

            if equity > max_eq {
                max_eq = equity;
            }
            let dd = (max_eq - equity) / max_eq * 100.0;
            if dd > max_dd_pct {
                max_dd_pct = dd;
            }

            if pnl_usd >= 0.0 {
                wins += 1;
                gross_win += pnl_usd;
            } else {
                losses += 1;
                gross_loss += pnl_usd.abs();
            }

            self.paper_trades.push(PaperTradeRecord {
                trade_id: format!("TRD-{:04}", idx + 1),
                timestamp_str: ev.timestamp_str.clone(),
                symbol: self.symbol.clone(),
                direction: direction.to_string(),
                entry_price: entry_p,
                exit_price: exit_p,
                size_btc,
                leverage: lev,
                pnl_usd,
                pnl_pct,
                exit_reason: if idx + 1 < self.events.len() { self.events[idx + 1].to_state.primary_label().to_string() } else { "OPEN_POSITION".to_string() },
            });
        }

        let total = wins + losses;
        let win_rate = if total > 0 { (wins as f64 / total as f64) * 100.0 } else { 0.0 };
        let pf = if gross_loss > 0.0 { gross_win / gross_loss } else { gross_win };

        self.paper_stats = LivePaperStats {
            initial_capital: initial_cap,
            current_equity: equity,
            realized_pnl,
            unrealized_pnl: 0.0,
            total_trades: total,
            wins,
            losses,
            win_rate_pct: win_rate,
            profit_factor: pf,
            max_drawdown_pct: max_dd_pct,
            avg_win_usd: if wins > 0 { gross_win / wins as f64 } else { 0.0 },
            avg_loss_usd: if losses > 0 { gross_loss / losses as f64 } else { 0.0 },
        };
    }

    pub fn select_next_config(&mut self) {
        if self.config.selected_option_index < 2 {
            self.config.selected_option_index += 1;
        }
    }

    pub fn select_prev_config(&mut self) {
        if self.config.selected_option_index > 0 {
            self.config.selected_option_index -= 1;
        }
    }

    pub fn toggle_config_option(&mut self) {
        match self.config.selected_option_index {
            0 => {
                self.config.leverage_mode = match self.config.leverage_mode {
                    LeverageMode::DynamicML => LeverageMode::StaticMultiplier(2.0),
                    LeverageMode::StaticMultiplier(2.0) => LeverageMode::StaticMultiplier(5.0),
                    LeverageMode::StaticMultiplier(5.0) => LeverageMode::StaticMultiplier(10.0),
                    _ => LeverageMode::DynamicML,
                };
            }
            1 => {
                self.config.tpsl_strategy = match self.config.tpsl_strategy {
                    TpSlStrategy::PineCompositeVolatility => TpSlStrategy::FixedPercentage { tp_pct: 1.5, sl_pct: 0.75 },
                    TpSlStrategy::FixedPercentage { .. } => TpSlStrategy::ChandelierTrailing,
                    TpSlStrategy::ChandelierTrailing => TpSlStrategy::ParabolicSarTrail,
                    TpSlStrategy::ParabolicSarTrail => TpSlStrategy::PineCompositeVolatility,
                };
            }
            2 => {
                self.config.risk_sizing_mode = match self.config.risk_sizing_mode {
                    RiskSizingMode::EquityPercentage(25.0) => RiskSizingMode::DynamicKellyPercent(15.0),
                    RiskSizingMode::DynamicKellyPercent(_) => RiskSizingMode::FixedUsdAmount(250.0),
                    RiskSizingMode::FixedUsdAmount(_) => RiskSizingMode::VolatilityParity,
                    RiskSizingMode::VolatilityParity => RiskSizingMode::EquityPercentage(25.0),
                    _ => RiskSizingMode::EquityPercentage(25.0),
                };
            }
            _ => {}
        }
        self.rebuild_paper_trades();
    }
}
