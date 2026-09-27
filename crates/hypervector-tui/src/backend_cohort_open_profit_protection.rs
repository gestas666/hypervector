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
    pub measured_entry_fee_rate_bps: f64,
    pub estimated_stop_exit_fee_usd: f64,
}

/// One acknowledged venue stop move, priced on the checkpoint's own mark and size.
pub(crate) struct StopMove {
    pub(crate) direction: f64,
    pub(crate) entry_size: f64,
    pub(crate) mark_price: f64,
    pub(crate) previous_trigger_price: f64,
    pub(crate) trigger_price: f64,
}

impl CohortOpenProfitProtection {
    /// Re-price only the stop leg after the venue stop moved, as the backend estimate would.
    ///
    /// The exit-now leg is unchanged. The basis must reproduce the checkpoint's
    /// previous stop fee, and the result must pass the same status validation as
    /// parsed evidence; otherwise no estimate is returned rather than a stale one.
    pub(crate) fn repriced(&self, stop: &StopMove) -> Option<Self> {
        let fee_rate = self.measured_entry_fee_rate_bps / 10_000.0;
        let basis_valid = stop.entry_size.is_finite()
            && stop.entry_size > 0.0
            && stop.mark_price.is_finite()
            && stop.mark_price > 0.0
            && close(
                self.estimated_stop_exit_fee_usd,
                stop.previous_trigger_price * stop.entry_size * fee_rate,
            );
        if !basis_valid {
            return None;
        }
        let shift = stop.trigger_price - stop.previous_trigger_price;
        let current = self.estimated_exit_now_net_usd;
        let stop_net =
            self.estimated_stop_net_usd + shift * stop.entry_size * (stop.direction - fee_rate);
        let giveback = current - stop_net;
        let fraction = (current > 0.0).then(|| (stop_net.max(0.0) / current).min(1.0));
        let status = protection_status(current, stop_net, giveback);
        validate_status(status, current, stop_net, giveback, fraction).ok()?;
        Some(Self {
            status: status.into(),
            estimated_stop_net_usd: stop_net,
            marked_to_stop_giveback_usd: giveback,
            protected_profit_fraction: fraction,
            stop_distance_from_mark_bps: stop.direction * (stop.mark_price - stop.trigger_price)
                / stop.mark_price
                * 10_000.0,
            estimated_stop_exit_fee_usd: stop.trigger_price * stop.entry_size * fee_rate,
            ..self.clone()
        })
    }
}

