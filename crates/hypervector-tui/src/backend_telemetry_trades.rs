//! Private reconstruction of completed paper and live trade records.

use serde_json::Value;

use crate::model::PaperTradeRecord;

use super::LedgerRow;
use super::backend_telemetry_trade_records::{close_live_trade, close_trade};

#[derive(Debug, Clone)]
pub(super) struct OpenTrade {
    pub(super) timestamp: String,
    pub(super) direction: String,
    pub(super) symbol: String,
    pub(super) entry_price: f64,
    pub(super) size: f64,
    pub(super) leverage: f64,
    pub(super) allocated_margin: f64,
    pub(super) realized_before_entry: f64,
    pub(super) entry_fee_usd: f64,
    pub(super) funding_payment_usd: f64,
    pub(super) entry_regime: TradeRegime,
}

#[derive(Debug, Clone)]
pub(super) struct TradeRegime {
    pub(super) primary: String,
    pub(super) state_1m: String,
    pub(super) state_5m: String,
    pub(super) context_15m: String,
}

struct LiveTradeAccumulator<'a> {
    trades: Vec<PaperTradeRecord>,
    open: Option<OpenTrade>,
    closes: Vec<&'a LedgerRow>,
    pending_reason: Option<String>,
    latest_regime: TradeRegime,
    position_qty: f64,
}

struct ShadowTradeAccumulator {
    trades: Vec<PaperTradeRecord>,
    open: Option<OpenTrade>,
    pending_reason: Option<String>,
    latest_realized: f64,
    latest_regime: TradeRegime,
}

impl TradeRegime {
    fn unknown() -> Self {
        Self {
            primary: "UNKNOWN".to_string(),
            state_1m: "UNKNOWN".to_string(),
            state_5m: "UNKNOWN".to_string(),
            context_15m: "UNKNOWN".to_string(),
        }
    }
}

impl ShadowTradeAccumulator {
    fn new() -> Self {
        Self {
            trades: Vec::new(),
            open: None,
            pending_reason: None,
            latest_realized: 0.0,
            latest_regime: TradeRegime::unknown(),
        }
    }

    fn observe(&mut self, run_id: &str, row: &LedgerRow, leverage: f64) {
        match row.action.as_str() {
            "regime_observation" => self.latest_regime = regime_from_row(row),
            "enter_long" | "enter_short" if is_filled_entry(row) => {
                if let Some(entry) = self.open.as_mut() {
                    merge_entry_fill(entry, row, leverage);
                } else {
                    self.open = Some(open_trade_from_row(
                        row,
                        leverage,
                        self.latest_realized,
                        self.latest_regime.clone(),
                    ));
                }
            }
            "funding" => add_live_funding(&mut self.open, row),
            "close" => self.observe_close(run_id, row),
            _ => {}
        }
        if let Some(realized) = row.realized_pnl {
            self.latest_realized = realized;
        }
    }

    fn observe_close(&mut self, run_id: &str, row: &LedgerRow) {
        if let Some(reason) = exit_reason(row) {
            self.pending_reason = Some(reason);
        }
        if is_filled_close(row)
            && let Some(entry) = self.open.take()
        {
            self.trades.push(close_trade(
                run_id,
                self.trades.len(),
                &entry,
                row,
                &self.latest_regime,
                self.pending_reason.as_deref(),
            ));
            self.pending_reason = None;
        }
    }
}

impl<'a> LiveTradeAccumulator<'a> {
    fn new() -> Self {
        Self {
            trades: Vec::new(),
            open: None,
            closes: Vec::new(),
            pending_reason: None,
            latest_regime: TradeRegime::unknown(),
            position_qty: 0.0,
        }
    }

    fn observe(&mut self, run_id: &str, row: &'a LedgerRow, leverage: f64) {
        if let Some(value) = row.position_qty {
            self.position_qty = value;
        }
        if matches!(row.action.as_str(), "enter_long" | "enter_short") && is_filled_entry(row) {
            self.finish(run_id);
        }
        match row.action.as_str() {
            "regime_observation" => self.latest_regime = regime_from_row(row),
            "enter_long" | "enter_short" if is_filled_entry(row) => {
                if let Some(entry) = self.open.as_mut() {
                    merge_entry_fill(entry, row, leverage);
                } else {
                    self.open = Some(open_trade_from_row(
                        row,
                        leverage,
                        0.0,
                        self.latest_regime.clone(),
                    ));
                }
            }
            "funding" => add_live_funding(&mut self.open, row),
            "close" => {
                self.pending_reason = self.pending_reason.take().or_else(|| exit_reason(row));
                if is_filled_close(row) {
                    self.closes.push(row);
                }
            }
            _ => {}
        }
    }

    fn finish(&mut self, run_id: &str) {
        finish_live_close(
            run_id,
            &mut self.trades,
            &mut self.open,
            &mut self.closes,
            &self.latest_regime,
            self.pending_reason.take(),
            self.position_qty,
        );
    }
}

pub(super) fn build_trades(
    run_id: &str,
    rows: &[&LedgerRow],
    configured_leverage: f64,
) -> Vec<PaperTradeRecord> {
    let has_live_positions = rows
        .iter()
        .any(|row| row.execution_mode.as_deref() == Some("live") && row.position_qty.is_some());
    if has_live_positions {
        build_live_position_trades(run_id, rows, configured_leverage)
    } else {
        build_shadow_trades(run_id, rows, configured_leverage)
    }
}

