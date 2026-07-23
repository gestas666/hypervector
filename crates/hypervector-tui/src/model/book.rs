//! Live book snapshot from the latest paper/shadow decision row.
//!
//! Source of truth: decisions.jsonl fields written by the paper/shadow session daemon
//! (`position_qty`, `realized_pnl`, `unrealized_pnl`, `equity`, strategy).

use super::DecisionRow;

/// Current paper/shadow book as projected from the ledger tail.
#[derive(Debug, Clone, Default)]
pub struct BookSnapshot {
    pub has_book: bool,
    pub flat: bool,
    pub strategy_name: String,
    pub symbol: String,
    pub timeframe: String,
    pub execution_mode: String,
    pub position_qty: f64,
    pub position_avg_px: f64,
    pub mark_px: f64,
    pub realized_pnl: f64,
    pub unrealized_pnl: f64,
    pub equity: f64,
    pub init_cash: f64,
    pub total_pnl: f64,
    pub side_label: String,
    /// Equity path oldest→newest for sparkline (raw then scaled by UI).
    pub equity_series: Vec<f64>,
    pub equity_spark: Vec<u64>,
}

impl BookSnapshot {
    /// Build from decision rows (file order oldest→newest).
    pub fn from_decisions(rows: &[DecisionRow]) -> Self {
        let mut equity_series: Vec<f64> = Vec::new();
        for r in rows {
            if let Some(e) = r.equity {
                equity_series.push(e);
            }
        }

        // Prefer last row that carries book fields (skip pure session_start if empty).
        let mut chosen: Option<&DecisionRow> = None;
        for r in rows.iter().rev() {
            if r.position_qty.is_some()
                || r.equity.is_some()
                || r.realized_pnl.is_some()
                || r.unrealized_pnl.is_some()
            {
                chosen = Some(r);
                break;
            }
        }
        let Some(r) = chosen else {
            return Self {
                has_book: false,
                flat: true,
                side_label: "FLAT".into(),
                equity_spark: scale_u64(&equity_series),
                equity_series,
                ..Default::default()
            };
        };

        let qty = r.position_qty.unwrap_or(0.0);
        let avg = r.position_avg_px.unwrap_or(0.0);
        let mark = r.mark_px.unwrap_or(0.0);
        let realized = r.realized_pnl.unwrap_or(0.0);
        let mut unrealized = r.unrealized_pnl.unwrap_or(0.0);
        if r.unrealized_pnl.is_none() && qty != 0.0 && mark != 0.0 && avg != 0.0 {
            unrealized = qty * (mark - avg);
        }
        let init_cash = r.init_cash.unwrap_or(10_000.0);
        let equity = r
            .equity
            .unwrap_or_else(|| init_cash + realized + unrealized);
        let side_label = if qty > 1e-12 {
            "LONG".into()
        } else if qty < -1e-12 {
            "SHORT".into()
        } else {
            "FLAT".into()
        };

        Self {
            has_book: true,
            flat: qty.abs() <= 1e-12,
            strategy_name: r
                .strategy_name
                .clone()
                .unwrap_or_else(|| "—".into()),
            symbol: r.symbol.clone().unwrap_or_else(|| "—".into()),
            timeframe: String::new(),
            execution_mode: r
                .execution_mode
                .clone()
                .unwrap_or_else(|| "shadow".into()),
            position_qty: qty,
            position_avg_px: avg,
            mark_px: mark,
            realized_pnl: realized,
            unrealized_pnl: unrealized,
            equity,
            init_cash,
            total_pnl: equity - init_cash,
            side_label,
            equity_spark: scale_u64(&equity_series),
            equity_series,
        }
    }
}

fn scale_u64(raw: &[f64]) -> Vec<u64> {
    if raw.is_empty() {
        return Vec::new();
    }
    let min = raw.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = raw.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    if !min.is_finite() || !max.is_finite() {
        return Vec::new();
    }
    if (max - min).abs() < 1e-12 {
        return raw.iter().map(|_| 50u64).collect();
    }
    raw.iter()
        .map(|v| {
            let t = ((v - min) / (max - min)).clamp(0.0, 1.0);
            (t * 100.0).round() as u64
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn book_from_positioned_rows() {
        let rows = vec![
            DecisionRow {
                strategy_name: Some("crown_stack_short".into()),
                symbol: Some("BTC".into()),
                execution_mode: Some("shadow".into()),
                position_qty: Some(0.0),
                equity: Some(10_000.0),
                realized_pnl: Some(0.0),
                unrealized_pnl: Some(0.0),
                init_cash: Some(10_000.0),
                mark_px: Some(65000.0),
                ..Default::default()
            },
            DecisionRow {
                strategy_name: Some("crown_stack_short".into()),
                symbol: Some("BTC".into()),
                execution_mode: Some("shadow".into()),
                position_qty: Some(-0.05),
                position_avg_px: Some(65000.0),
                mark_px: Some(64000.0),
                realized_pnl: Some(-2.0),
                unrealized_pnl: Some(50.0),
                equity: Some(10_048.0),
                init_cash: Some(10_000.0),
                ..Default::default()
            },
        ];
        let b = BookSnapshot::from_decisions(&rows);
        assert!(b.has_book);
        assert_eq!(b.side_label, "SHORT");
        assert!((b.position_qty - -0.05).abs() < 1e-9);
        assert!((b.equity - 10_048.0).abs() < 1e-9);
        assert_eq!(b.strategy_name, "crown_stack_short");
        assert_eq!(b.equity_spark.len(), 2);
    }
}
