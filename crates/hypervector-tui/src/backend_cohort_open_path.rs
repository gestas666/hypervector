//! Strict projection of completed-candle path evidence for an open lifecycle.

use serde::Deserialize;

/// Causal post-entry excursion and marked giveback evidence.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortOpenPath {
    pub status: String,
    pub completed_bars: u64,
    pub first_timestamp_ms: Option<u64>,
    pub last_timestamp_ms: Option<u64>,
    pub highest_price: Option<f64>,
    pub lowest_price: Option<f64>,
    pub current_directional_return_bps: Option<f64>,
    pub maximum_favorable_excursion_bps: Option<f64>,
    pub maximum_adverse_excursion_bps: Option<f64>,
    pub peak_giveback_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawOpenPath {
    status: String,
    completed_bars: u64,
    first_timestamp_ms: Option<u64>,
    last_timestamp_ms: Option<u64>,
    highest_price: Option<f64>,
    lowest_price: Option<f64>,
    current_directional_return_bps: Option<f64>,
    maximum_favorable_excursion_bps: Option<f64>,
    maximum_adverse_excursion_bps: Option<f64>,
    peak_giveback_bps: Option<f64>,
}

pub(crate) fn project_open_path(raw: RawOpenPath) -> Result<CohortOpenPath, String> {
    validate_path(&raw)?;
    Ok(CohortOpenPath {
        status: raw.status,
        completed_bars: raw.completed_bars,
        first_timestamp_ms: raw.first_timestamp_ms,
        last_timestamp_ms: raw.last_timestamp_ms,
        highest_price: raw.highest_price,
        lowest_price: raw.lowest_price,
        current_directional_return_bps: raw.current_directional_return_bps,
        maximum_favorable_excursion_bps: raw.maximum_favorable_excursion_bps,
        maximum_adverse_excursion_bps: raw.maximum_adverse_excursion_bps,
        peak_giveback_bps: raw.peak_giveback_bps,
    })
}

fn validate_path(raw: &RawOpenPath) -> Result<(), String> {
    let values = [
        raw.highest_price,
        raw.lowest_price,
        raw.current_directional_return_bps,
        raw.maximum_favorable_excursion_bps,
        raw.maximum_adverse_excursion_bps,
        raw.peak_giveback_bps,
    ];
    if values.into_iter().flatten().any(|value| !value.is_finite()) {
        return Err("open path contains a non-finite value".into());
    }
    match raw.status.as_str() {
        "observed" if observed_path_is_valid(raw) => Ok(()),
        "unavailable" if unavailable_path_is_valid(raw) => Ok(()),
        _ => Err("open path identity is invalid".into()),
    }
}

fn observed_path_is_valid(raw: &RawOpenPath) -> bool {
    raw.completed_bars > 0
        && matches!((raw.first_timestamp_ms, raw.last_timestamp_ms), (Some(first), Some(last)) if first <= last)
        && matches!((raw.highest_price, raw.lowest_price), (Some(high), Some(low)) if high > 0.0 && low > 0.0 && high >= low)
        && raw.current_directional_return_bps.is_some()
        && nonnegative(raw.maximum_favorable_excursion_bps)
        && nonnegative(raw.maximum_adverse_excursion_bps)
        && nonnegative(raw.peak_giveback_bps)
}

fn unavailable_path_is_valid(raw: &RawOpenPath) -> bool {
    raw.completed_bars == 0
        && raw.first_timestamp_ms.is_none()
        && raw.last_timestamp_ms.is_none()
        && raw.highest_price.is_none()
        && raw.lowest_price.is_none()
        && raw.current_directional_return_bps.is_some()
        && raw.maximum_favorable_excursion_bps.is_none()
        && raw.maximum_adverse_excursion_bps.is_none()
        && raw.peak_giveback_bps.is_none()
}

fn nonnegative(value: Option<f64>) -> bool {
    value.is_some_and(|number| number >= 0.0)
}
