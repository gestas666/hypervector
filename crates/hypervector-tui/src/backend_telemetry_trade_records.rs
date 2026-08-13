//! Private construction of completed telemetry trade records.

use serde_json::Value;

use crate::model::PaperTradeRecord;

use super::LedgerRow;
use super::backend_telemetry_trades::{OpenTrade, TradeRegime, exit_reason};

struct LiveTradeFinancials {
    exit_price: f64,
    pnl: f64,
    pnl_pct: f64,
    exit_fee_usd: f64,
    total_cost_usd: f64,
}

pub(super) fn close_trade(
    run_id: &str,
    index: usize,
    entry: &OpenTrade,
    row: &LedgerRow,
    exit_regime: &TradeRegime,
    pending_exit_reason: Option<&str>,
) -> PaperTradeRecord {
    let financials = shadow_trade_financials(entry, row);
    PaperTradeRecord {
        trade_id: format!("{run_id}-{:04}", index + 1),
        timestamp_str: if row.feed_ts.is_empty() {
            entry.timestamp.clone()
        } else {
            row.feed_ts.clone()
        },
        entry_timestamp_str: entry.timestamp.clone(),
        exit_timestamp_str: row.feed_ts.clone(),
        symbol: row.symbol.clone().unwrap_or_else(|| entry.symbol.clone()),
        direction: entry.direction.clone(),
        entry_price: entry.entry_price,
        exit_price: financials.exit_price,
        size_btc: entry.size,
        leverage: row.leverage.unwrap_or(entry.leverage),
        pnl_usd: financials.pnl,
        pnl_pct: financials.pnl_pct,
        gross_pnl_usd: financials.pnl + financials.total_cost_usd,
        entry_fee_usd: entry.entry_fee_usd,
        exit_fee_usd: financials.exit_fee_usd,
        funding_payment_usd: entry.funding_payment_usd,
        total_cost_usd: financials.total_cost_usd,
        entry_primary_regime: entry.entry_regime.primary.clone(),
        entry_regime_1m: entry.entry_regime.state_1m.clone(),
        entry_regime_5m: entry.entry_regime.state_5m.clone(),
        entry_context_15m: entry.entry_regime.context_15m.clone(),
        exit_primary_regime: exit_regime.primary.clone(),
        exit_regime_1m: exit_regime.state_1m.clone(),
        exit_regime_5m: exit_regime.state_5m.clone(),
        exit_context_15m: exit_regime.context_15m.clone(),
        exit_reason: exit_reason(row)
            .or_else(|| pending_exit_reason.map(str::to_string))
            .unwrap_or_else(|| "exit_reason_not_recorded".to_string()),
    }
}

fn shadow_trade_financials(entry: &OpenTrade, row: &LedgerRow) -> LiveTradeFinancials {
    let live_fill = row.execution_mode.as_deref() == Some("live")
        && row.extra.get("event_type").and_then(Value::as_str) == Some("fill");
    let pnl = if live_fill {
        row.realized_pnl.unwrap_or(0.0)
    } else {
        row.realized_pnl.unwrap_or(entry.realized_before_entry) - entry.realized_before_entry
    };
    let pnl_pct = margin_return_percent(pnl, entry.allocated_margin);
    let exit_fee_usd = row.fee_usd.unwrap_or(0.0);
    let funding_cost = if row.execution_mode.as_deref() == Some("live") {
        -entry.funding_payment_usd
    } else {
        entry.funding_payment_usd
    };
    LiveTradeFinancials {
        exit_price: row.fill_px.unwrap_or(0.0),
        pnl,
        pnl_pct,
        exit_fee_usd,
        total_cost_usd: entry.entry_fee_usd + exit_fee_usd + funding_cost,
    }
}

pub(super) fn close_live_trade(
    run_id: &str,
    index: usize,
    entry: &OpenTrade,
    closes: &[&LedgerRow],
    exit_regime: &TradeRegime,
    pending_exit_reason: Option<&str>,
) -> PaperTradeRecord {
    let last = closes
        .last()
        .expect("live close requires at least one fill");
    let financials = live_trade_financials(entry, closes);
    PaperTradeRecord {
        trade_id: format!("{run_id}-{:04}", index + 1),
        timestamp_str: last.feed_ts.clone(),
        entry_timestamp_str: entry.timestamp.clone(),
        exit_timestamp_str: last.feed_ts.clone(),
        symbol: last.symbol.clone().unwrap_or_else(|| entry.symbol.clone()),
        direction: entry.direction.clone(),
        entry_price: entry.entry_price,
        exit_price: financials.exit_price,
        size_btc: entry.size,
        leverage: last.leverage.unwrap_or(entry.leverage),
        pnl_usd: financials.pnl,
        pnl_pct: financials.pnl_pct,
        gross_pnl_usd: financials.pnl + financials.total_cost_usd,
        entry_fee_usd: entry.entry_fee_usd,
        exit_fee_usd: financials.exit_fee_usd,
        funding_payment_usd: entry.funding_payment_usd,
        total_cost_usd: financials.total_cost_usd,
        entry_primary_regime: entry.entry_regime.primary.clone(),
        entry_regime_1m: entry.entry_regime.state_1m.clone(),
        entry_regime_5m: entry.entry_regime.state_5m.clone(),
        entry_context_15m: entry.entry_regime.context_15m.clone(),
        exit_primary_regime: exit_regime.primary.clone(),
        exit_regime_1m: exit_regime.state_1m.clone(),
        exit_regime_5m: exit_regime.state_5m.clone(),
        exit_context_15m: exit_regime.context_15m.clone(),
        exit_reason: pending_exit_reason
            .unwrap_or("exit_reason_not_recorded")
            .to_string(),
    }
}

fn live_trade_financials(entry: &OpenTrade, closes: &[&LedgerRow]) -> LiveTradeFinancials {
    let size: f64 = closes
        .iter()
        .filter_map(|row| row.fill_qty)
        .map(f64::abs)
        .sum();
    let exit_notional: f64 = closes
        .iter()
        .map(|row| row.fill_px.unwrap_or(0.0) * row.fill_qty.unwrap_or(0.0).abs())
        .sum();
    let pnl: f64 = closes.iter().filter_map(|row| row.realized_pnl).sum();
    let exit_fee_usd: f64 = closes.iter().filter_map(|row| row.fee_usd).sum();
    let funding_cost = -entry.funding_payment_usd;
    let total_cost_usd = entry.entry_fee_usd + exit_fee_usd + funding_cost;
    let pnl_pct = margin_return_percent(pnl, entry.allocated_margin);
    LiveTradeFinancials {
        exit_price: if size > 0.0 {
            exit_notional / size
        } else {
            0.0
        },
        pnl,
        pnl_pct,
        exit_fee_usd,
        total_cost_usd,
    }
}

fn margin_return_percent(pnl: f64, allocated_margin: f64) -> f64 {
    if allocated_margin.abs() > f64::EPSILON {
        pnl / allocated_margin * 100.0
    } else {
        0.0
    }
}