fn protection_status(current: f64, stop: f64, giveback: f64) -> &'static str {
    if current <= 0.0 {
        "no_open_profit"
    } else if stop <= 0.0 {
        "open_profit_unprotected"
    } else if giveback > TOLERANCE {
        "partial_profit_locked"
    } else {
        "current_profit_locked"
    }
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
    let stop_fee = nonnegative(value.estimated_stop_exit_fee_usd, "stop fee")?;
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
        measured_entry_fee_rate_bps: fee_rate,
        estimated_stop_exit_fee_usd: stop_fee,
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

    /// Backend `build_open_profit_protection` output for one lifecycle and stop.
    fn backend_estimate(value: serde_json::Value) -> super::CohortOpenProfitProtection {
        let raw: RawOpenProfitProtection = serde_json::from_value(value).expect("raw fixture");
        project(Some(raw))
            .expect("backend estimate")
            .expect("available")
    }

    fn assert_matches_backend(
        observed: &super::CohortOpenProfitProtection,
        expected: &super::CohortOpenProfitProtection,
    ) {
        let pairs = [
            (
                observed.estimated_exit_now_net_usd,
                expected.estimated_exit_now_net_usd,
            ),
            (
                observed.estimated_stop_net_usd,
                expected.estimated_stop_net_usd,
            ),
            (
                observed.marked_to_stop_giveback_usd,
                expected.marked_to_stop_giveback_usd,
            ),
            (
                observed.stop_distance_from_mark_bps,
                expected.stop_distance_from_mark_bps,
            ),
            (
                observed.estimated_stop_exit_fee_usd,
                expected.estimated_stop_exit_fee_usd,
            ),
            (
                observed.protected_profit_fraction.expect("fraction"),
                expected.protected_profit_fraction.expect("fraction"),
            ),
        ];
        for (left, right) in pairs {
            assert!((left - right).abs() < 1e-9, "{observed:?} != {expected:?}");
        }
        assert_eq!(observed.status, expected.status);
    }

    #[test]
    fn repriced_long_stop_matches_the_backend_estimate_for_the_raised_trigger() {
        // Both estimates come from the backend's own formula for one BRENTOIL long
        // (entry 99.05 x 5.84, mark 99.9765): the initial stop and the V93 floor raise.
        let initial = backend_estimate(json!({
            "status": "open_profit_unprotected",
            "reported_marked_net_pnl_usd": 5.358215230201701,
            "estimated_exit_now_net_usd": 5.307769975257308,
            "estimated_stop_net_usd": -8.838407701195626,
            "marked_to_stop_giveback_usd": 14.146177676452934,
            "protected_profit_fraction": 0.0,
            "stop_distance_from_mark_bps": 242.30694213140083,
            "measured_entry_fee_rate_bps": 0.8639916500992931,
            "estimated_current_exit_fee_usd": 0.05044525494439275,
            "estimated_stop_exit_fee_usd": 0.049222931397331283,
            "method": "measured_entry_fee_rate_no_future_funding_or_slippage"
        }));
        let raised = backend_estimate(json!({
            "status": "partial_profit_locked",
            "reported_marked_net_pnl_usd": 5.358215230201701,
            "estimated_exit_now_net_usd": 5.307769975257308,
            "estimated_stop_net_usd": 1.3434825159788528,
            "marked_to_stop_giveback_usd": 3.9642874592784554,
            "protected_profit_fraction": 0.2531161904607074,
            "stop_distance_from_mark_bps": 67.90345731246893,
            "measured_entry_fee_rate_bps": 0.8639916500992931,
            "estimated_current_exit_fee_usd": 0.05044525494439275,
            "estimated_stop_exit_fee_usd": 0.050102714222819436,
            "method": "measured_entry_fee_rate_no_future_funding_or_slippage"
        }));

        let observed = initial
            .repriced(&super::StopMove {
                direction: 1.0,
                entry_size: 5.84,
                mark_price: 99.9765,
                previous_trigger_price: 97.554,
                trigger_price: 99.297625,
            })
            .expect("repriced estimate");

        assert_matches_backend(&observed, &raised);
    }

    #[test]
    fn repriced_short_stop_matches_the_backend_estimate_for_the_raised_trigger() {
        let initial = backend_estimate(json!({
            "status": "open_profit_unprotected",
            "reported_marked_net_pnl_usd": 4.72472,
            "estimated_exit_now_net_usd": 4.450399999999999,
            "estimated_stop_net_usd": -6.554352000000001,
            "marked_to_stop_giveback_usd": 11.004752,
            "protected_profit_fraction": 0.0,
            "stop_distance_from_mark_bps": 173.22834645669292,
            "measured_entry_fee_rate_bps": 4.319999999999999,
            "estimated_current_exit_fee_usd": 0.27432,
            "estimated_stop_exit_fee_usd": 0.279072,
            "method": "measured_entry_fee_rate_no_future_funding_or_slippage"
        }));
        let raised = backend_estimate(json!({
            "status": "partial_profit_locked",
            "reported_marked_net_pnl_usd": 4.72472,
            "estimated_exit_now_net_usd": 4.450399999999999,
            "estimated_stop_net_usd": 1.0489312000000002,
            "marked_to_stop_giveback_usd": 3.401468799999999,
            "protected_profit_fraction": 0.23569369045479066,
            "stop_distance_from_mark_bps": 53.54330708661417,
            "measured_entry_fee_rate_bps": 4.319999999999999,
            "estimated_current_exit_fee_usd": 0.27432,
            "estimated_stop_exit_fee_usd": 0.2757888,
            "method": "measured_entry_fee_rate_no_future_funding_or_slippage"
        }));

        let observed = initial
            .repriced(&super::StopMove {
                direction: -1.0,
                entry_size: 0.01,
                mark_price: 63_500.0,
                previous_trigger_price: 64_600.0,
                trigger_price: 63_840.0,
            })
            .expect("repriced estimate");

        assert_matches_backend(&observed, &raised);
    }

    #[test]
    fn reprice_refuses_a_size_basis_that_does_not_reproduce_the_stop_fee() {
        let initial = backend_estimate(json!({
            "status": "open_profit_unprotected",
            "reported_marked_net_pnl_usd": 4.72472,
            "estimated_exit_now_net_usd": 4.450399999999999,
            "estimated_stop_net_usd": -6.554352000000001,
            "marked_to_stop_giveback_usd": 11.004752,
            "protected_profit_fraction": 0.0,
            "stop_distance_from_mark_bps": 173.22834645669292,
            "measured_entry_fee_rate_bps": 4.319999999999999,
            "estimated_current_exit_fee_usd": 0.27432,
            "estimated_stop_exit_fee_usd": 0.279072,
            "method": "measured_entry_fee_rate_no_future_funding_or_slippage"
        }));

        let observed = initial.repriced(&super::StopMove {
            direction: -1.0,
            entry_size: 0.02,
            mark_price: 63_500.0,
            previous_trigger_price: 64_600.0,
            trigger_price: 63_840.0,
        });

        assert_eq!(observed, None);
    }
}
