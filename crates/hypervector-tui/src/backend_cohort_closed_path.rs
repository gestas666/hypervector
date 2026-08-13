//! Strict projection of completed-candle paths after a closed lifecycle.

use serde::Deserialize;
use std::collections::BTreeMap;

/// Completed-candle path after an authoritative trade exit.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortTradeExitPath {
    pub status: String,
    pub directional_close_return_bps: Option<f64>,
    pub favorable_excursion_bps: Option<f64>,
    pub adverse_excursion_bps: Option<f64>,
    pub interpretation: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawExitPath {
    status: String,
    directional_close_return_bps: Option<f64>,
    favorable_excursion_bps: Option<f64>,
    adverse_excursion_bps: Option<f64>,
    interpretation: Option<String>,
}

pub(crate) fn project_exit_paths(
    raw: BTreeMap<String, RawExitPath>,
) -> Result<BTreeMap<u16, CohortTradeExitPath>, String> {
    raw.into_iter()
        .map(|(horizon, path)| project_path(&horizon, path))
        .collect()
}

fn project_path(horizon: &str, raw: RawExitPath) -> Result<(u16, CohortTradeExitPath), String> {
    let minutes = horizon
        .parse::<u16>()
        .map_err(|_| "trade-reflection horizon is invalid".to_string())?;
    if minutes == 0
        || !matches!(
            raw.status.as_str(),
            "resolved" | "censored" | "missing_data"
        )
    {
        return Err("trade-reflection exit path is invalid".into());
    }
    validate_path_values(&raw)?;
    Ok((
        minutes,
        CohortTradeExitPath {
            status: raw.status,
            directional_close_return_bps: raw.directional_close_return_bps,
            favorable_excursion_bps: raw.favorable_excursion_bps,
            adverse_excursion_bps: raw.adverse_excursion_bps,
            interpretation: raw.interpretation,
        },
    ))
}

fn validate_path_values(path: &RawExitPath) -> Result<(), String> {
    let values = [
        path.directional_close_return_bps,
        path.favorable_excursion_bps,
        path.adverse_excursion_bps,
    ];
    if values.into_iter().flatten().any(|value| !value.is_finite()) {
        return Err("trade-reflection exit path contains a non-finite value".into());
    }
    if path.status == "resolved"
        && (path.directional_close_return_bps.is_none()
            || !matches!(
                path.interpretation.as_deref(),
                Some(
                    "continued_original_direction"
                        | "reversed_against_original_direction"
                        | "unchanged"
                )
            ))
    {
        return Err("resolved trade-reflection exit path is incomplete".into());
    }
    Ok(())
}
