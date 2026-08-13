//! Staged, restart-only configuration editor state for the cohort cockpit.

use crate::backend_cohort::BackendCohortTelemetry;
use crate::cohort_operator::{
    CohortAssetStageRequest, CohortProfileStageRequest, CohortProviderStageRequest,
};

pub(crate) const CONFIG_ROW_COUNT: usize = 11;

#[derive(Debug, Clone)]
pub(crate) struct CohortConfigEditor {
    pub maximum_positions: usize,
    pub poll_seconds: f64,
    pub assets: Vec<CohortAssetStageRequest>,
    pub providers: Vec<CohortProviderStageRequest>,
    pub dirty: bool,
}

impl CohortConfigEditor {
    pub(crate) fn from_backend(cohort: &BackendCohortTelemetry) -> Option<Self> {
        let runtime = cohort.runtime.as_ref()?;
        if cohort.asset_configs.is_empty() || cohort.providers.is_empty() {
            return None;
        }
        Some(Self {
            maximum_positions: cohort.maximum_concurrent_positions,
            poll_seconds: runtime.poll_seconds,
            assets: cohort
                .asset_configs
                .iter()
                .map(|asset| CohortAssetStageRequest {
                    symbol: asset.symbol.clone(),
                    leverage: asset.leverage,
                    margin_fraction: asset.margin_fraction,
                    max_notional_usd: asset.max_notional_usd,
                    stop_bps: asset.stop_bps,
                    maximum_hold_seconds: asset.maximum_hold_seconds,
                })
                .collect(),
            providers: cohort
                .providers
                .iter()
                .map(|provider| CohortProviderStageRequest {
                    strategy_id: provider.strategy_id.clone(),
                    execution_symbols: provider.execution_symbols.clone().unwrap_or_default(),
                })
                .collect(),
            dirty: false,
        })
    }

    pub(crate) fn adjust(&mut self, row: usize, asset: usize, delta: f64) {
        let Some(envelope) = self.assets.get_mut(asset) else {
            return;
        };
        match row {
            0 => return,
            1 => self.poll_seconds = (self.poll_seconds + delta).clamp(1.0, 60.0),
            2 => {
                let venue_max = envelope_max_leverage(&envelope.symbol);
                envelope.leverage = (envelope.leverage + delta).clamp(1.0, venue_max);
            }
            3 => {
                envelope.margin_fraction =
                    (envelope.margin_fraction + delta * 0.01).clamp(0.01, 1.0);
            }
            4 => {
                envelope.max_notional_usd = (envelope.max_notional_usd + delta * 5.0).max(5.0);
            }
            5 => envelope.stop_bps = (envelope.stop_bps + delta * 10.0).max(10.0),
            6 => {
                envelope.maximum_hold_seconds =
                    (envelope.maximum_hold_seconds as f64 + delta * 3_600.0).max(3_600.0) as u64;
            }
            _ => return,
        }
        self.dirty = true;
    }

    pub(crate) fn toggle_provider_symbol(&mut self, provider: usize, symbol: &str) {
        let Some(scope) = self.providers.get_mut(provider) else {
            return;
        };
        if let Some(index) = scope
            .execution_symbols
            .iter()
            .position(|value| value == symbol)
        {
            scope.execution_symbols.remove(index);
        } else {
            scope.execution_symbols.push(symbol.into());
            scope.execution_symbols.sort();
        }
        self.dirty = true;
    }

    pub(crate) fn request(&self) -> CohortProfileStageRequest {
        CohortProfileStageRequest {
            maximum_positions: self.maximum_positions,
            poll_seconds: self.poll_seconds,
            assets: self.assets.clone(),
            providers: self.providers.clone(),
        }
    }
}

fn envelope_max_leverage(symbol: &str) -> f64 {
    match symbol {
        "BTC" => 40.0,
        "ETH" => 25.0,
        "SOL" => 20.0,
        "HYPE" => 10.0,
        _ => 10.0,
    }
}
