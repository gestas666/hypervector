//! Small strict value projections shared by cohort trade reflections.

use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub(crate) struct RawExecutionLeg {
    pub price: f64,
    pub venue_timestamp_ms: u64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawRegimeDrift {
    pub signal_provider_changed: Option<bool>,
    pub canonical_regime_changed: Option<bool>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawMarkedEconomics {
    pub mark_price: f64,
    pub active_lifecycle_marked_net_pnl_usd: f64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawProtectiveStop {
    oid: u64,
    trigger_price: f64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawTargetOrder {
    oid: u64,
    limit_price: f64,
    directional_distance_bps: f64,
}

pub(crate) struct ProjectedTargetOrder {
    pub(crate) oid: u64,
    pub(crate) limit_price: f64,
    pub(crate) directional_distance_bps: f64,
}

pub(crate) fn project_protective_stop(
    raw: Option<RawProtectiveStop>,
) -> Result<(Option<u64>, Option<f64>), String> {
    let Some(value) = raw else {
        return Ok((None, None));
    };
    if value.oid == 0 || !value.trigger_price.is_finite() || value.trigger_price <= 0.0 {
        return Err("trade reflection protective stop is invalid".into());
    }
    Ok((Some(value.oid), Some(value.trigger_price)))
}

pub(crate) fn project_target_order(
    raw: Option<RawTargetOrder>,
) -> Result<Option<ProjectedTargetOrder>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    if value.oid == 0
        || !value.limit_price.is_finite()
        || value.limit_price <= 0.0
        || !value.directional_distance_bps.is_finite()
    {
        return Err("open-trade reflection target order is invalid".into());
    }
    Ok(Some(ProjectedTargetOrder {
        oid: value.oid,
        limit_price: value.limit_price,
        directional_distance_bps: value.directional_distance_bps,
    }))
}
