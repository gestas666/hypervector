//! Private portfolio statistics and active-position projection.

use crate::model::{ActivePosition, LivePaperStats, PaperTradeRecord};

use super::LedgerRow;
use super::backend_telemetry_trades::is_filled_entry;

struct ActivePositionCycle<'a> {
    latest: &'a LedgerRow,
    entry: Option<&'a LedgerRow>,
    qty: f64,
    entry_fee_usd: f64,
    funding_payment_usd: f64,
    liquidation_price: Option<f64>,
    mark_price: Option<f64>,
}

pub(super) fn build_stats(
    rows: &[&LedgerRow],
    trades: &[PaperTradeRecord],
    equity: &[f64],
) -> LivePaperStats {
    let initial = rows
        .iter()
        .find_map(|row| row.init_cash)
        .or_else(|| equity.first().copied())
        .unwrap_or(10_000.0);
    let current = equity.last().copied().unwrap_or(initial);
    let realized = rows
        .iter()
        .rev()
        .find_map(|row| row.realized_pnl)
        .unwrap_or(0.0);
    let unrealized = rows
        .iter()
        .rev()
        .find_map(|row| row.unrealized_pnl)
        .unwrap_or(0.0);
    let (wins, losses) = partition_trade_pnl(trades);
    let gross_win: f64 = wins.iter().sum();
    let gross_loss: f64 = losses.iter().map(|value| value.abs()).sum();
    LivePaperStats {
        initial_capital: initial,
        current_equity: current,
        realized_pnl: realized,
        unrealized_pnl: unrealized,
        total_trades: trades.len(),
        wins: wins.len(),
        losses: losses.len(),
        win_rate_pct: ratio_percent(wins.len(), trades.len()),
        profit_factor: if gross_loss > 0.0 {
            gross_win / gross_loss
        } else {
            0.0
        },
        max_drawdown_pct: max_drawdown_percent(equity),
        avg_win_usd: average(&wins),
        avg_loss_usd: average(&losses),
    }
}

fn partition_trade_pnl(trades: &[PaperTradeRecord]) -> (Vec<f64>, Vec<f64>) {
    let wins = trades
        .iter()
        .filter(|trade| trade.pnl_usd >= 0.0)
        .map(|trade| trade.pnl_usd)
        .collect();
    let losses = trades
        .iter()
        .filter(|trade| trade.pnl_usd < 0.0)
        .map(|trade| trade.pnl_usd)
        .collect();
    (wins, losses)
}

pub(super) fn build_active_position(
    rows: &[&LedgerRow],
    configured_leverage: f64,
    maker_fee_rate: f64,
) -> ActivePosition {
    let Some(cycle) = active_position_cycle(rows) else {
        return ActivePosition::flat();
    };
    let estimated_exit_price = cycle.mark_price.unwrap_or_else(|| {
        cycle
            .latest
            .position_avg_px
            .or_else(|| cycle.entry.and_then(|row| row.fill_px))
            .unwrap_or(0.0)
    });
    ActivePosition {
        entry_timestamp: cycle
            .entry
            .map(|row| row.feed_ts.clone())
            .unwrap_or_default(),
        symbol: cycle
            .entry
            .and_then(|row| row.symbol.clone())
            .unwrap_or_else(|| "UNKNOWN".to_string()),
        direction: if cycle.qty > 0.0 { "LONG" } else { "SHORT" }.to_string(),
        entry_price: cycle
            .latest
            .position_avg_px
            .or_else(|| cycle.entry.and_then(|row| row.fill_px))
            .unwrap_or(0.0),
        size_btc: cycle.qty.abs(),
        leverage: cycle
            .entry
            .and_then(|row| row.leverage)
            .unwrap_or(configured_leverage),
        entry_equity: cycle.entry.and_then(|row| row.equity).unwrap_or(0.0),
        peak_margin_pct: 0.0,
        entry_fee_usd: cycle.entry_fee_usd,
        funding_payment_usd: cycle.funding_payment_usd,
        estimated_exit_fee_usd: cycle.qty.abs() * estimated_exit_price * maker_fee_rate,
        liquidation_price: cycle.liquidation_price,
        mark_price: cycle.mark_price,
    }
}

fn active_position_cycle<'a>(rows: &[&'a LedgerRow]) -> Option<ActivePositionCycle<'a>> {
    let (latest_index, latest) = rows
        .iter()
        .enumerate()
        .rev()
        .find(|(_, row)| row.position_qty.is_some())
        .map(|(index, row)| (index, *row))?;
    let qty = latest.position_qty.unwrap_or(0.0);
    if qty.abs() <= f64::EPSILON {
        return None;
    }
    let cycle_start = rows[..=latest_index]
        .iter()
        .rposition(|row| {
            row.position_qty
                .is_some_and(|value| value.abs() <= f64::EPSILON)
        })
        .map_or(0, |index| index + 1);
    let cycle_rows = &rows[cycle_start..];
    let entries: Vec<&LedgerRow> = cycle_rows
        .iter()
        .filter(|row| matches!(row.action.as_str(), "enter_long" | "enter_short"))
        .filter(|row| is_filled_entry(row))
        .copied()
        .collect();
    Some(ActivePositionCycle {
        latest,
        entry: entries.first().copied(),
        qty,
        entry_fee_usd: entries.iter().filter_map(|row| row.fee_usd).sum(),
        funding_payment_usd: cycle_rows
            .iter()
            .filter(|row| row.action == "funding")
            .filter_map(|row| row.funding_payment_usd)
            .sum(),
        liquidation_price: cycle_rows
            .iter()
            .rev()
            .find_map(|row| row.liquidation_price)
            .filter(|price| *price > 0.0),
        mark_price: cycle_rows.iter().rev().find_map(|row| row.mark_px),
    })
}

pub(super) fn empty_stats() -> LivePaperStats {
    LivePaperStats {
        initial_capital: 10_000.0,
        current_equity: 10_000.0,
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
    }
}

fn ratio_percent(numerator: usize, denominator: usize) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        numerator as f64 / denominator as f64 * 100.0
    }
}

fn average(values: &[f64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

fn max_drawdown_percent(equity: &[f64]) -> f64 {
    let mut peak = 0.0_f64;
    let mut max_drawdown = 0.0_f64;
    for value in equity {
        peak = peak.max(*value);
        if peak > 0.0 {
            max_drawdown = max_drawdown.max((peak - value) / peak * 100.0);
        }
    }
    max_drawdown
}
