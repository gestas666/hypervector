//! Strict projection of report-only open-profit protection evidence.

use serde::Deserialize;

const METHOD: &str = "measured_entry_fee_rate_no_future_funding_or_slippage";
const TOLERANCE: f64 = 0.000_005;

/// Estimated current and protective-stop economics for one open lifecycle.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortOpenProfitProtection {
    pub status: String,
    pub estimated_exit_now_net_usd: f64,
    pub estimated_stop_net_usd: f64,
    pub marked_to_stop_giveback_usd: f64,
    pub protected_profit_fraction: Option<f64>,
    pub stop_distance_from_mark_bps: f64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawOpenProfitProtection {
    status: String,
    #[serde(default)]
    reason: Option<String>,
    #[serde(default)]
    reported_marked_net_pnl_usd: Option<f64>,
    #[serde(default)]
    estimated_exit_now_net_usd: Option<f64>,
    #[serde(default)]
    estimated_stop_net_usd: Option<f64>,
    #[serde(default)]
    marked_to_stop_giveback_usd: Option<f64>,
    #[serde(default)]
    protected_profit_fraction: Option<f64>,
    #[serde(default)]
    stop_distance_from_mark_bps: Option<f64>,
    #[serde(default)]
    measured_entry_fee_rate_bps: Option<f64>,
    #[serde(default)]
    estimated_current_exit_fee_usd: Option<f64>,
    #[serde(default)]
    estimated_stop_exit_fee_usd: Option<f64>,
    #[serde(default)]
    method: Option<String>,
}

pub(crate) fn project(
    raw: Option<RawOpenProfitProtection>,
) -> Result<Option<CohortOpenProfitProtection>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    if value.status == "unavailable" {
        return project_unavailable(value);
    }
    project_available(value).map(Some)
}

fn project_unavailable(
    value: RawOpenProfitProtection,
) -> Result<Option<CohortOpenProfitProtection>, String> {
    if value.reason.as_deref() != Some("protective_stop_unavailable") || value.has_measurements() {
        return Err("unavailable profit protection is success-shaped".into());
    }
    Ok(None)
}

fn project_available(value: RawOpenProfitProtection) -> Result<CohortOpenProfitProtection, String> {
    if value.reason.is_some() || value.method.as_deref() != Some(METHOD) {
        return Err("profit-protection provenance is invalid".into());
    }
    let marked = required(value.reported_marked_net_pnl_usd, "marked net")?;
    let current = required(value.estimated_exit_now_net_usd, "current net")?;
    let stop = required(value.estimated_stop_net_usd, "stop net")?;
    let giveback = required(value.marked_to_stop_giveback_usd, "giveback")?;
    let distance = required(value.stop_distance_from_mark_bps, "stop distance")?;
    let fee_rate = nonnegative(value.measured_entry_fee_rate_bps, "fee rate")?;
    let current_fee = nonnegative(value.estimated_current_exit_fee_usd, "current fee")?;
    nonnegative(value.estimated_stop_exit_fee_usd, "stop fee")?;
    if !close(giveback, current - stop) || !close(marked - current, current_fee) {
        return Err("profit-protection economics do not reconcile".into());
    }
    validate_status(
        &value.status,
        current,
        stop,
        giveback,
        value.protected_profit_fraction,
    )?;
    if !distance.is_finite() || !fee_rate.is_finite() {
        return Err("profit-protection distance or fee rate is invalid".into());
    }
    Ok(CohortOpenProfitProtection {
        status: value.status,
        estimated_exit_now_net_usd: current,
        estimated_stop_net_usd: stop,
        marked_to_stop_giveback_usd: giveback,
        protected_profit_fraction: value.protected_profit_fraction,
        stop_distance_from_mark_bps: distance,
    })
}

fn validate_status(
    status: &str,
    current: f64,
    stop: f64,
    giveback: f64,
    fraction: Option<f64>,
) -> Result<(), String> {
    let valid = match status {
        "no_open_profit" => current <= 0.0 && fraction.is_none(),
        "open_profit_unprotected" => current > 0.0 && stop <= 0.0 && fraction == Some(0.0),
        "partial_profit_locked" => {
            current > 0.0
                && stop > 0.0
                && giveback > TOLERANCE
                && fraction.is_some_and(|value| close(value, stop / current))
        }
        "current_profit_locked" => {
            current > 0.0
                && stop > 0.0
                && giveback <= TOLERANCE
                && fraction.is_some_and(|value| close(value, 1.0))
        }
        _ => false,
    };
    if valid {
        Ok(())
    } else {
        Err("profit-protection status disagrees with its economics".into())
    }
}

fn required(value: Option<f64>, label: &str) -> Result<f64, String> {
    value
        .filter(|number| number.is_finite())
        .ok_or_else(|| format!("profit-protection {label} is missing or invalid"))
}

fn nonnegative(value: Option<f64>, label: &str) -> Result<f64, String> {
    let parsed = required(value, label)?;
    if parsed < 0.0 {
        return Err(format!("profit-protection {label} must be nonnegative"));
    }
    Ok(parsed)
}

fn close(left: f64, right: f64) -> bool {
    (left - right).abs() <= TOLERANCE
}

impl RawOpenProfitProtection {
    fn has_measurements(&self) -> bool {
        self.reported_marked_net_pnl_usd.is_some()
            || self.estimated_exit_now_net_usd.is_some()
            || self.estimated_stop_net_usd.is_some()
            || self.marked_to_stop_giveback_usd.is_some()
            || self.protected_profit_fraction.is_some()
            || self.stop_distance_from_mark_bps.is_some()
            || self.measured_entry_fee_rate_bps.is_some()
            || self.estimated_current_exit_fee_usd.is_some()
            || self.estimated_stop_exit_fee_usd.is_some()
            || self.method.is_some()
    }
}

#[cfg(test)]
mod tests {
    use super::{RawOpenProfitProtection, project};
    use serde_json::json;

    #[test]
    fn rejects_giveback_that_does_not_reconcile() {
        let raw: RawOpenProfitProtection = serde_json::from_value(json!({
            "status": "open_profit_unprotected",
            "reported_marked_net_pnl_usd": 0.11,
            "estimated_exit_now_net_usd": 0.10,
            "estimated_stop_net_usd": -0.20,
            "marked_to_stop_giveback_usd": 99.0,
            "protected_profit_fraction": 0.0,
            "stop_distance_from_mark_bps": 100.0,
            "measured_entry_fee_rate_bps": 4.32,
            "estimated_current_exit_fee_usd": 0.01,
            "estimated_stop_exit_fee_usd": 0.01,
            "method": "measured_entry_fee_rate_no_future_funding_or_slippage"
        }))
        .expect("raw fixture");

        let error = project(Some(raw)).expect_err("imbalanced giveback must fail");
        assert!(error.contains("do not reconcile"), "{error}");
    }

    #[test]
    fn rejects_success_shaped_unavailable_evidence() {
        let raw: RawOpenProfitProtection = serde_json::from_value(json!({
            "status": "unavailable",
            "reason": "protective_stop_unavailable",
            "estimated_exit_now_net_usd": 0.0
        }))
        .expect("raw fixture");

        let error = project(Some(raw)).expect_err("invented measurement must fail");
        assert!(error.contains("success-shaped"), "{error}");
    }
}
