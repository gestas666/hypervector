//! Portfolio-level concentration of currently open provider hypotheses.

use std::collections::BTreeMap;

use crate::backend_cohort_open_trade_reflection::CohortOpenTradeReflection;

/// Largest same-provider, same-side cluster among current open lifecycles.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct CohortOpenCluster {
    pub(crate) open_lifecycles: usize,
    pub(crate) clustered_lifecycles: usize,
    pub(crate) strategy_id: String,
    pub(crate) side: String,
    pub(crate) symbols: Vec<String>,
}

impl CohortOpenCluster {
    /// Express the cluster as a percentage of all current open lifecycles.
    pub(crate) fn concentration_pct(&self) -> f64 {
        100.0 * self.clustered_lifecycles as f64 / self.open_lifecycles as f64
    }
}

/// Derive concentration without granting the result execution authority.
pub(crate) fn largest_open_cluster(
    trades: &[CohortOpenTradeReflection],
) -> Option<CohortOpenCluster> {
    if trades.is_empty() {
        return None;
    }
    let mut grouped = BTreeMap::<(String, String), Vec<String>>::new();
    for trade in trades {
        grouped
            .entry((trade.strategy_id.clone(), trade.side.to_ascii_lowercase()))
            .or_default()
            .push(trade.symbol.clone());
    }
    let ((strategy_id, side), mut symbols) =
        grouped
            .into_iter()
            .max_by(|(left_key, left), (right_key, right)| {
                left.len()
                    .cmp(&right.len())
                    .then_with(|| right_key.cmp(left_key))
            })?;
    symbols.sort();
    Some(CohortOpenCluster {
        open_lifecycles: trades.len(),
        clustered_lifecycles: symbols.len(),
        strategy_id,
        side,
        symbols,
    })
}

/// Format one compact, explicitly descriptive concentration label.
pub(crate) fn open_cluster_label(cluster: &CohortOpenCluster, provider_alias: &str) -> String {
    format!(
        "CLUSTER {}/{} {:.0}% {} // {provider_alias}",
        cluster.clustered_lifecycles,
        cluster.open_lifecycles,
        cluster.concentration_pct(),
        cluster.side.to_ascii_uppercase(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn open_trade(symbol: &str, strategy_id: &str, side: &str) -> CohortOpenTradeReflection {
        CohortOpenTradeReflection {
            symbol: symbol.into(),
            strategy_id: strategy_id.into(),
            side: side.into(),
            ..CohortOpenTradeReflection::default()
        }
    }

    #[test]
    fn largest_cluster_exposes_one_shared_four_asset_short_hypothesis() {
        let trades = [
            open_trade("BTC", "hype_breakout_onset_bidirectional_v1", "short"),
            open_trade("ETH", "hype_breakout_onset_bidirectional_v1", "short"),
            open_trade("SOL", "hype_breakout_onset_bidirectional_v1", "short"),
            open_trade("HYPE", "hype_breakout_onset_bidirectional_v1", "short"),
        ];

        let cluster = largest_open_cluster(&trades).expect("cluster");

        assert_eq!(cluster.open_lifecycles, 4);
        assert_eq!(cluster.clustered_lifecycles, 4);
        assert_eq!(cluster.strategy_id, "hype_breakout_onset_bidirectional_v1");
        assert_eq!(cluster.side, "short");
        assert_eq!(cluster.symbols, vec!["BTC", "ETH", "HYPE", "SOL"]);
        assert_eq!(cluster.concentration_pct(), 100.0);
    }

    #[test]
    fn largest_cluster_remains_descriptive_for_mixed_open_hypotheses() {
        let trades = [
            open_trade("BTC", "provider_a", "long"),
            open_trade("ETH", "provider_a", "long"),
            open_trade("SOL", "provider_b", "short"),
        ];

        let cluster = largest_open_cluster(&trades).expect("cluster");

        assert_eq!(cluster.open_lifecycles, 3);
        assert_eq!(cluster.clustered_lifecycles, 2);
        assert_eq!(cluster.strategy_id, "provider_a");
        assert_eq!(cluster.side, "long");
        assert!((cluster.concentration_pct() - 66.666_666_666_7).abs() < 1e-9);
    }

    #[test]
    fn flat_portfolio_has_no_open_cluster() {
        assert_eq!(largest_open_cluster(&[]), None);
    }

    #[test]
    fn cluster_label_is_compact_and_operator_legible() {
        let cluster = CohortOpenCluster {
            open_lifecycles: 4,
            clustered_lifecycles: 4,
            strategy_id: "hype_breakout_onset_bidirectional_v1".into(),
            side: "short".into(),
            symbols: vec!["BTC".into(), "ETH".into(), "HYPE".into(), "SOL".into()],
        };

        assert_eq!(
            open_cluster_label(&cluster, "HT-Breakout"),
            "CLUSTER 4/4 100% SHORT // HT-Breakout"
        );
    }
}
