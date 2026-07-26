//! Read-only projection of the authoritative Python paper/shadow ledger.

use serde::Deserialize;
use serde_json::Value;
use std::collections::HashMap;
use thiserror::Error;

use crate::backend_market::{BackendBookTelemetry, build_regime_snapshots, latest_book};
use crate::model::{ActivePosition, LivePaperStats, PaperTradeRecord, RegimeSnapshot};

pub use crate::backend_source::BackendTelemetrySource;

/// Health of the TUI's read-only connection to the backend ledger.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BackendConnectionState {
    Connected,
    Stale,
    Disconnected,
    Error,
}

/// Latest backend-confirmed state projected for display.
#[derive(Debug, Clone)]
pub struct BackendTelemetrySnapshot {
    pub connection: BackendConnectionState,
    pub status_message: String,
    pub run_id: Option<String>,
    pub export_id: Option<String>,
    pub data_root: Option<String>,
    pub strategy_name: Option<String>,
    pub execution_mode: Option<String>,
    pub metalabel_mode: Option<String>,
    pub metalabel_bundle_id: Option<String>,
    pub latest_metalabel_p: Option<f64>,
    pub latest_conviction_source: Option<String>,
    pub strategy_params: Value,
    pub exits: Value,
    pub risk: Value,
    pub execution_policy: Value,
    pub position_policy: Value,
    pub regime_policy: Value,
    pub costs: Value,
    pub runtime: Value,
    pub orderbook_archive: Value,
    pub latest_regime: Option<String>,
    pub latest_regime_feed_ts: Option<String>,
    pub latest_regime_reason: Option<String>,
    pub latest_regime_confidence: Option<f64>,
    pub latest_regime_strength_score: Option<f64>,
    pub latest_regime_score_source: Option<String>,
    pub entry_direction: Option<String>,
    pub entry_allowed: Option<bool>,
    pub pending_entry_direction: Option<String>,
    pub entry_retry_state: Option<String>,
    pub entry_cooldown_active: Option<bool>,
    pub funding_rate_hourly: Option<f64>,
    pub regime_history: Vec<String>,
    pub regime_snapshots: Vec<RegimeSnapshot>,
    pub book: Option<BackendBookTelemetry>,
    pub trades: Vec<PaperTradeRecord>,
    pub stats: LivePaperStats,
    pub active_position: ActivePosition,
    pub equity_history: Vec<f64>,
}

impl BackendTelemetrySnapshot {
    /// Construct an empty snapshot that explicitly reports disconnection.
    pub fn disconnected(message: impl Into<String>) -> Self {
        Self::empty(BackendConnectionState::Disconnected, message)
    }

    pub(crate) fn error(message: impl Into<String>) -> Self {
        Self::empty(BackendConnectionState::Error, message)
    }

    fn empty(state: BackendConnectionState, message: impl Into<String>) -> Self {
        Self {
            connection: state,
            status_message: message.into(),
            run_id: None,
            export_id: None,
            data_root: None,
            strategy_name: None,
            execution_mode: None,
            metalabel_mode: None,
            metalabel_bundle_id: None,
            latest_metalabel_p: None,
            latest_conviction_source: None,
            strategy_params: Value::Null,
            exits: Value::Null,
            risk: Value::Null,
            execution_policy: Value::Null,
            position_policy: Value::Null,
            regime_policy: Value::Null,
            costs: Value::Null,
            runtime: Value::Null,
            orderbook_archive: Value::Null,
            latest_regime: None,
            latest_regime_feed_ts: None,
            latest_regime_reason: None,
            latest_regime_confidence: None,
            latest_regime_strength_score: None,
            latest_regime_score_source: None,
            entry_direction: None,
            entry_allowed: None,
            pending_entry_direction: None,
            entry_retry_state: None,
            entry_cooldown_active: None,
            funding_rate_hourly: None,
            regime_history: Vec::new(),
            regime_snapshots: Vec::new(),
            book: None,
            trades: Vec::new(),
            stats: empty_stats(),
            active_position: ActivePosition::flat(),
            equity_history: Vec::new(),
        }
    }
}

/// A structural error that prevents trustworthy ledger projection.
#[derive(Debug, Error)]
pub enum BackendTelemetryError {
    #[error("invalid backend ledger JSON at line {line}: {source}")]
    InvalidJson {
        line: usize,
        #[source]
        source: serde_json::Error,
    },
}

