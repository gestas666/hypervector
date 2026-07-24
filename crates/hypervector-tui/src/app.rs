//! Application state and event loop controller for Quant TA Regime Cockpit.

use crate::model::{ActivePosition, get_coin_max_leverage, BookLevel, EngineConfig, HypervelocityBookState, HypervelocityTrade, LeverageMode, LivePaperStats, PaperTradeRecord, RegimeEvent, RegimeSnapshot, RegimeState, RiskSizingMode, SimulatedTrade, TpSlStrategy};
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
    pub active_tab: usize, // 0 = Regime Engine, 1 = Strategy Policy, 2 = Live Shadow Dashboard, 3 = Hypervelocity, 4 = Engine & Risk Config
    // Hypervelocity state
    pub active_position: ActivePosition,
    pub previous_margin_pct: f64,
    pub hv_trades: Vec<HypervelocityTrade>,
    pub position_run_direction: String,
    pub run_position_index: u32,
    pub run_wins: u32,
    pub run_pnl: f64,
    pub equity_history: Vec<f64>,
    pub book_state: HypervelocityBookState,
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
            active_position: ActivePosition::flat(),
            previous_margin_pct: 0.0,
            hv_trades: Vec::new(),
            position_run_direction: "FLAT".to_string(),
            run_position_index: 0,
            run_wins: 0,
            run_pnl: 0.0,
            equity_history: Vec::new(),
            book_state: HypervelocityBookState::default(),
        };
        app.rebuild_events();
        app.rebuild_paper_trades();
        app.rebuild_hypervelocity_trades();
        app.update_book_state();
        app
    }

    pub fn toggle_tab(&mut self) {
        self.active_tab = (self.active_tab + 1) % 5;
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

    /// Run the shared position-sizing + PnL simulation once and materialise
    /// both the paper journal and hypervelocity trade list from the results.
    fn simulate_trades(&self) -> (Vec<SimulatedTrade>, LivePaperStats) {
        let initial_cap = 10000.0;
        let mut equity = initial_cap;
        let mut realized_pnl = 0.0;
        let mut wins: usize = 0;
        let mut losses: usize = 0;
        let mut gross_win = 0.0;
        let mut gross_loss = 0.0;
        let mut max_eq = initial_cap;
        let mut max_dd_pct = 0.0;
        let mut trades: Vec<SimulatedTrade> = Vec::new();

        let max_coin_lev = get_coin_max_leverage(&self.symbol);
        let lev = match self.config.leverage_mode {
            LeverageMode::DynamicML => 2.0_f64.min(max_coin_lev),
            LeverageMode::StaticMultiplier(mult) => mult.min(max_coin_lev),
        };
        let tp_pct = self.config.fixed_tp_pct;
        let sl_pct = self.config.fixed_sl_pct;

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

            let pos_val = equity * 0.25 * lev;
            let size_btc = pos_val / entry_p;

            let pnl_usd = if direction == "LONG" {
                (exit_p - entry_p) * size_btc
            } else {
                (entry_p - exit_p) * size_btc
            };

            let margin_pnl_pct = if pos_val > 0.0 { (pnl_usd / (pos_val / lev)) * 100.0 } else { 0.0 };

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

            let exit_reason = if idx + 1 >= self.events.len() {
                "OPEN".to_string()
            } else if margin_pnl_pct >= tp_pct {
                "tp1".to_string()
            } else if margin_pnl_pct <= -sl_pct {
                "SL".to_string()
            } else {
                self.events[idx + 1].to_state.primary_label().to_string()
            };

            trades.push(SimulatedTrade {
                index: (idx + 1) as u32,
                timestamp_str: ev.timestamp_str.clone(),
                direction: direction.to_string(),
                entry_price: entry_p,
                exit_price: exit_p,
                size_btc,
                leverage: lev,
                pnl_usd,
                margin_pnl_pct,
                exit_reason,
            });
        }

        let total = wins + losses;
        let win_rate = if total > 0 { (wins as f64 / total as f64) * 100.0 } else { 0.0 };
        let pf = if gross_loss > 0.0 { gross_win / gross_loss } else { gross_win };

        let stats = LivePaperStats {
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

        (trades, stats)
    }

    pub fn rebuild_paper_trades(&mut self) {
        let (trades, stats) = self.simulate_trades();
        self.paper_trades = trades.iter().map(|t| PaperTradeRecord {
            trade_id: format!("TRD-{:04}", t.index),
            timestamp_str: t.timestamp_str.clone(),
            symbol: self.symbol.clone(),
            direction: t.direction.clone(),
            entry_price: t.entry_price,
            exit_price: t.exit_price,
            size_btc: t.size_btc,
            leverage: t.leverage,
            pnl_usd: t.pnl_usd,
            pnl_pct: t.margin_pnl_pct,
            exit_reason: t.exit_reason.clone(),
        }).collect();
        self.paper_stats = stats;
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
                    LeverageMode::DynamicML => LeverageMode::StaticMultiplier(1.0),
                    LeverageMode::StaticMultiplier(v) if v < 2.0 => LeverageMode::StaticMultiplier(2.0),
                    LeverageMode::StaticMultiplier(v) if v < 3.0 => LeverageMode::StaticMultiplier(3.0),
                    LeverageMode::StaticMultiplier(v) if v < 5.0 => LeverageMode::StaticMultiplier(5.0),
                    LeverageMode::StaticMultiplier(v) if v < 10.0 => LeverageMode::StaticMultiplier(10.0),
                    LeverageMode::StaticMultiplier(v) if v < 20.0 => LeverageMode::StaticMultiplier(20.0),
                    LeverageMode::StaticMultiplier(v) if v < 25.0 => LeverageMode::StaticMultiplier(25.0),
                    LeverageMode::StaticMultiplier(v) if v < 30.0 => LeverageMode::StaticMultiplier(30.0),
                    LeverageMode::StaticMultiplier(v) if v < 40.0 => LeverageMode::StaticMultiplier(40.0),
                    LeverageMode::StaticMultiplier(v) if v < 50.0 => LeverageMode::StaticMultiplier(50.0),
                    LeverageMode::StaticMultiplier(v) if v < 100.0 => LeverageMode::StaticMultiplier(100.0),
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

    pub fn increase_config_value(&mut self) {
        let max_lev = get_coin_max_leverage(&self.symbol);
        if self.config.selected_option_index == 0 {
            let cur = match self.config.leverage_mode {
                LeverageMode::DynamicML => 1.0,
                LeverageMode::StaticMultiplier(v) => v,
            };
            let next = (cur + 1.0).min(max_lev);
            self.config.leverage_mode = LeverageMode::StaticMultiplier(next);
            self.rebuild_paper_trades();
        }
    }

    pub fn decrease_config_value(&mut self) {
        if self.config.selected_option_index == 0 {
            let cur = match self.config.leverage_mode {
                LeverageMode::DynamicML => 1.0,
                LeverageMode::StaticMultiplier(v) => v,
            };
            let next = (cur - 1.0).max(1.0);
            if next <= 1.0 {
                self.config.leverage_mode = LeverageMode::DynamicML;
            } else {
                self.config.leverage_mode = LeverageMode::StaticMultiplier(next);
            }
            self.rebuild_paper_trades();
        }
    }

    // -----------------------------------------------------------------------
    // Hypervelocity methods
    // -----------------------------------------------------------------------

    pub fn rebuild_hypervelocity_trades(&mut self) {
        let (trades, stats) = self.simulate_trades();

        // Build equity history from the simulated trade stream
        self.equity_history = vec![stats.initial_capital];
        let mut eq = stats.initial_capital;
        for t in &trades {
            eq += t.pnl_usd;
            self.equity_history.push(eq);
        }

        // Build hypervelocity trade list with directional-run tracking
        // and live position state derived from most recent trade
        self.hv_trades.clear();
        let mut current_direction = String::from("FLAT");
        let mut run_idx: u32 = 0;
        let mut run_wins: u32 = 0;
        let mut run_pnl: f64 = 0.0;
        let mut last_pos: Option<ActivePosition> = None;

        for t in &trades {
            if t.direction != current_direction {
                current_direction = t.direction.clone();
                run_idx = 1;
                run_wins = 0;
                run_pnl = 0.0;
            } else {
                run_idx += 1;
            }

            if t.pnl_usd >= 0.0 {
                run_wins += 1;
            }
            run_pnl += t.pnl_usd;

            let exit_label = match t.exit_reason.as_str() {
                "tp1" | "tp2" | "SL" | "OPEN" => t.exit_reason.clone(),
                other => other.to_string(),
            };

            self.hv_trades.push(HypervelocityTrade {
                index: t.index,
                tick_closed: 0,
                direction: t.direction.clone(),
                pnl_usd: t.pnl_usd,
                margin_pnl_pct: t.margin_pnl_pct,
                exit_reason: exit_label.clone(),
                fill_type: "maker".to_string(),
            });

            // Track live position: record the most recent trade as a candidate
            // position. If the last trade's exit reason is "OPEN", it's still
            // open; otherwise the position is closed.
            last_pos = Some(ActivePosition {
                direction: t.direction.clone(),
                entry_price: t.entry_price,
                size_btc: t.size_btc,
                leverage: t.leverage,
                entry_equity: eq - t.pnl_usd,
                peak_margin_pct: t.margin_pnl_pct.max(0.0),
            });
        }

        // If the most recent trade is closed (exit_reason != "OPEN"), position is flat
        self.active_position = if let Some(pos) = last_pos {
            if let Some(last_trade) = trades.last() {
                if last_trade.exit_reason != "OPEN" {
                    ActivePosition::flat()
                } else {
                    pos
                }
            } else {
                ActivePosition::flat()
            }
        } else {
            ActivePosition::flat()
        };

        self.position_run_direction = current_direction;
        self.run_position_index = run_idx;
        self.run_wins = run_wins;
        self.run_pnl = run_pnl;
    }

    pub fn update_book_state(&mut self) {
        let spread_bps = self.current_snapshot().spread_bps;
        let opi = self.current_snapshot().opi;
        let bid_depth_ratio = self.current_snapshot().bid_depth_ratio;
        let price = self.current_snapshot().price;
        let volume = self.current_snapshot().volume;

        let bs = &mut self.book_state;

        bs.spread_bps = spread_bps;
        bs.opi = opi;
        bs.depth_ratio = bid_depth_ratio;
        bs.microprice_delta_bps = 0.0;

        let spread_ok = spread_bps <= 5.0;
        let depth_ok = bid_depth_ratio >= 0.5 && bid_depth_ratio <= 2.0;

        bs.gate_ok = spread_ok && depth_ok;
        bs.gate_reason = if !spread_ok {
            format!("SPREAD {:.1}bps WIDE", spread_bps)
        } else if !depth_ok {
            "DEPTH IMBALANCED".to_string()
        } else {
            String::new()
        };

        let spread_dollars = spread_bps * price / 10000.0;
        let base_size = volume.max(0.5);
        let mid = price;

        bs.bid_levels.clear();
        bs.ask_levels.clear();

        let mut bid_changes: Vec<u64> = Vec::with_capacity(5);
        let mut ask_changes: Vec<u64> = Vec::with_capacity(5);
        let now = self.tick_count;

        for i in 0..5 {
            let offset = spread_dollars * 0.5 + i as f64 * spread_dollars * 0.8;
            let bid_sz = base_size * bid_depth_ratio * (1.0 - i as f64 * 0.18).max(0.1);
            let ask_sz = base_size / bid_depth_ratio.max(0.1) * (1.0 - i as f64 * 0.18).max(0.1);

            // Check if this level's size changed vs previous value
            let old_bid = bs.bid_levels.get(i).map(|l| l.size).unwrap_or(0.0);
            let old_ask = bs.ask_levels.get(i).map(|l| l.size).unwrap_or(0.0);

            bid_changes.push(if (bid_sz - old_bid).abs() > old_bid.max(0.001) * 0.01 { now } else { bs.bid_last_change.get(i).copied().unwrap_or(0) });
            ask_changes.push(if (ask_sz - old_ask).abs() > old_ask.max(0.001) * 0.01 { now } else { bs.ask_last_change.get(i).copied().unwrap_or(0) });

            bs.bid_levels.push(BookLevel { price: mid - offset, size: bid_sz });
            bs.ask_levels.push(BookLevel { price: mid + offset, size: ask_sz });
        }

        bs.bid_last_change = bid_changes;
        bs.ask_last_change = ask_changes;

        if let (Some(b), Some(a)) = (bs.bid_levels.first(), bs.ask_levels.first()) {
            bs.touch_bid_sz = b.size;
            bs.touch_ask_sz = a.size;
        }
    }

    pub fn sparkline_equity_data(&self) -> Vec<u64> {
        if self.equity_history.is_empty() {
            return vec![50];
        }
        let len = self.equity_history.len();
        let start = if len > 60 { len - 60 } else { 0 };
        let window = &self.equity_history[start..];
        let (min, max) = window.iter().fold((f64::MAX, f64::MIN), |(mn, mx), &v| (mn.min(v), mx.max(v)));
        let range = (max - min).max(0.01);
        window.iter().map(|&v| (((v - min) / range) * 100.0) as u64).collect()
    }

    pub fn compute_hypervelocity_signals(&self) -> Vec<bool> {
        let snap = self.current_snapshot();
        let rsi_val = snap.rsi;
        let funding_z = snap.funding_zscore;
        let is_bull = snap.long_weight > 0.0 && snap.short_weight == 0.0;
        let is_bear = snap.short_weight > 0.0 && snap.long_weight == 0.0;

        vec![
            is_bull || is_bear,                         // EMA direction gate
            rsi_val > 30.0 && rsi_val < 70.0,           // RSI filter
            snap.bbwp_percentile > 20.0,                 // Chop/ADX (proxy: BBWP > coiling threshold)
            snap.confidence > 0.3,                       // Momentum pulse (proxy: conviction)
            funding_z.abs() < 1.8,                       // Funding gate
            self.book_state.gate_ok,                     // Orderbook gate
        ]
    }
}
