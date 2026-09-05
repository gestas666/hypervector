//! Validation model for assets retired from a staged growth roster.

use std::collections::BTreeSet;

use serde::Deserialize;

/// Reconciled venue state for one asset absent from the staged roster.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct GrowthPreflightRetiredAssetTelemetry {
    pub symbol: String,
    pub flat_no_orders: bool,
    pub ledger_reconciled: bool,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RetiredAsset {
    pub(crate) symbol: String,
    pub(crate) position_size_signed: f64,
    pub(crate) open_order_ids: Vec<u64>,
    pub(crate) ledger_position_size_signed: f64,
    pub(crate) ledger_owned_order_ids: Vec<u64>,
    pub(crate) ledger_reconciled: bool,
    pub(crate) flat_no_orders: bool,
}

pub(crate) fn valid_retired_asset(asset: &RetiredAsset) -> bool {
    let order_ids = asset
        .open_order_ids
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let ledger_ids = asset
        .ledger_owned_order_ids
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    !asset.symbol.trim().is_empty()
        && asset.position_size_signed.is_finite()
        && asset.ledger_position_size_signed.is_finite()
        && order_ids.len() == asset.open_order_ids.len()
        && ledger_ids.len() == asset.ledger_owned_order_ids.len()
        && order_ids.iter().all(|oid| *oid > 0)
        && ledger_ids.iter().all(|oid| *oid > 0)
        && (!asset.ledger_reconciled || order_ids == ledger_ids)
        && asset.flat_no_orders
            == (asset.position_size_signed == 0.0 && asset.open_order_ids.is_empty())
}

pub(crate) fn project_retired_asset(asset: RetiredAsset) -> GrowthPreflightRetiredAssetTelemetry {
    GrowthPreflightRetiredAssetTelemetry {
        symbol: asset.symbol,
        flat_no_orders: asset.flat_no_orders,
        ledger_reconciled: asset.ledger_reconciled,
    }
}
