//! Ledger-derived chart series for the Shadow Ops Floor.
//!
//! Pure functions over decision rows — no second strategy brain.
//! Derived equity is a shadow mark-to-market sketch, not venue accounting.

use super::DecisionRow;

/// Action mix counters for KPI chrome.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ActionMix {
    pub buy: usize,
    pub sell: usize,
    pub hold: usize,
    pub other: usize,
}

/// Chartable series + KPI helpers from the decision tape.
#[derive(Debug, Clone, Default)]
pub struct SeriesSnapshot {
    /// Mark prices oldest → newest (missing marks skipped).
    pub mark_px: Vec<u64>,
    /// Fill prices oldest → newest (missing fills skipped).
    pub fill_px: Vec<u64>,
    /// Decision activity buckets oldest → newest.
    pub activity: Vec<u64>,
    /// Derived equity path (scaled to u64 for sparklines), oldest → newest.
    pub equity: Vec<u64>,
    /// Last raw derived equity (USD units), if any fills/marks existed.
    pub last_equity: Option<f64>,
    /// Last mark price seen.
    pub last_mark: Option<f64>,
    /// Last fill price seen.
    pub last_fill: Option<f64>,
    pub action_mix: ActionMix,
    /// True when at least one price point exists for charting.
    pub has_price: bool,
    /// True when derived equity series is non-empty.
    pub has_equity: bool,
}

impl SeriesSnapshot {
    pub fn from_decisions(rows: &[DecisionRow], activity_buckets: usize) -> Self {
        let mut mark_raw: Vec<f64> = Vec::new();
        let mut fill_raw: Vec<f64> = Vec::new();
        let mut equity_raw: Vec<f64> = Vec::new();
        let mut mix = ActionMix::default();

        // Shadow mark-to-market sketch.
        let mut cash = 10_000.0_f64;
        let mut position = 0.0_f64;
        let mut last_mark = None;
        let mut last_fill = None;

        for r in rows {
            match r.action_str().to_ascii_lowercase().as_str() {
                "buy" => mix.buy += 1,
                "sell" => mix.sell += 1,
                "hold" => mix.hold += 1,
                _ => mix.other += 1,
            }

            if let Some(m) = r.mark_px {
                mark_raw.push(m);
                last_mark = Some(m);
            }
            if let Some(f) = r.fill_px {
                fill_raw.push(f);
                last_fill = Some(f);
            }

            let px = r.fill_px.or(r.mark_px);
            let qty = r.qty.unwrap_or(0.0);
            let act = r.action_str().to_ascii_lowercase();
            if let Some(p) = px {
                if qty > 0.0 {
                    match act.as_str() {
                        "buy" => {
                            cash -= p * qty;
                            position += qty;
                        }
                        "sell" => {
                            cash += p * qty;
                            position -= qty;
                        }
                        _ => {}
                    }
                }
                let mark = r.mark_px.or(Some(p)).unwrap_or(p);
                let eq = cash + position * mark;
                equity_raw.push(eq);
            } else if let Some(m) = last_mark {
                let eq = cash + position * m;
                equity_raw.push(eq);
            }
        }

        let activity = activity_buckets_from_len(rows.len(), activity_buckets.max(1));
        let mark_px = scale_series_u64(&mark_raw);
        let fill_px = scale_series_u64(&fill_raw);
        let equity = scale_series_u64(&equity_raw);

        SeriesSnapshot {
            has_price: !mark_px.is_empty() || !fill_px.is_empty(),
            has_equity: !equity.is_empty(),
            last_equity: equity_raw.last().copied(),
            last_mark,
            last_fill,
            mark_px,
            fill_px,
            activity,
            equity,
            action_mix: mix,
        }
    }
}

fn activity_buckets_from_len(n: usize, bucket_count: usize) -> Vec<u64> {
    let mut buckets = vec![0u64; bucket_count];
    if n == 0 {
        return buckets;
    }
    for i in 0..n {
        let idx = (i * bucket_count) / n;
        buckets[idx.min(bucket_count - 1)] += 1;
    }
    buckets
}

/// Scale f64 series to u64 sparkline domain while preserving shape.
fn scale_series_u64(raw: &[f64]) -> Vec<u64> {
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

    fn row(action: &str, mark: f64, fill: f64, qty: f64) -> DecisionRow {
        DecisionRow {
            action: Some(action.into()),
            mark_px: Some(mark),
            fill_px: Some(fill),
            qty: Some(qty),
            submitted: Some(false),
            execution_mode: Some("shadow".into()),
            ..Default::default()
        }
    }

    #[test]
    fn series_builds_price_activity_and_mix() {
        let rows = vec![
            row("hold", 100.0, 100.0, 0.0),
            row("buy", 101.0, 101.5, 0.01),
            row("sell", 102.0, 101.8, 0.01),
            row("buy", 103.0, 103.1, 0.02),
        ];
        let s = SeriesSnapshot::from_decisions(&rows, 8);
        assert!(s.has_price);
        assert_eq!(s.mark_px.len(), 4);
        assert_eq!(s.action_mix.buy, 2);
        assert_eq!(s.action_mix.sell, 1);
        assert_eq!(s.action_mix.hold, 1);
        assert_eq!(s.activity.iter().sum::<u64>(), 4);
        assert!(s.has_equity);
        assert!(s.last_mark.is_some());
    }

    #[test]
    fn empty_tape_series() {
        let s = SeriesSnapshot::from_decisions(&[], 8);
        assert!(!s.has_price);
        assert!(!s.has_equity);
        assert_eq!(s.activity.iter().sum::<u64>(), 0);
    }
}
