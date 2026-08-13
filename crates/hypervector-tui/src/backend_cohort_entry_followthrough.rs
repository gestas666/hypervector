//! Strict projection of report-only entry follow-through candle paths.

use serde::Deserialize;
use std::collections::BTreeMap;

/// One partial or resolved path measured from an authoritative entry fill.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortTradeEntryFollowthroughPath {
    pub status: String,
    pub bars_observed: u16,
    pub bars_required: u16,
    pub completion_pct: f64,
    pub directional_close_return_bps: Option<f64>,
    pub favorable_excursion_bps: Option<f64>,
    pub adverse_excursion_bps: Option<f64>,
    pub protective_stop_price_crossed: Option<bool>,
    pub first_stop_price_cross_timestamp_ms: Option<u64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawEntryFollowthroughPath {
    status: String,
    bars_observed: u16,
    bars_required: u16,
    completion_pct: f64,
    directional_close_return_bps: Option<f64>,
    favorable_excursion_bps: Option<f64>,
    adverse_excursion_bps: Option<f64>,
    protective_stop_price_crossed: Option<bool>,
    first_stop_price_cross_timestamp_ms: Option<u64>,
}

pub(crate) fn project_entry_followthrough_paths(
    raw: BTreeMap<String, RawEntryFollowthroughPath>,
) -> Result<BTreeMap<u16, CohortTradeEntryFollowthroughPath>, String> {
    raw.into_iter()
        .map(|(horizon, path)| project_path(&horizon, path))
        .collect()
}

fn project_path(
    horizon: &str,
    raw: RawEntryFollowthroughPath,
) -> Result<(u16, CohortTradeEntryFollowthroughPath), String> {
    let parsed = horizon
        .parse::<u16>()
        .map_err(|_| "entry follow-through horizon must be an integer")?;
    if parsed == 0 || parsed != raw.bars_required {
        return Err("entry follow-through horizon disagrees with required bars".into());
    }
    if !matches!(
        raw.status.as_str(),
        "resolved" | "censored" | "missing_data"
    ) {
        return Err("entry follow-through status is unsupported".into());
    }
    if raw.bars_observed > raw.bars_required
        || (raw.status == "resolved" && raw.bars_observed != raw.bars_required)
    {
        return Err("entry follow-through bar coverage is inconsistent".into());
    }
    let expected_pct = f64::from(raw.bars_observed) / f64::from(raw.bars_required) * 100.0;
    if !raw.completion_pct.is_finite() || (raw.completion_pct - expected_pct).abs() > 1e-6 {
        return Err("entry follow-through completion is inconsistent".into());
    }
    if raw.protective_stop_price_crossed == Some(true)
        && raw.first_stop_price_cross_timestamp_ms.is_none()
    {
        return Err("entry follow-through stop-price cross lacks its first timestamp".into());
    }
    if raw.protective_stop_price_crossed != Some(true)
        && raw.first_stop_price_cross_timestamp_ms.is_some()
    {
        return Err("entry follow-through stop-price timestamp lacks a cross".into());
    }
    Ok((
        parsed,
        CohortTradeEntryFollowthroughPath {
            status: raw.status,
            bars_observed: raw.bars_observed,
            bars_required: raw.bars_required,
            completion_pct: raw.completion_pct,
            directional_close_return_bps: raw.directional_close_return_bps,
            favorable_excursion_bps: raw.favorable_excursion_bps,
            adverse_excursion_bps: raw.adverse_excursion_bps,
            protective_stop_price_crossed: raw.protective_stop_price_crossed,
            first_stop_price_cross_timestamp_ms: raw.first_stop_price_cross_timestamp_ms,
        },
    ))
}
