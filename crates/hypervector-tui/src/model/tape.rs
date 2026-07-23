//! Decision tape rows from paper/live decisions.jsonl.

use serde::Deserialize;
use serde_json::Value;

/// One decision ledger row (flexible extras ignored for display).
#[derive(Debug, Clone, Default, Deserialize)]
pub struct DecisionRow {
    #[serde(default)]
    pub feed_ts: Option<Value>,
    #[serde(default)]
    pub ts: Option<Value>,
    #[serde(default)]
    pub execution_mode: Option<String>,
    #[serde(default)]
    pub action: Option<String>,
    #[serde(default)]
    pub side: Option<String>,
    #[serde(default)]
    pub symbol: Option<String>,
    #[serde(default)]
    pub submitted: Option<bool>,
    #[serde(default)]
    pub place_attempted: Option<bool>,
    #[serde(default)]
    pub qty: Option<f64>,
    #[serde(default)]
    pub mark_px: Option<f64>,
    #[serde(default)]
    pub fill_px: Option<f64>,
    #[serde(default)]
    pub fill_model_id: Option<String>,
    #[serde(default)]
    pub network: Option<String>,
    #[serde(default)]
    pub run_id: Option<String>,
    #[serde(default)]
    pub strategy_name: Option<String>,
    #[serde(default)]
    pub position_qty: Option<f64>,
    #[serde(default)]
    pub position_avg_px: Option<f64>,
    #[serde(default)]
    pub realized_pnl: Option<f64>,
    #[serde(default)]
    pub unrealized_pnl: Option<f64>,
    #[serde(default)]
    pub equity: Option<f64>,
    #[serde(default)]
    pub init_cash: Option<f64>,
}

impl DecisionRow {
    pub fn timestamp_display(&self) -> String {
        for key in [&self.feed_ts, &self.ts] {
            if let Some(v) = key {
                return match v {
                    Value::String(s) => s.clone(),
                    Value::Number(n) => n.to_string(),
                    other => other.to_string(),
                };
            }
        }
        "—".into()
    }

    pub fn mode_str(&self) -> &str {
        self.execution_mode.as_deref().unwrap_or("?")
    }

    pub fn action_str(&self) -> &str {
        self.action.as_deref().unwrap_or("—")
    }

    pub fn submitted_str(&self) -> &str {
        match self.submitted {
            Some(true) => "Y",
            Some(false) => "N",
            None => "—",
        }
    }
}

/// Aggregates over a tape slice for book chrome.
#[derive(Debug, Clone, Default)]
pub struct TapeAggregate {
    pub decision_count: usize,
    pub submitted_count: usize,
    pub place_attempted_count: usize,
    pub last_event_age_secs: Option<u64>,
    /// Per-bucket decision counts for sparkline (oldest → newest).
    pub buckets: Vec<u64>,
}

/// Pure aggregate helpers for tape density.
pub fn aggregate_tape(rows: &[DecisionRow], bucket_count: usize) -> TapeAggregate {
    let decision_count = rows.len();
    let submitted_count = rows.iter().filter(|r| r.submitted == Some(true)).count();
    let place_attempted_count = rows
        .iter()
        .filter(|r| r.place_attempted == Some(true))
        .count();

    // Simple equal-width buckets over row order (not wall-clock) for density.
    let mut buckets = vec![0u64; bucket_count.max(1)];
    if !rows.is_empty() {
        let n = bucket_count.max(1);
        for (i, _) in rows.iter().enumerate() {
            let idx = (i * n) / rows.len();
            buckets[idx.min(n - 1)] += 1;
        }
    }

    TapeAggregate {
        decision_count,
        submitted_count,
        place_attempted_count,
        last_event_age_secs: None, // filled by app if wall clock known
        buckets,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn aggregate_counts_submitted() {
        let rows = vec![
            DecisionRow {
                submitted: Some(true),
                place_attempted: Some(true),
                action: Some("buy".into()),
                ..Default::default()
            },
            DecisionRow {
                submitted: Some(false),
                place_attempted: Some(false),
                action: Some("hold".into()),
                ..Default::default()
            },
            DecisionRow {
                submitted: Some(true),
                place_attempted: Some(true),
                action: Some("sell".into()),
                ..Default::default()
            },
        ];
        let a = aggregate_tape(&rows, 4);
        assert_eq!(a.decision_count, 3);
        assert_eq!(a.submitted_count, 2);
        assert_eq!(a.place_attempted_count, 2);
        assert_eq!(a.buckets.iter().sum::<u64>(), 3);
    }
}