#[derive(Debug, Clone, Deserialize)]
pub(crate) struct LedgerRow {
    #[serde(default)]
    pub(crate) feed_ts: String,
    #[serde(default)]
    pub(crate) action: String,
    #[serde(default)]
    skipped: bool,
    run_id: Option<String>,
    export_id: Option<String>,
    data_root: Option<String>,
    strategy_name: Option<String>,
    execution_mode: Option<String>,
    metalabel_mode: Option<String>,
    metalabel_bundle_id: Option<String>,
    conviction_source: Option<String>,
    metalabel_p: Option<f64>,
    symbol: Option<String>,
    pub(crate) fill_px: Option<f64>,
    fill_qty: Option<f64>,
    qty: Option<f64>,
    leverage: Option<f64>,
    position_qty: Option<f64>,
    position_avg_px: Option<f64>,
    equity: Option<f64>,
    init_cash: Option<f64>,
    realized_pnl: Option<f64>,
    unrealized_pnl: Option<f64>,
    fee_usd: Option<f64>,
    funding_payment_usd: Option<f64>,
    pub(crate) primary_regime: Option<String>,
    strategy_params: Option<Value>,
    exits: Option<Value>,
    risk: Option<Value>,
    execution: Option<Value>,
    position_policy: Option<Value>,
    regime_policy: Option<Value>,
    costs: Option<Value>,
    runtime: Option<Value>,
    orderbook_archive: Option<Value>,
    exit_reason: Option<String>,
    pub(crate) mark_px: Option<f64>,
    #[serde(flatten)]
    pub(crate) extra: HashMap<String, Value>,
}

#[derive(Debug, Clone)]
struct OpenTrade {
    timestamp: String,
    direction: String,
    symbol: String,
    entry_price: f64,
    size: f64,
    leverage: f64,
    allocated_margin: f64,
    realized_before_entry: f64,
    entry_fee_usd: f64,
    funding_payment_usd: f64,
    entry_regime: TradeRegime,
}

struct ActivePositionCycle<'a> {
    latest: &'a LedgerRow,
    entry: Option<&'a LedgerRow>,
    qty: f64,
    entry_fee_usd: f64,
    funding_payment_usd: f64,
}

