//! Strict projection of causal path evidence after a soft maximum-hold boundary.

use serde::Deserialize;

/// Incremental completed-candle path after the configured soft deadline.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortOpenExtensionPath {
    pub status: String,
    pub boundary_timestamp_ms: u64,
    pub baseline_timestamp_ms: Option<u64>,
    pub baseline_price: Option<f64>,
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
pub(crate) struct RawOpenExtensionPath {
    status: String,
    boundary_timestamp_ms: u64,
    baseline_timestamp_ms: Option<u64>,
    baseline_price: Option<f64>,
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

pub(crate) fn project_open_extension_path(
    raw: RawOpenExtensionPath,
) -> Result<CohortOpenExtensionPath, String> {
    validate_path(&raw)?;
    Ok(CohortOpenExtensionPath {
        status: raw.status,
        boundary_timestamp_ms: raw.boundary_timestamp_ms,
        baseline_timestamp_ms: raw.baseline_timestamp_ms,
        baseline_price: raw.baseline_price,
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

fn validate_path(raw: &RawOpenExtensionPath) -> Result<(), String> {
    if raw.boundary_timestamp_ms == 0 || contains_nonfinite(raw) {
        return Err("post-soft path contains an invalid boundary or value".into());
    }
    let valid = match raw.status.as_str() {
        "observed" => observed_is_valid(raw),
        "awaiting_completed_bar" => awaiting_is_valid(raw),
        "pending_soft_deadline" | "unavailable_boundary_close" => unavailable_is_valid(raw),
        _ => false,
    };
    if !valid {
        return Err("post-soft path identity is invalid".into());
    }
    Ok(())
}

fn contains_nonfinite(raw: &RawOpenExtensionPath) -> bool {
    [
        raw.baseline_price,
        raw.highest_price,
        raw.lowest_price,
        raw.current_directional_return_bps,
        raw.maximum_favorable_excursion_bps,
        raw.maximum_adverse_excursion_bps,
        raw.peak_giveback_bps,
    ]
    .into_iter()
    .flatten()
    .any(|value| !value.is_finite())
}

fn observed_is_valid(raw: &RawOpenExtensionPath) -> bool {
    baseline_is_valid(raw)
        && raw.completed_bars > 0
        && matches!((raw.first_timestamp_ms, raw.last_timestamp_ms), (Some(first), Some(last)) if first >= raw.boundary_timestamp_ms && first <= last)
        && matches!((raw.highest_price, raw.lowest_price), (Some(high), Some(low)) if high > 0.0 && low > 0.0 && high >= low)
        && raw.current_directional_return_bps.is_some()
        && nonnegative(raw.maximum_favorable_excursion_bps)
        && nonnegative(raw.maximum_adverse_excursion_bps)
        && nonnegative(raw.peak_giveback_bps)
}

fn awaiting_is_valid(raw: &RawOpenExtensionPath) -> bool {
    baseline_is_valid(raw)
        && raw.completed_bars == 0
        && excursion_fields_absent(raw)
        && raw.current_directional_return_bps.is_some()
}

fn unavailable_is_valid(raw: &RawOpenExtensionPath) -> bool {
    raw.baseline_timestamp_ms.is_none()
        && raw.baseline_price.is_none()
        && raw.completed_bars == 0
        && excursion_fields_absent(raw)
        && raw.current_directional_return_bps.is_none()
}

fn baseline_is_valid(raw: &RawOpenExtensionPath) -> bool {
    matches!(raw.baseline_timestamp_ms, Some(timestamp) if timestamp < raw.boundary_timestamp_ms)
        && raw.baseline_price.is_some_and(|price| price > 0.0)
}

fn excursion_fields_absent(raw: &RawOpenExtensionPath) -> bool {
    raw.first_timestamp_ms.is_none()
        && raw.last_timestamp_ms.is_none()
        && raw.highest_price.is_none()
        && raw.lowest_price.is_none()
        && raw.maximum_favorable_excursion_bps.is_none()
        && raw.maximum_adverse_excursion_bps.is_none()
        && raw.peak_giveback_bps.is_none()
}

fn nonnegative(value: Option<f64>) -> bool {
    value.is_some_and(|number| number >= 0.0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn raw(value: serde_json::Value) -> RawOpenExtensionPath {
        serde_json::from_value(value).expect("raw post-soft path")
    }

    #[test]
    fn accepts_causal_awaiting_completed_bar_shape() {
        let projected = project_open_extension_path(raw(json!({
            "status":"awaiting_completed_bar",
            "boundary_timestamp_ms":120000,
            "baseline_timestamp_ms":60000,
            "baseline_price":100.0,
            "completed_bars":0,
            "first_timestamp_ms":null,
            "last_timestamp_ms":null,
            "highest_price":null,
            "lowest_price":null,
            "current_directional_return_bps":2.0,
            "maximum_favorable_excursion_bps":null,
            "maximum_adverse_excursion_bps":null,
            "peak_giveback_bps":null
        })))
        .expect("valid awaiting path");

        assert_eq!(projected.status, "awaiting_completed_bar");
        assert_eq!(projected.current_directional_return_bps, Some(2.0));
    }

    #[test]
    fn accepts_completed_bar_opening_at_aligned_soft_boundary() {
        let projected = project_open_extension_path(raw(json!({
            "status":"observed",
            "boundary_timestamp_ms":120000,
            "baseline_timestamp_ms":60000,
            "baseline_price":100.0,
            "completed_bars":1,
            "first_timestamp_ms":120000,
            "last_timestamp_ms":120000,
            "highest_price":102.0,
            "lowest_price":99.0,
            "current_directional_return_bps":100.0,
            "maximum_favorable_excursion_bps":200.0,
            "maximum_adverse_excursion_bps":100.0,
            "peak_giveback_bps":100.0
        })))
        .expect("aligned boundary candle is the first causal completed bar");

        assert_eq!(projected.first_timestamp_ms, Some(120000));
    }

    #[test]
    fn rejects_success_shaped_pending_path() {
        let result = project_open_extension_path(raw(json!({
            "status":"pending_soft_deadline",
            "boundary_timestamp_ms":120000,
            "baseline_timestamp_ms":null,
            "baseline_price":null,
            "completed_bars":0,
            "first_timestamp_ms":null,
            "last_timestamp_ms":null,
            "highest_price":null,
            "lowest_price":null,
            "current_directional_return_bps":2.0,
            "maximum_favorable_excursion_bps":null,
            "maximum_adverse_excursion_bps":null,
            "peak_giveback_bps":null
        })));

        assert_eq!(result.unwrap_err(), "post-soft path identity is invalid");
    }
}
