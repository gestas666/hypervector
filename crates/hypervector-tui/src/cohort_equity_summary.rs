//! Closed-lifecycle equity summary derived from backend-authored performance.

/// Headline values for the closed-lifecycle equity instrument.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct ClosedEquitySummary {
    pub(crate) closed_equity: Option<f64>,
    pub(crate) net: f64,
    pub(crate) return_pct: Option<f64>,
}

impl ClosedEquitySummary {
    /// Reconcile current-profile net PnL with its matching run baseline.
    pub(crate) fn from_path(start: Option<f64>, net: f64) -> Self {
        let closed_equity = start.map(|value| value + net);
        Self {
            closed_equity,
            net,
            return_pct: start
                .filter(|value| value.abs() > f64::EPSILON)
                .map(|value| net / value * 100.0),
        }
    }
}

/// Calculate peak-to-trough drawdown from one closed-equity path.
pub(crate) fn closed_path_maximum_drawdown_pct(values: &[f64]) -> Option<f64> {
    let mut values = values.iter().copied().filter(|value| value.is_finite());
    let first = values.next()?;
    let mut peak = first;
    let mut maximum = 0.0_f64;
    for value in values {
        peak = peak.max(value);
        if peak.abs() > f64::EPSILON {
            maximum = maximum.max((peak - value) / peak.abs() * 100.0);
        }
    }
    Some(maximum)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn closed_drawdown_uses_only_the_closed_trade_path() {
        assert_eq!(
            closed_path_maximum_drawdown_pct(&[100.0, 100.05, 100.28]),
            Some(0.0),
        );
        let observed = closed_path_maximum_drawdown_pct(&[100.0, 100.90, 100.68]);
        assert!(observed.is_some_and(|value| (value - 0.218_037_66).abs() < 1e-8));
    }
}
