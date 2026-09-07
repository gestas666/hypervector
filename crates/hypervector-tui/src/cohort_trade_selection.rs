//! Independent selection state for lifecycle and exact-fill journals.

use crate::app::App;

/// Journal receiving navigation and detail commands on the trade screen.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum CohortTradeFocus {
    #[default]
    Lifecycles,
    Fills,
}

impl App {
    /// Resolve focus against journals that actually contain backend records.
    pub fn effective_cohort_trade_focus(&self) -> CohortTradeFocus {
        match (
            self.backend
                .cohort_checkpoint
                .user_trade_reflections()
                .is_empty(),
            self.backend.cohort.fills.is_empty(),
        ) {
            (true, false) => CohortTradeFocus::Fills,
            (false, true) => CohortTradeFocus::Lifecycles,
            _ => self.cohort_trade_focus,
        }
    }

    /// Move focus between the lifecycle and exact-fill journals.
    pub fn move_cohort_trade_focus(&mut self, delta: isize) {
        if self
            .backend
            .cohort_checkpoint
            .user_trade_reflections()
            .is_empty()
            || self.backend.cohort.fills.is_empty()
        {
            self.cohort_trade_focus = self.effective_cohort_trade_focus();
            return;
        }
        self.cohort_trade_focus = if delta < 0 {
            CohortTradeFocus::Lifecycles
        } else {
            CohortTradeFocus::Fills
        };
    }

    /// Select the next row in the focused journal without moving the other cursor.
    pub fn select_next_cohort_trade_record(&mut self) {
        match self.effective_cohort_trade_focus() {
            CohortTradeFocus::Lifecycles => {
                let count = self
                    .backend
                    .cohort_checkpoint
                    .user_trade_reflections()
                    .len();
                if self.selected_cohort_lifecycle_index + 1 < count {
                    self.selected_cohort_lifecycle_index += 1;
                }
            }
            CohortTradeFocus::Fills => {
                let count = self.backend.cohort.fills.len();
                if self.selected_cohort_fill_index + 1 < count {
                    self.selected_cohort_fill_index += 1;
                }
            }
        }
    }

    /// Select the previous row in the focused journal.
    pub fn select_prev_cohort_trade_record(&mut self) {
        match self.effective_cohort_trade_focus() {
            CohortTradeFocus::Lifecycles => {
                self.selected_cohort_lifecycle_index =
                    self.selected_cohort_lifecycle_index.saturating_sub(1);
            }
            CohortTradeFocus::Fills => {
                self.selected_cohort_fill_index = self.selected_cohort_fill_index.saturating_sub(1);
            }
        }
    }

    /// Toggle details only when the focused journal has the selected record.
    pub fn toggle_cohort_fill_modal(&mut self) {
        self.cohort_detail_scroll = 0;
        let valid = match self.effective_cohort_trade_focus() {
            CohortTradeFocus::Lifecycles => {
                self.selected_cohort_lifecycle_index
                    < self
                        .backend
                        .cohort_checkpoint
                        .user_trade_reflections()
                        .len()
            }
            CohortTradeFocus::Fills => {
                self.selected_cohort_fill_index < self.backend.cohort.fills.len()
            }
        };
        if valid {
            self.show_cohort_fill_modal = !self.show_cohort_fill_modal;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend_cohort::CohortFill;
    use crate::backend_cohort_trade_reflections::CohortTradeReflection;
    use serde_json::json;

    #[test]
    fn lifecycle_and_fill_cursors_move_independently() {
        let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        app.backend.cohort_checkpoint.trade_reflections = vec![
            CohortTradeReflection::default(),
            CohortTradeReflection::default(),
        ];
        app.backend.cohort.fills = vec![fill(1), fill(2)];

        app.select_next_cohort_trade_record();
        assert_eq!(app.selected_cohort_lifecycle_index, 1);
        assert_eq!(app.selected_cohort_fill_index, 0);

        app.move_cohort_trade_focus(1);
        app.select_next_cohort_trade_record();
        assert_eq!(app.selected_cohort_lifecycle_index, 1);
        assert_eq!(app.selected_cohort_fill_index, 1);
    }

    fn fill(oid: u64) -> CohortFill {
        serde_json::from_value(json!({
            "symbol":"BTC", "strategy_id":"test", "operation":"entry",
            "trade_id":oid, "oid":oid, "venue_timestamp_ms":oid,
            "price":100.0, "size":0.1, "side":"B", "direction":"Open Long",
            "fee_usd":0.01, "closed_pnl_usd":0.0, "expected_price":100.0,
            "slippage_bps":0.0, "acknowledgement_latency_ms":10,
            "markout_bps":0.0, "markout_horizon_ms":5000,
            "exit_reason":null
        }))
        .expect("valid fill")
    }
}
