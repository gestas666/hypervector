//! Application of authoritative backend telemetry to read-only TUI state.

use crate::app::App;
use crate::backend_market::BackendBookTelemetry;
use crate::backend_telemetry::{BackendConnectionState, BackendTelemetrySnapshot};
use crate::model::{BookLevel, HypervelocityBookState, HypervelocityTrade};

impl App {
    /// Apply a confirmed backend ledger snapshot without recalculating trades.
    pub fn apply_backend_telemetry(&mut self, telemetry: BackendTelemetrySnapshot) {
        self.backend = telemetry;
        self.apply_backend_regimes();
        self.apply_backend_state();
    }

    fn apply_backend_regimes(&mut self) {
        if self.backend.regime_snapshots.is_empty() {
            return;
        }
        self.snapshots = self.backend.regime_snapshots.clone();
        if let Some(book) = &self.backend.book
            && let Some(latest) = self.snapshots.last_mut()
        {
            latest.price = book.mid_price;
            latest.spread_bps = book.spread_bps;
            latest.opi = book.opi;
            latest.bid_depth_ratio = book.bid_depth_ratio;
        }
        self.current_index = self.snapshots.len() - 1;
        self.rebuild_events();
    }

    fn apply_backend_state(&mut self) {
        self.paper_trades = self.backend.trades.clone();
        self.selected_trade_index = self
            .selected_trade_index
            .min(self.paper_trades.len().saturating_sub(1));
        self.paper_stats = self.backend.stats.clone();
        self.active_position = self.backend.active_position.clone();
        self.equity_history = self.backend.equity_history.clone();
        self.hv_trades = self
            .paper_trades
            .iter()
            .enumerate()
            .map(|(index, trade)| HypervelocityTrade {
                index: (index + 1) as u32,
                tick_closed: 0,
                direction: trade.direction.clone(),
                pnl_usd: trade.pnl_usd,
                margin_pnl_pct: trade.pnl_pct,
                exit_reason: trade.exit_reason.clone(),
                fill_type: "backend".to_string(),
            })
            .collect();
        self.position_run_direction = if self.active_position.is_active() {
            self.active_position.direction.clone()
        } else {
            self.hv_trades
                .last()
                .map(|trade| trade.direction.clone())
                .unwrap_or_else(|| "FLAT".to_string())
        };
        self.run_position_index = self.hv_trades.len() as u32;
        self.run_wins = self
            .hv_trades
            .iter()
            .filter(|trade| trade.pnl_usd >= 0.0)
            .count() as u32;
        self.run_pnl = self.hv_trades.iter().map(|trade| trade.pnl_usd).sum();
        if let Some(book) = self.backend.book.clone() {
            self.apply_backend_book(&book);
        } else {
            self.book_state = HypervelocityBookState::default();
        }
    }

    fn apply_backend_book(&mut self, book: &BackendBookTelemetry) {
        let prior_bids: Vec<f64> = self
            .book_state
            .bid_levels
            .iter()
            .map(|level| level.size)
            .collect();
        let prior_asks: Vec<f64> = self
            .book_state
            .ask_levels
            .iter()
            .map(|level| level.size)
            .collect();
        self.book_state.spread_bps = book.spread_bps;
        self.book_state.opi = book.opi;
        self.book_state.depth_ratio = book.bid_depth_ratio;
        self.book_state.age_ms = book_age_ms(book);
        self.book_state.microprice_delta_bps = book.opi * book.spread_bps * 0.5;
        self.book_state.touch_bid_sz = first_size(&book.bid_levels);
        self.book_state.touch_ask_sz = first_size(&book.ask_levels);
        self.book_state.bid_last_change =
            changed_ticks(&prior_bids, &book.bid_levels, self.tick_count);
        self.book_state.ask_last_change =
            changed_ticks(&prior_asks, &book.ask_levels, self.tick_count);
        self.book_state.bid_levels = book.bid_levels.clone();
        self.book_state.ask_levels = book.ask_levels.clone();
        self.book_state.gate_ok = self.backend.connection == BackendConnectionState::Connected;
        self.book_state.gate_reason = format!("{} TELEMETRY", book.source);
    }
}

fn first_size(levels: &[BookLevel]) -> f64 {
    levels.first().map(|level| level.size).unwrap_or(0.0)
}

fn book_age_ms(book: &BackendBookTelemetry) -> f64 {
    let timestamp = book.exchange_ts_ms.unwrap_or(book.recv_ts_ms);
    (chrono::Utc::now().timestamp_millis() as f64 - timestamp).max(0.0)
}

fn changed_ticks(prior: &[f64], current: &[BookLevel], tick: u64) -> Vec<u64> {
    current
        .iter()
        .enumerate()
        .map(|(index, level)| {
            let old = prior.get(index).copied().unwrap_or(0.0);
            if (level.size - old).abs() > old.max(0.001) * 0.01 {
                tick
            } else {
                0
            }
        })
        .collect()
}