#[derive(Debug, Clone)]
struct TradeRegime {
    primary: String,
    state_1m: String,
    state_5m: String,
    context_15m: String,
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

/// Parse JSONL and project only the most recent identified backend run.
pub fn parse_backend_telemetry(
    content: &str,
) -> Result<BackendTelemetrySnapshot, BackendTelemetryError> {
    let rows = parse_rows(content)?;
    let Some(run_id) = rows.iter().rev().find_map(|row| row.run_id.clone()) else {
        return Ok(BackendTelemetrySnapshot::disconnected(
            "ledger has no run identity",
        ));
    };
    let run_rows: Vec<&LedgerRow> = rows
        .iter()
        .filter(|row| row.run_id.as_deref() == Some(run_id.as_str()))
        .collect();
    Ok(build_snapshot(run_id, &run_rows))
}

fn parse_rows(content: &str) -> Result<Vec<LedgerRow>, BackendTelemetryError> {
    content
        .lines()
        .enumerate()
        .filter(|(_, line)| !line.trim().is_empty())
        .map(|(index, line)| {
            serde_json::from_str(line).map_err(|source| BackendTelemetryError::InvalidJson {
                line: index + 1,
                source,
            })
        })
        .collect()
}

fn build_snapshot(run_id: String, rows: &[&LedgerRow]) -> BackendTelemetrySnapshot {
    let identity = rows
        .iter()
        .rev()
        .find(|row| row.action == "session_start")
        .copied();
    let configured_leverage = identity
        .and_then(|row| row.strategy_params.as_ref())
        .and_then(|params| params.get("leverage"))
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let trades = build_trades(&run_id, rows, configured_leverage);
    let equity_history: Vec<f64> = rows.iter().filter_map(|row| row.equity).collect();
    let stats = build_stats(rows, &trades, &equity_history);
    let maker_fee_rate = identity
        .and_then(|row| row.costs.as_ref())
        .and_then(|costs| costs.get("maker_fee_rate"))
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let active_position = build_active_position(rows, configured_leverage, maker_fee_rate);
    let regime_snapshots = build_regime_snapshots(rows, configured_leverage);
    let book = latest_book(rows);
    let latest_regime_row = rows
        .iter()
        .rev()
        .find(|row| row.action == "regime_observation")
        .copied();
    let latest_execution_row = rows
        .iter()
        .rev()
        .find(|row| row.action == "entry_execution_observation")
        .copied();
    BackendTelemetrySnapshot {
        connection: BackendConnectionState::Connected,
        status_message: "backend ledger connected".to_string(),
        run_id: Some(run_id),
        export_id: latest_value(rows, |row| row.export_id.clone())
            .or_else(|| identity.and_then(|row| row.export_id.clone())),
        data_root: latest_value(rows, |row| row.data_root.clone()),
        strategy_name: latest_value(rows, |row| row.strategy_name.clone()),
        execution_mode: latest_value(rows, |row| row.execution_mode.clone()),
        metalabel_mode: latest_value(rows, |row| row.metalabel_mode.clone()),
        metalabel_bundle_id: latest_value(rows, |row| row.metalabel_bundle_id.clone()),
        latest_metalabel_p: rows.iter().rev().find_map(|row| row.metalabel_p),
        latest_conviction_source: latest_value(rows, |row| row.conviction_source.clone()),
        strategy_params: identity
            .and_then(|row| row.strategy_params.clone())
            .unwrap_or(Value::Null),
        exits: identity
            .and_then(|row| row.exits.clone())
            .unwrap_or(Value::Null),
        risk: identity
            .and_then(|row| row.risk.clone())
            .unwrap_or(Value::Null),
        execution_policy: identity
            .and_then(|row| row.execution.clone())
            .unwrap_or(Value::Null),
        position_policy: identity
            .and_then(|row| row.position_policy.clone())
            .unwrap_or(Value::Null),
        regime_policy: identity
            .and_then(|row| row.regime_policy.clone())
            .unwrap_or(Value::Null),
        costs: identity
            .and_then(|row| row.costs.clone())
            .unwrap_or(Value::Null),
        runtime: identity
            .and_then(|row| row.runtime.clone())
            .unwrap_or(Value::Null),
        orderbook_archive: identity
            .and_then(|row| row.orderbook_archive.clone())
            .unwrap_or(Value::Null),
        latest_regime: latest_regime_row.and_then(|row| row.primary_regime.clone()),
        latest_regime_feed_ts: latest_regime_row.map(|row| row.feed_ts.clone()),
        latest_regime_reason: latest_regime_row
            .and_then(|row| row.extra.get("regime_reason"))
            .and_then(Value::as_str)
            .map(str::to_string),
        latest_regime_confidence: latest_regime_row
            .and_then(|row| row.extra.get("confidence"))
            .and_then(Value::as_f64),
        latest_regime_strength_score: latest_regime_row
            .and_then(|row| row.extra.get("regime_strength_score"))
            .and_then(Value::as_f64)
            .or_else(|| {
                latest_regime_row
                    .and_then(|row| row.extra.get("confidence"))
                    .and_then(Value::as_f64)
            }),
        latest_regime_score_source: latest_regime_row
            .and_then(|row| row.extra.get("regime_score_source"))
            .and_then(Value::as_str)
            .map(str::to_string)
            .or_else(|| {
                latest_regime_row
                    .and_then(|row| row.extra.get("confidence"))
                    .and_then(Value::as_f64)
                    .map(|_| "legacy_confidence_alias".to_string())
            }),
        entry_direction: latest_regime_row
            .and_then(|row| row.extra.get("entry_direction"))
            .and_then(Value::as_str)
            .map(str::to_string),
        entry_allowed: latest_regime_row
            .and_then(|row| row.extra.get("entry_allowed"))
            .and_then(Value::as_bool),
        pending_entry_direction: latest_pending_entry_direction(rows),
        entry_retry_state: latest_execution_row
            .or(latest_regime_row)
            .and_then(|row| row.extra.get("entry_retry_state"))
            .and_then(Value::as_str)
            .map(str::to_string),
        entry_cooldown_active: latest_execution_row
            .or(latest_regime_row)
            .and_then(|row| row.extra.get("entry_cooldown_active"))
            .and_then(Value::as_bool),
        funding_rate_hourly: rows
            .iter()
            .rev()
            .find_map(|row| row.extra.get("funding_rate_hourly"))
            .and_then(Value::as_f64)
            .or_else(|| {
                identity
                    .and_then(|row| row.costs.as_ref())
                    .and_then(|costs| costs.get("funding_rate_hourly"))
                    .and_then(Value::as_f64)
            }),
        regime_history: rows
            .iter()
            .filter(|row| row.action == "regime_observation")
            .filter_map(|row| row.primary_regime.clone())
            .collect(),
        regime_snapshots,
        book,
        trades,
        stats,
        active_position,
        equity_history,
    }
}

fn latest_pending_entry_direction(rows: &[&LedgerRow]) -> Option<String> {
    let mut pending = None;
    for row in rows {
        match row.action.as_str() {
            "submit_entry" => {
                pending = row
                    .extra
                    .get("side")
                    .and_then(Value::as_str)
                    .and_then(entry_direction_from_side);
            }
            "cancel_entry" | "rejected_entry" => pending = None,
            "enter_long" | "enter_short" if is_filled_entry(row) => pending = None,
            _ => {}
        }
    }
    pending
}

fn entry_direction_from_side(side: &str) -> Option<String> {
    match side {
        "buy" => Some("long".to_string()),
        "sell" => Some("short".to_string()),
        _ => None,
    }
}

fn latest_value<T>(rows: &[&LedgerRow], get: impl Fn(&LedgerRow) -> Option<T>) -> Option<T> {
    rows.iter().rev().find_map(|row| get(row))
}

fn build_trades(
    run_id: &str,
    rows: &[&LedgerRow],
    configured_leverage: f64,
) -> Vec<PaperTradeRecord> {
    let mut trades = Vec::new();
    let mut open: Option<OpenTrade> = None;
    let mut latest_realized = 0.0;
    let mut latest_regime = TradeRegime::unknown();
    for row in rows {
        match row.action.as_str() {
            "regime_observation" => latest_regime = regime_from_row(row),
            "enter_long" | "enter_short" if is_filled_entry(row) => {
                if let Some(entry) = open.as_mut() {
                    merge_entry_fill(entry, row, configured_leverage);
                } else {
                    open = Some(open_trade_from_row(
                        row,
                        configured_leverage,
                        latest_realized,
                        latest_regime.clone(),
                    ));
                }
            }
            "funding" => {
                if let Some(entry) = open.as_mut() {
                    entry.funding_payment_usd += row.funding_payment_usd.unwrap_or(0.0);
                }
            }
            "close" => {
                if let Some(entry) = open.take() {
                    trades.push(close_trade(
                        run_id,
                        trades.len(),
                        &entry,
                        row,
                        &latest_regime,
                    ));
                }
            }
            _ => {}
        }
        if let Some(realized) = row.realized_pnl {
            latest_realized = realized;
        }
    }
    trades
}

fn is_filled_entry(row: &LedgerRow) -> bool {
    let quantity = row.fill_qty.or(row.qty).or(row.position_qty).unwrap_or(0.0);
    !row.skipped && quantity.abs() > f64::EPSILON
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

fn close_trade(
    run_id: &str,
    index: usize,
    entry: &OpenTrade,
    row: &LedgerRow,
    exit_regime: &TradeRegime,
) -> PaperTradeRecord {
    let pnl = row.realized_pnl.unwrap_or(entry.realized_before_entry) - entry.realized_before_entry;
    let pnl_pct = if entry.allocated_margin.abs() > f64::EPSILON {
        pnl / entry.allocated_margin * 100.0
    } else {
        0.0
    };
    let exit_fee_usd = row.fee_usd.unwrap_or(0.0);
    let total_cost_usd = entry.entry_fee_usd + exit_fee_usd + entry.funding_payment_usd;
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
        exit_price: row.fill_px.unwrap_or(0.0),
        size_btc: entry.size,
        leverage: row.leverage.unwrap_or(entry.leverage),
        pnl_usd: pnl,
        pnl_pct,
        gross_pnl_usd: pnl + total_cost_usd,
        entry_fee_usd: entry.entry_fee_usd,
        exit_fee_usd,
        funding_payment_usd: entry.funding_payment_usd,
        total_cost_usd,
        entry_primary_regime: entry.entry_regime.primary.clone(),
        entry_regime_1m: entry.entry_regime.state_1m.clone(),
        entry_regime_5m: entry.entry_regime.state_5m.clone(),
        entry_context_15m: entry.entry_regime.context_15m.clone(),
        exit_primary_regime: exit_regime.primary.clone(),
        exit_regime_1m: exit_regime.state_1m.clone(),
        exit_regime_5m: exit_regime.state_5m.clone(),
        exit_context_15m: exit_regime.context_15m.clone(),
        exit_reason: row
            .exit_reason
            .clone()
            .unwrap_or_else(|| "exit_reason_not_recorded".to_string()),
    }
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

fn build_stats(rows: &[&LedgerRow], trades: &[PaperTradeRecord], equity: &[f64]) -> LivePaperStats {
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
    let wins: Vec<f64> = trades
        .iter()
        .filter(|trade| trade.pnl_usd >= 0.0)
        .map(|trade| trade.pnl_usd)
        .collect();
    let losses: Vec<f64> = trades
        .iter()
        .filter(|trade| trade.pnl_usd < 0.0)
        .map(|trade| trade.pnl_usd)
        .collect();
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

fn build_active_position(
    rows: &[&LedgerRow],
    configured_leverage: f64,
    maker_fee_rate: f64,
) -> ActivePosition {
    let Some(cycle) = active_position_cycle(rows) else {
        return ActivePosition::flat();
    };
    let estimated_exit_price = cycle.latest.mark_px.unwrap_or_else(|| {
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
    let cycle_rows = &rows[cycle_start..=latest_index];
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
    })
}

fn empty_stats() -> LivePaperStats {
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
