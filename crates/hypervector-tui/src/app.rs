//! Application state and event loop controller for Quant TA Regime Cockpit.

use crate::backend_telemetry::BackendTelemetrySnapshot;
use crate::model::{
    ActivePosition, EngineConfig, HypervelocityBookState, HypervelocityTrade, LivePaperStats,
    PaperTradeRecord, RegimeEvent, RegimeSnapshot, RegimeState,
};
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
    pub selected_trade_index: usize,
    pub show_trade_detail_modal: bool,
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
    pub backend: BackendTelemetrySnapshot,
}

impl App {
    pub fn new(
        symbol: String,
        timeframe: String,
        snapshots: Vec<RegimeSnapshot>,
        is_live: bool,
        is_synthetic: bool,
    ) -> Self {
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
            selected_trade_index: 0,
            show_trade_detail_modal: false,
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
            backend: BackendTelemetrySnapshot::disconnected("backend ledger not loaded"),
        };
        app.rebuild_events();
        if !app.is_live && !app.snapshots.is_empty() {
            app.update_book_state();
        }
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

    pub fn select_next_trade(&mut self) {
        if !self.paper_trades.is_empty() && self.selected_trade_index + 1 < self.paper_trades.len()
        {
            self.selected_trade_index += 1;
        }
    }

    pub fn select_prev_trade(&mut self) {
        if self.selected_trade_index > 0 {
            self.selected_trade_index -= 1;
        }
    }

    pub fn toggle_trade_modal(&mut self) {
        if !self.paper_trades.is_empty() {
            self.show_trade_detail_modal = !self.show_trade_detail_modal;
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
        let start = self.current_index.saturating_sub(60);
        let end = (self.current_index + 1).min(self.snapshots.len());
        let window = &self.snapshots[start..end];
        let (min, max) = window.iter().fold((f64::MAX, f64::MIN), |(mn, mx), s| {
            (mn.min(s.price), mx.max(s.price))
        });
        let range = (max - min).max(0.01);
        window
            .iter()
            .map(|s| (((s.price - min) / range) * 100.0) as u64)
            .collect()
    }

    pub fn sparkline_bbwp_data(&self) -> Vec<u64> {
        let start = self.current_index.saturating_sub(60);
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

    /// Refresh display-only market telemetry after the playhead moves.
    pub fn refresh_playhead_state(&mut self) {
        if self.snapshots.is_empty() {
            return;
        }
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
        if self.is_live {
            if !self.snapshots.is_empty() {
                self.current_index = self.snapshots.len() - 1;
            }
            return;
        }
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

    pub(crate) fn rebuild_events(&mut self) {
        self.events.clear();
        if self.snapshots.len() < 2 {
            return;
        }
        for i in 1..self.snapshots.len() {
            let prev = &self.snapshots[i - 1];
            let curr = &self.snapshots[i];
            if prev.state != curr.state {
                let fallback_reason = match curr.state {
                    RegimeState::BullMomentum | RegimeState::BearMomentum => "5m_primary_trend",
                    RegimeState::VolatilityCoiling => "breakout_reason_not_reported",
                    RegimeState::FundingCarry => "transition_reason_not_reported",
                    RegimeState::RangeChop => "range_reason_not_reported",
                    RegimeState::Unknown => "unknown_reason_not_reported",
                };
                let reason = if curr.regime_reason.is_empty() {
                    fallback_reason
                } else {
                    &curr.regime_reason
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

    pub fn select_next_config(&mut self) {
        let count = crate::config_view::backend_config_rows(&self.backend).len();
        if self.config.selected_option_index + 1 < count {
            self.config.selected_option_index += 1;
        }
    }

    pub fn select_prev_config(&mut self) {
        if self.config.selected_option_index > 0 {
            self.config.selected_option_index -= 1;
        }
    }

    pub fn toggle_config_option(&mut self) {
        // Backend-owned configuration is intentionally immutable from the TUI.
    }

    pub fn increase_config_value(&mut self) {
        // Backend-owned configuration is intentionally immutable from the TUI.
    }

    pub fn decrease_config_value(&mut self) {
        // Backend-owned configuration is intentionally immutable from the TUI.
    }

    pub fn update_book_state(&mut self) {
        let snapshot = self.current_snapshot().clone();
        self.book_state = HypervelocityBookState::default();
        if snapshot.microstructure_source != "not_available" {
            self.book_state.spread_bps = snapshot.spread_bps;
            self.book_state.opi = snapshot.opi;
            self.book_state.depth_ratio = snapshot.bid_depth_ratio;
            self.book_state.gate_reason = format!(
                "{} AGGREGATES; L2 LEVELS NOT RECORDED",
                snapshot.microstructure_source
            );
        }
    }

    pub fn sparkline_equity_data(&self) -> Vec<u64> {
        if self.equity_history.is_empty() {
            return vec![50];
        }
        let len = self.equity_history.len();
        let start = len.saturating_sub(60);
        let window = &self.equity_history[start..];
        let (min, max) = window
            .iter()
            .fold((f64::MAX, f64::MIN), |(mn, mx), &v| (mn.min(v), mx.max(v)));
        let range = (max - min).max(0.01);
        window
            .iter()
            .map(|&v| (((v - min) / range) * 100.0) as u64)
            .collect()
    }
}
