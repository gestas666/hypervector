//! Strict projection of fee-only profit-lock counterfactual economics.

use serde::Deserialize;

const METHOD: &str = "measured_entry_fee_rate_causal_reference_price";

/// One causal exit estimate with counterfactual funding and slippage excluded.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortOpenProfitLockEconomics {
    pub status: String,
    pub reference_price: f64,
    pub gross_return_bps: f64,
    pub estimated_net_pnl_excluding_funding_usd: f64,
    pub estimated_current_exit_net_excluding_funding_usd: f64,
    pub estimated_minus_current_exit_net_excluding_funding_usd: f64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawOpenProfitLockEconomics {
    status: String,
    reason: Option<String>,
    reference_price: Option<f64>,
    gross_return_bps: Option<f64>,
    gross_pnl_usd: Option<f64>,
    estimated_entry_fee_usd: Option<f64>,
    estimated_exit_fee_usd: Option<f64>,
    estimated_net_pnl_excluding_funding_usd: Option<f64>,
    estimated_current_exit_net_excluding_funding_usd: Option<f64>,
    estimated_minus_current_exit_net_excluding_funding_usd: Option<f64>,
    funding_included: Option<bool>,
    additional_slippage_included: Option<bool>,
    method: Option<String>,
}

pub(crate) fn project(
    schema_version: u16,
    policy_status: &str,
    trigger_reference_price: Option<f64>,
    active_stop_price: Option<f64>,
    raw: Option<RawOpenProfitLockEconomics>,
) -> Result<Option<CohortOpenProfitLockEconomics>, String> {
    if schema_version == 1 {
        return if raw.is_none() {
            Ok(None)
        } else {
            Err("v1 open profit-lock contains v2 economics".into())
        };
    }
    let value = raw.ok_or_else(|| "v2 open profit-lock economics are missing".to_string())?;
    let (expected_status, expected_reference) = match policy_status {
        "triggered_before_current_boundary" => ("estimated_trigger_exit", trigger_reference_price),
        "armed_not_triggered" => ("estimated_active_stop_exit", active_stop_price),
        _ => return project_unavailable(value),
    };
    project_estimate(value, expected_status, expected_reference)
}

fn project_unavailable(
    raw: RawOpenProfitLockEconomics,
) -> Result<Option<CohortOpenProfitLockEconomics>, String> {
    if raw.status != "unavailable"
        || raw.reason.as_deref().is_none_or(str::is_empty)
        || !estimated_fields_absent(&raw)
    {
        return Err("unavailable profit-lock counterfactual economics are invalid".into());
    }
    Ok(None)
}

fn project_estimate(
    raw: RawOpenProfitLockEconomics,
    expected_status: &str,
    expected_reference: Option<f64>,
) -> Result<Option<CohortOpenProfitLockEconomics>, String> {
    let reference = required(raw.reference_price, "reference price")?;
    let gross_return = required(raw.gross_return_bps, "gross return")?;
    let gross_pnl = required(raw.gross_pnl_usd, "gross PnL")?;
    let entry_fee = required(raw.estimated_entry_fee_usd, "entry fee")?;
    let exit_fee = required(raw.estimated_exit_fee_usd, "exit fee")?;
    let net = required(
        raw.estimated_net_pnl_excluding_funding_usd,
        "estimated net PnL",
    )?;
    let current = required(
        raw.estimated_current_exit_net_excluding_funding_usd,
        "current exit net PnL",
    )?;
    let delta = required(
        raw.estimated_minus_current_exit_net_excluding_funding_usd,
        "estimated delta",
    )?;
    if raw.status != expected_status
        || raw.reason.is_some()
        || !expected_reference.is_some_and(|value| approximately(value, reference))
        || reference <= 0.0
        || !gross_pnl.is_finite()
        || entry_fee < 0.0
        || exit_fee < 0.0
        || raw.funding_included != Some(false)
        || raw.additional_slippage_included != Some(false)
        || raw.method.as_deref() != Some(METHOD)
        || !approximately(delta, net - current)
    {
        return Err("profit-lock counterfactual economics are invalid".into());
    }
    Ok(Some(CohortOpenProfitLockEconomics {
        status: raw.status,
        reference_price: reference,
        gross_return_bps: gross_return,
        estimated_net_pnl_excluding_funding_usd: net,
        estimated_current_exit_net_excluding_funding_usd: current,
        estimated_minus_current_exit_net_excluding_funding_usd: delta,
    }))
}

fn estimated_fields_absent(raw: &RawOpenProfitLockEconomics) -> bool {
    raw.reference_price.is_none()
        && raw.gross_return_bps.is_none()
        && raw.gross_pnl_usd.is_none()
        && raw.estimated_entry_fee_usd.is_none()
        && raw.estimated_exit_fee_usd.is_none()
        && raw.estimated_net_pnl_excluding_funding_usd.is_none()
        && raw
            .estimated_current_exit_net_excluding_funding_usd
            .is_none()
        && raw
            .estimated_minus_current_exit_net_excluding_funding_usd
            .is_none()
        && raw.funding_included.is_none()
        && raw.additional_slippage_included.is_none()
        && raw.method.is_none()
}

fn required(value: Option<f64>, label: &str) -> Result<f64, String> {
    match value {
        Some(number) if number.is_finite() => Ok(number),
        _ => Err(format!("profit-lock counterfactual {label} is invalid")),
    }
}

fn approximately(left: f64, right: f64) -> bool {
    left.is_finite() && right.is_finite() && (left - right).abs() <= 1e-6
}
