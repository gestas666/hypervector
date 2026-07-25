//! Application state and event loop controller for Quant TA Regime Cockpit.

use crate::model::{ActivePosition, FillMode, get_coin_max_leverage, BookLevel, EngineConfig, HypervelocityBookState, HypervelocityTrade, LeverageMode, LivePaperStats, PaperTradeRecord, RegimeEvent, RegimeSnapshot, RegimeState, RiskSizingMode, SimulatedTrade, SplitPositionMode, TpSlStrategy};
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
    pub active_tab: usize, // 0 = Dashboard, 1 = Regime Detection, 2 = Config
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
        app.rebuild_trade_state();
        app.update_book_state();
        app
    }

    pub fn toggle_tab(&mut self) {
        self.active_tab = (self.active_tab + 1) % 3;
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
            self.refresh_playhead_state();
        }
    }

    pub fn step_backward(&mut self) {
        if self.current_index > 0 {
            self.current_index -= 1;
            self.refresh_playhead_state();
        }
    }

    pub fn reset_playhead(&mut self) {
        self.current_index = 0;
        self.refresh_playhead_state();
    }

    /// Re-derive every playhead-dependent feed (book ladder, paper journal,
    /// hypervelocity trades, position, stats) after the index moves.
    pub fn refresh_playhead_state(&mut self) {
        if self.snapshots.is_empty() {
            return;
        }
        self.rebuild_trade_state();
        self.update_book_state();
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
            self.refresh_playhead_state();
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
                    snapshot_index: i,
                    from_state: prev.state,
                    to_state: curr.state,
                    trigger_reason: reason.into(),
                    price: curr.price,
                });
            }
        }
    }

    /// Playhead-aware simulation of the reverse-engineered hypervelocity
    /// strategy (docs/external plan section 4.5): entries at directional
    /// regime transitions, bar-walked exits at the margin TP target, margin
    /// SL stop, or trend-flip invalidation at the next transition. Supports
    /// split take-profit blending and compounding equity sizing.
    fn simulate_trades(&self) -> (Vec<SimulatedTrade>, LivePaperStats) {
        let initial_cap = 10000.0;
        let mut equity = initial_cap;
        let mut realized_pnl = 0.0;
        let mut unrealized_pnl = 0.0;
        let mut wins: usize = 0;
        let mut losses: usize = 0;
        let mut gross_win = 0.0;
        let mut gross_loss = 0.0;
        let mut max_eq = initial_cap;
        let mut max_dd_pct = 0.0;
        let mut trades: Vec<SimulatedTrade> = Vec::new();

        if self.snapshots.is_empty() {
            return (
                trades,
                LivePaperStats {
                    initial_capital: initial_cap,
                    current_equity: initial_cap,
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
            );
        }

        let upto = self.current_index.min(self.snapshots.len() - 1);
        let events: Vec<&RegimeEvent> = self
            .events
            .iter()
            .filter(|e| e.snapshot_index <= upto)
            .collect();

        let max_coin_lev = get_coin_max_leverage(&self.symbol);
        let lev = match self.config.leverage_mode {
            LeverageMode::DynamicML => 2.0_f64.min(max_coin_lev),
            LeverageMode::StaticMultiplier(mult) => mult.min(max_coin_lev),
        };
        // Margin-return targets are strategy-native; price barriers derive
        // by dividing by leverage (8% margin at 40x == 0.2% price move).
        let margin_tp_pct = self.config.margin_tp_pct;
        let margin_sl_pct = self.config.margin_sl_pct;
        let risk_frac = self.config.equity_risk_frac;
        let tp_frac = margin_tp_pct / lev.max(1.0) / 100.0;
        let sl_frac = margin_sl_pct / lev.max(1.0) / 100.0;
        let tp1_ratio = self.config.split_position_mode.tp1_ratio();
        // Plan section 8 (TP/SL ruler): TP2 is the tighter target at ~81%
        // of TP1 (6.5% vs 8.0% in the observed dataset).
        let tp2_margin_pct = margin_tp_pct * 0.8125;

        for (idx, ev) in events.iter().enumerate() {
            let direction = match ev.to_state {
                RegimeState::BullMomentum => "LONG",
                RegimeState::BearMomentum => "SHORT",
                _ => continue,
            };
            let is_long = direction == "LONG";
            let entry_p = ev.price;
            if entry_p <= 0.0 {
                continue;
            }

            let (tp_price, sl_price) = if is_long {
                (entry_p * (1.0 + tp_frac), entry_p * (1.0 - sl_frac))
            } else {
                (entry_p * (1.0 - tp_frac), entry_p * (1.0 + sl_frac))
            };

            let next_event = events.get(idx + 1);
            let walk_end = match next_event {
                Some(n) => n.snapshot_index.saturating_sub(1).min(upto),
                None => upto,
            };

            let mut peak_margin_pct: f64 = 0.0;
            let mut exit_price: Option<f64> = None;
            let mut exit_reason = String::new();

            for j in (ev.snapshot_index + 1)..=walk_end {
                let bar = &self.snapshots[j];
                let fav_move = if is_long {
                    (bar.high - entry_p) / entry_p
                } else {
                    (entry_p - bar.low) / entry_p
                };
                peak_margin_pct = peak_margin_pct.max(fav_move * lev * 100.0);

                let sl_hit = if is_long { bar.low <= sl_price } else { bar.high >= sl_price };
                let tp_hit = if is_long { bar.high >= tp_price } else { bar.low <= tp_price };

                // Conservative intrabar ordering: stop evaluated before target.
                if sl_hit {
                    exit_price = Some(sl_price);
                    exit_reason = "SL".into();
                    break;
                }
                if tp_hit {
                    if tp1_ratio < 1.0 {
                        let blended_margin =
                            tp1_ratio * margin_tp_pct + (1.0 - tp1_ratio) * tp2_margin_pct;
                        let blended_frac = blended_margin / lev.max(1.0) / 100.0;
                        exit_price = Some(if is_long {
                            entry_p * (1.0 + blended_frac)
                        } else {
                            entry_p * (1.0 - blended_frac)
                        });
                        exit_reason = "tp1+tp2".into();
                    } else {
                        exit_price = Some(tp_price);
                        exit_reason = "tp1".into();
                    }
                    break;
                }
            }

            let is_open = exit_price.is_none() && next_event.is_none();
            let exit_p = match exit_price {
                Some(p) => p,
                None => match next_event {
                    // Trend invalidation: flip closes the position at the
                    // transition price (plan section 3.1 exit rule 4).
                    Some(n) => {
                        exit_reason = n.to_state.primary_label().to_string();
                        n.price
                    }
                    None => {
                        exit_reason = "OPEN".into();
                        self.snapshots[upto].price
                    }
                },
            };

            // Position value = account equity * risk fraction * leverage
            let pos_val = equity * risk_frac * lev;
            let size_btc = pos_val / entry_p;
            let margin_posted = pos_val / lev.max(1.0);

            let pnl_usd = if is_long {
                (exit_p - entry_p) * size_btc
            } else {
                (entry_p - exit_p) * size_btc
            };
            let margin_pnl_pct = if margin_posted > 0.0 {
                (pnl_usd / margin_posted) * 100.0
            } else {
                0.0
            };
            peak_margin_pct = peak_margin_pct.max(margin_pnl_pct.max(0.0));

            if is_open {
                unrealized_pnl += pnl_usd;
            } else {
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
            }

            trades.push(SimulatedTrade {
                index: trades.len() as u32 + 1,
                timestamp_str: ev.timestamp_str.clone(),
                direction: direction.to_string(),
                entry_price: entry_p,
                exit_price: exit_p,
                size_btc,
                leverage: lev,
                pnl_usd,
                margin_pnl_pct,
                peak_margin_pct,
                exit_reason,
            });
        }

        let total = wins + losses;
        let win_rate = if total > 0 { (wins as f64 / total as f64) * 100.0 } else { 0.0 };
        let pf = if gross_loss > 0.0 { gross_win / gross_loss } else { gross_win };

        let stats = LivePaperStats {
            initial_capital: initial_cap,
            current_equity: equity + unrealized_pnl,
            realized_pnl,
            unrealized_pnl,
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

    pub fn select_next_config(&mut self) {
        if self.config.selected_option_index < 5 {
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
                self.config.tpsl_strategy = match &self.config.tpsl_strategy {
                    TpSlStrategy::PineCompositeVolatility => TpSlStrategy::FixedPercentage { tp_pct: 1.5, sl_pct: 0.75 },
                    TpSlStrategy::FixedPercentage { .. } => TpSlStrategy::ChandelierTrailing,
                    TpSlStrategy::ChandelierTrailing => TpSlStrategy::ParabolicSarTrail,
                    TpSlStrategy::ParabolicSarTrail => TpSlStrategy::HypervelocityTargetTrail { target_margin_pct: 8.0 },
                    TpSlStrategy::HypervelocityTargetTrail { .. } => TpSlStrategy::PineCompositeVolatility,
                };
            }
            2 => {
                // Margin TP target: cycle through common values
                let current = self.config.margin_tp_pct;
                self.config.margin_tp_pct = match current {
                    v if v < 3.0 => 4.0,
                    v if v < 5.0 => 6.0,
                    v if v < 7.0 => 8.0,
                    v if v < 9.0 => 10.0,
                    v if v < 11.0 => 12.0,
                    _ => 2.0,
                };
            }
            3 => {
                // Margin SL stop: cycle through common values
                let current = self.config.margin_sl_pct;
                self.config.margin_sl_pct = match current {
                    v if v < 1.5 => 2.0,
                    v if v < 2.5 => 3.0,
                    v if v < 3.5 => 4.0,
                    v if v < 5.0 => 5.0,
                    _ => 1.0,
                };
            }
            4 => {
                // Execution params: cycle fill mode then split position
                if self.config.fill_mode == FillMode::MakerOnly {
                    self.config.fill_mode = FillMode::TakerOk;
                } else {
                    self.config.fill_mode = FillMode::MakerOnly;
                    self.config.split_position_mode = match self.config.split_position_mode {
                        SplitPositionMode::None => SplitPositionMode::Active { tp1_ratio: 0.63 },
                        SplitPositionMode::Active { tp1_ratio: 0.63 } => SplitPositionMode::Active { tp1_ratio: 0.50 },
                        SplitPositionMode::Active { .. } => SplitPositionMode::None,
                    };
                }
            }
            5 => {
                self.config.risk_sizing_mode = match &self.config.risk_sizing_mode {
                    RiskSizingMode::EquityPercentage(_) => RiskSizingMode::DynamicKellyPercent(15.0),
                    RiskSizingMode::DynamicKellyPercent(_) => RiskSizingMode::FixedUsdAmount(250.0),
                    RiskSizingMode::FixedUsdAmount(_) => RiskSizingMode::VolatilityParity,
                    RiskSizingMode::VolatilityParity => RiskSizingMode::HypervelocityMarginParity { leverage: 40.0, target_pct: 8.0 },
                    RiskSizingMode::HypervelocityMarginParity { .. } => RiskSizingMode::EquityPercentage(25.0),
                };
            }
            _ => {}
        }
        self.rebuild_trade_state();
    }

    pub fn increase_config_value(&mut self) {
        let max_lev = get_coin_max_leverage(&self.symbol);
        match self.config.selected_option_index {
            0 => {
                let cur = match self.config.leverage_mode {
                    LeverageMode::DynamicML => 1.0,
                    LeverageMode::StaticMultiplier(v) => v,
                };
                let next = (cur + 1.0).min(max_lev);
                self.config.leverage_mode = LeverageMode::StaticMultiplier(next);
            }
            2 => {
                self.config.margin_tp_pct = (self.config.margin_tp_pct + 0.5).min(20.0);
            }
            3 => {
                self.config.margin_sl_pct = (self.config.margin_sl_pct + 0.5).min(10.0);
            }
            4 => {
                self.config.equity_risk_frac = (self.config.equity_risk_frac + 0.05).min(0.50);
            }
            _ => {}
        }
        self.rebuild_trade_state();
    }

    pub fn decrease_config_value(&mut self) {
        match self.config.selected_option_index {
            0 => {
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
            }
            2 => {
                self.config.margin_tp_pct = (self.config.margin_tp_pct - 0.5).max(0.5);
            }
            3 => {
                self.config.margin_sl_pct = (self.config.margin_sl_pct - 0.5).max(0.5);
            }
            4 => {
                self.config.equity_risk_frac = (self.config.equity_risk_frac - 0.05).max(0.05);
            }
            _ => {}
        }
        self.rebuild_trade_state();
    }

    // -----------------------------------------------------------------------
    // Trade state (paper journal + hypervelocity feeds)
    // -----------------------------------------------------------------------

    /// Run the playhead-aware simulation once and materialise every derived
    /// feed: paper journal, paper stats, hypervelocity trade tape, equity
    /// curve, directional-run tracking, and the live position panel.
    pub fn rebuild_trade_state(&mut self) {
        let (trades, stats) = self.simulate_trades();
        let fill_label = self.config.fill_mode.label().to_string();

        self.paper_trades = trades
            .iter()
            .map(|t| PaperTradeRecord {
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
            })
            .collect();

        // Realised equity curve (open trade PnL stays unrealised)
        self.equity_history = vec![stats.initial_capital];
        let mut eq = stats.initial_capital;
        for t in &trades {
            if t.exit_reason != "OPEN" {
                eq += t.pnl_usd;
                self.equity_history.push(eq);
            }
        }

        // Hypervelocity trade tape with directional-run tracking and the
        // live position derived from the most recent (possibly open) trade
        self.hv_trades.clear();
        let mut current_direction = String::from("FLAT");
        let mut run_idx: u32 = 0;
        let mut run_wins: u32 = 0;
        let mut run_pnl: f64 = 0.0;
        let mut last_pos: Option<ActivePosition> = None;
        let mut entry_eq = stats.initial_capital;

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

            self.hv_trades.push(HypervelocityTrade {
                index: t.index,
                tick_closed: 0,
                direction: t.direction.clone(),
                pnl_usd: t.pnl_usd,
                margin_pnl_pct: t.margin_pnl_pct,
                exit_reason: t.exit_reason.clone(),
                fill_type: fill_label.clone(),
            });

            last_pos = Some(ActivePosition {
                direction: t.direction.clone(),
                entry_price: t.entry_price,
                size_btc: t.size_btc,
                leverage: t.leverage,
                entry_equity: entry_eq,
                peak_margin_pct: t.peak_margin_pct,
            });

            if t.exit_reason != "OPEN" {
                entry_eq += t.pnl_usd;
            }
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
        self.paper_stats = stats;
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
        // Microprice tilt derived from order-book pressure imbalance:
        // positive OPI pulls the microprice toward the ask side.
        bs.microprice_delta_bps = opi * spread_bps * 0.5;

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

        let old_bids: Vec<f64> = bs.bid_levels.iter().map(|l| l.size).collect();
        let old_asks: Vec<f64> = bs.ask_levels.iter().map(|l| l.size).collect();

        bs.bid_levels.clear();
        bs.ask_levels.clear();

        let mut bid_changes: Vec<u64> = Vec::with_capacity(5);
        let mut ask_changes: Vec<u64> = Vec::with_capacity(5);
        let now = self.tick_count;

        for i in 0..5 {
            let offset = spread_dollars * 0.5 + i as f64 * spread_dollars * 0.8;
            let bid_sz = base_size * bid_depth_ratio * (1.0 - i as f64 * 0.18).max(0.1);
            let ask_sz = base_size / bid_depth_ratio.max(0.1) * (1.0 - i as f64 * 0.18).max(0.1);

            // Flash a level only when its size actually moved vs the prior tick
            let old_bid = old_bids.get(i).copied().unwrap_or(0.0);
            let old_ask = old_asks.get(i).copied().unwrap_or(0.0);

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
        // EMA direction gate: directional momentum regime with MTF agreement
        let is_directional = matches!(snap.state, RegimeState::BullMomentum | RegimeState::BearMomentum);
        let mtf_aligned = snap.trend_1m == snap.trend_15m;

        vec![
            is_directional && mtf_aligned,               // EMA direction gate
            rsi_val > 30.0 && rsi_val < 70.0,            // RSI filter (avoid extremes)
            snap.bbwp_percentile > 20.0,                 // Chop gate (proxy: BBWP above coiling floor)
            snap.confidence > 0.55,                      // Momentum pulse (proxy: regime conviction)
            funding_z.abs() < 1.8,                       // Funding gate
            self.book_state.gate_ok,                     // Orderbook gate
        ]
    }
}