fn build_shadow_trades(
    run_id: &str,
    rows: &[&LedgerRow],
    configured_leverage: f64,
) -> Vec<PaperTradeRecord> {
    let mut accumulator = ShadowTradeAccumulator::new();
    for row in rows {
        accumulator.observe(run_id, row, configured_leverage);
    }
    accumulator.trades
}

fn build_live_position_trades(
    run_id: &str,
    rows: &[&LedgerRow],
    configured_leverage: f64,
) -> Vec<PaperTradeRecord> {
    let mut accumulator = LiveTradeAccumulator::new();
    for row in rows {
        accumulator.observe(run_id, row, configured_leverage);
    }
    accumulator.finish(run_id);
    accumulator.trades
}

fn add_live_funding(open: &mut Option<OpenTrade>, row: &LedgerRow) {
    if let Some(entry) = open.as_mut() {
        entry.funding_payment_usd += row.funding_payment_usd.unwrap_or(0.0);
    }
}

fn finish_live_close(
    run_id: &str,
    trades: &mut Vec<PaperTradeRecord>,
    open: &mut Option<OpenTrade>,
    closes: &mut Vec<&LedgerRow>,
    exit_regime: &TradeRegime,
    reason: Option<String>,
    position_qty: f64,
) {
    if position_qty.abs() > f64::EPSILON || closes.is_empty() {
        return;
    }
    let Some(entry) = open.take() else {
        closes.clear();
        return;
    };
    trades.push(close_live_trade(
        run_id,
        trades.len(),
        &entry,
        closes,
        exit_regime,
        reason.as_deref(),
    ));
    closes.clear();
}

pub(super) fn is_filled_entry(row: &LedgerRow) -> bool {
    let quantity = row.fill_qty.or(row.qty).or(row.position_qty).unwrap_or(0.0);
    !row.skipped && quantity.abs() > f64::EPSILON
}

fn is_filled_close(row: &LedgerRow) -> bool {
    match row.extra.get("event_type").and_then(Value::as_str) {
        Some("fill") => row.fill_px.is_some(),
        Some(_) => false,
        None => row.fill_px.is_some(),
    }
}

pub(super) fn exit_reason(row: &LedgerRow) -> Option<String> {
    row.exit_reason.clone().or_else(|| {
        row.extra
            .get("reason")
            .and_then(Value::as_str)
            .map(str::to_string)
    })
}

fn open_trade_from_row(
    row: &LedgerRow,
    configured_leverage: f64,
    realized_before_entry: f64,
    entry_regime: TradeRegime,
) -> OpenTrade {
    let leverage = row.leverage.unwrap_or(configured_leverage);
    let entry_price = row.fill_px.or(row.position_avg_px).unwrap_or(0.0);
    let size = row.fill_qty.or(row.qty).unwrap_or(0.0).abs();
    let allocated_margin = if leverage > 0.0 {
        entry_price * size / leverage
    } else {
        row.equity.unwrap_or(0.0)
    };
    OpenTrade {
        timestamp: row.feed_ts.clone(),
        direction: if row.action == "enter_short" {
            "SHORT"
        } else {
            "LONG"
        }
        .to_string(),
        symbol: row.symbol.clone().unwrap_or_else(|| "UNKNOWN".to_string()),
        entry_price,
        size,
        leverage,
        allocated_margin,
        realized_before_entry,
        entry_fee_usd: row.fee_usd.unwrap_or(0.0),
        funding_payment_usd: 0.0,
        entry_regime,
    }
}

fn merge_entry_fill(entry: &mut OpenTrade, row: &LedgerRow, configured_leverage: f64) {
    let fill_size = row.fill_qty.or(row.qty).unwrap_or(0.0).abs();
    let fill_price = row.fill_px.or(row.position_avg_px).unwrap_or(0.0);
    if fill_size <= f64::EPSILON || fill_price <= 0.0 {
        return;
    }
    let total_size = entry.size + fill_size;
    entry.entry_price = (entry.entry_price * entry.size + fill_price * fill_size) / total_size;
    entry.size = total_size;
    let leverage = row.leverage.unwrap_or(configured_leverage);
    if leverage > 0.0 {
        entry.allocated_margin += fill_price * fill_size / leverage;
    }
    entry.entry_fee_usd += row.fee_usd.unwrap_or(0.0);
}

fn regime_from_row(row: &LedgerRow) -> TradeRegime {
    TradeRegime {
        primary: row
            .primary_regime
            .clone()
            .unwrap_or_else(|| "UNKNOWN".to_string()),
        state_1m: row
            .extra
            .get("state_1m")
            .and_then(Value::as_str)
            .unwrap_or("UNKNOWN")
            .to_string(),
        state_5m: row
            .extra
            .get("state_5m")
            .and_then(Value::as_str)
            .unwrap_or("UNKNOWN")
            .to_string(),
        context_15m: row
            .extra
            .get("context_15m")
            .and_then(Value::as_str)
            .unwrap_or("UNKNOWN")
            .to_string(),
    }
}
