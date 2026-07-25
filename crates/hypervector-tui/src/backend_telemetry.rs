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
    pub costs: Value,
    pub latest_regime: Option<String>,
    pub entry_direction: Option<String>,
    pub entry_allowed: Option<bool>,
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
            costs: Value::Null,
            latest_regime: None,
            entry_direction: None,
            entry_allowed: None,
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
    pub(crate) primary_regime: Option<String>,
    strategy_params: Option<Value>,
    exits: Option<Value>,
    risk: Option<Value>,
    execution: Option<Value>,
    position_policy: Option<Value>,
    costs: Option<Value>,
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
        .find(|row| row.action == "session_start")
        .copied();
    let latest = rows.last().copied();
    let configured_leverage = identity
        .and_then(|row| row.strategy_params.as_ref())
        .and_then(|params| params.get("leverage"))
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let trades = build_trades(&run_id, rows, configured_leverage);
    let equity_history: Vec<f64> = rows.iter().filter_map(|row| row.equity).collect();
    let stats = build_stats(rows, &trades, &equity_history);
    let active_position = build_active_position(rows, latest, configured_leverage);
    let regime_snapshots = build_regime_snapshots(rows, configured_leverage);
    let book = latest_book(rows);
    let latest_regime_row = rows
        .iter()
        .rev()
        .find(|row| row.action == "regime_observation")
        .copied();
    BackendTelemetrySnapshot {
        connection: BackendConnectionState::Connected,
        status_message: "backend ledger connected".to_string(),
        run_id: Some(run_id),
        export_id: latest_value(rows, |row| row.export_id.clone())
            .or_else(|| identity.and_then(|row| row.export_id.clone())),
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
        costs: identity
            .and_then(|row| row.costs.clone())
            .unwrap_or(Value::Null),
        latest_regime: latest_regime_row.and_then(|row| row.primary_regime.clone()),
        entry_direction: latest_regime_row
            .and_then(|row| row.extra.get("entry_direction"))
            .and_then(Value::as_str)
            .map(str::to_string),
        entry_allowed: latest_regime_row
            .and_then(|row| row.extra.get("entry_allowed"))
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
    for row in rows {
        match row.action.as_str() {
            "enter_long" | "enter_short" if is_filled_entry(row) => {
                open = Some(open_trade_from_row(
                    row,
                    configured_leverage,
                    latest_realized,
                ));
            }
            "close" => {
                if let Some(entry) = open.take() {
                    trades.push(close_trade(run_id, trades.len(), &entry, row));
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
    }
}

fn close_trade(run_id: &str, index: usize, entry: &OpenTrade, row: &LedgerRow) -> PaperTradeRecord {
    let pnl = row.realized_pnl.unwrap_or(entry.realized_before_entry) - entry.realized_before_entry;
    let pnl_pct = if entry.allocated_margin.abs() > f64::EPSILON {
        pnl / entry.allocated_margin * 100.0
    } else {
        0.0
    };
    PaperTradeRecord {
        trade_id: format!("{run_id}-{:04}", index + 1),
        timestamp_str: if row.feed_ts.is_empty() {
            entry.timestamp.clone()
        } else {
            row.feed_ts.clone()
        },
        symbol: row.symbol.clone().unwrap_or_else(|| entry.symbol.clone()),
        direction: entry.direction.clone(),
        entry_price: entry.entry_price,
        exit_price: row.fill_px.unwrap_or(0.0),
        size_btc: entry.size,
        leverage: row.leverage.unwrap_or(entry.leverage),
        pnl_usd: pnl,
        pnl_pct,
        exit_reason: "backend_close".to_string(),
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
    latest: Option<&LedgerRow>,
    configured_leverage: f64,
) -> ActivePosition {
    let Some(latest) = latest else {
        return ActivePosition::flat();
    };
    let qty = latest.position_qty.unwrap_or(0.0);
    if qty.abs() <= f64::EPSILON {
        return ActivePosition::flat();
    }
    let entry = rows
        .iter()
        .rev()
        .find(|row| matches!(row.action.as_str(), "enter_long" | "enter_short"));
    ActivePosition {
        direction: if qty > 0.0 { "LONG" } else { "SHORT" }.to_string(),
        entry_price: latest
            .position_avg_px
            .or_else(|| entry.and_then(|row| row.fill_px))
            .unwrap_or(0.0),
        size_btc: qty.abs(),
        leverage: entry
            .and_then(|row| row.leverage)
            .unwrap_or(configured_leverage),
        entry_equity: entry.and_then(|row| row.equity).unwrap_or(0.0),
        peak_margin_pct: 0.0,
    }
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
