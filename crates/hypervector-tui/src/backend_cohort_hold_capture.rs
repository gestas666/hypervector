//! Strict projection of completed-candle capture for accepted live trades.

use serde::Deserialize;

#[derive(Debug, Clone, PartialEq)]
pub struct CohortCompletedHoldCapture {
    pub status: String,
    pub completed_bars: Option<usize>,
    pub maximum_favorable_excursion_bps: Option<f64>,
    pub maximum_adverse_excursion_bps: Option<f64>,
    pub realized_gross_return_bps: Option<f64>,
    pub gross_mfe_capture_ratio: Option<f64>,
    pub peak_giveback_bps: Option<f64>,
    pub observed_cost_hurdle_bps: Option<f64>,
    pub maximum_net_excursion_bps: Option<f64>,
    pub realized_net_return_bps: Option<f64>,
    pub authoritative_gross_return_bps: Option<f64>,
    pub price_gross_reconciliation_gap_bps: Option<f64>,
    pub economic_outcome: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawCompletedHoldCapture {
    status: String,
    #[serde(default)]
    completed_bars: Option<usize>,
    #[serde(default)]
    maximum_favorable_excursion_bps: Option<f64>,
    #[serde(default)]
    maximum_adverse_excursion_bps: Option<f64>,
    #[serde(default)]
    realized_gross_return_bps: Option<f64>,
    #[serde(default)]
    gross_mfe_capture_ratio: Option<f64>,
    #[serde(default)]
    peak_giveback_bps: Option<f64>,
    #[serde(default)]
    observed_cost_hurdle_bps: Option<f64>,
    #[serde(default)]
    maximum_net_excursion_bps: Option<f64>,
    #[serde(default)]
    realized_net_return_bps: Option<f64>,
    #[serde(default)]
    authoritative_gross_return_bps: Option<f64>,
    #[serde(default)]
    price_gross_reconciliation_gap_bps: Option<f64>,
    #[serde(default)]
    economic_outcome: Option<String>,
}

pub(crate) fn project_completed_hold_capture(
    raw: Option<RawCompletedHoldCapture>,
) -> Result<Option<CohortCompletedHoldCapture>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    if !matches!(
        value.status.as_str(),
        "resolved" | "missing_data" | "no_completed_candles"
    ) {
        return Err("completed-hold capture status is invalid".into());
    }
    if value.status == "resolved" {
        validate_resolved(&value)?;
    }
    Ok(Some(CohortCompletedHoldCapture {
        status: value.status,
        completed_bars: value.completed_bars,
        maximum_favorable_excursion_bps: value.maximum_favorable_excursion_bps,
        maximum_adverse_excursion_bps: value.maximum_adverse_excursion_bps,
        realized_gross_return_bps: value.realized_gross_return_bps,
        gross_mfe_capture_ratio: value.gross_mfe_capture_ratio,
        peak_giveback_bps: value.peak_giveback_bps,
        observed_cost_hurdle_bps: value.observed_cost_hurdle_bps,
        maximum_net_excursion_bps: value.maximum_net_excursion_bps,
        realized_net_return_bps: value.realized_net_return_bps,
        authoritative_gross_return_bps: value.authoritative_gross_return_bps,
        price_gross_reconciliation_gap_bps: value.price_gross_reconciliation_gap_bps,
        economic_outcome: value.economic_outcome,
    }))
}

fn validate_resolved(value: &RawCompletedHoldCapture) -> Result<(), String> {
    let numbers = [
        value.maximum_favorable_excursion_bps,
        value.maximum_adverse_excursion_bps,
        value.realized_gross_return_bps,
        value.peak_giveback_bps,
    ];
    if value.completed_bars == Some(0)
        || value.completed_bars.is_none()
        || numbers.into_iter().any(|item| item.is_none())
        || numbers.into_iter().flatten().any(|item| !item.is_finite())
        || value
            .gross_mfe_capture_ratio
            .is_some_and(|item| !item.is_finite())
        || value.maximum_favorable_excursion_bps.unwrap_or(-1.0) < 0.0
        || value.maximum_adverse_excursion_bps.unwrap_or(-1.0) < 0.0
    {
        return Err("resolved completed-hold capture is incomplete".into());
    }
    validate_economics(value)?;
    Ok(())
}

fn validate_economics(value: &RawCompletedHoldCapture) -> Result<(), String> {
    let numeric = [
        value.observed_cost_hurdle_bps,
        value.maximum_net_excursion_bps,
        value.realized_net_return_bps,
        value.authoritative_gross_return_bps,
        value.price_gross_reconciliation_gap_bps,
    ];
    let present = numeric.iter().filter(|item| item.is_some()).count();
    if present == 0 && value.economic_outcome.is_none() {
        return Ok(());
    }
    if present != numeric.len()
        || numeric.into_iter().flatten().any(|item| !item.is_finite())
        || !matches!(
            value.economic_outcome.as_deref(),
            Some(
                "profitable_after_costs"
                    | "breakeven_after_costs"
                    | "never_cleared_observed_cost_hurdle"
                    | "cleared_cost_hurdle_then_surrendered"
                    | "completed_path_unavailable"
            )
        )
    {
        return Err("completed-hold economic capture is incomplete".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_success_shaped_capture_without_mfe() {
        let raw = RawCompletedHoldCapture {
            status: "resolved".into(),
            completed_bars: Some(4),
            maximum_favorable_excursion_bps: None,
            maximum_adverse_excursion_bps: Some(2.0),
            realized_gross_return_bps: Some(1.0),
            gross_mfe_capture_ratio: None,
            peak_giveback_bps: Some(0.0),
            observed_cost_hurdle_bps: None,
            maximum_net_excursion_bps: None,
            realized_net_return_bps: None,
            authoritative_gross_return_bps: None,
            price_gross_reconciliation_gap_bps: None,
            economic_outcome: None,
        };

        assert!(project_completed_hold_capture(Some(raw)).is_err());
    }
}
