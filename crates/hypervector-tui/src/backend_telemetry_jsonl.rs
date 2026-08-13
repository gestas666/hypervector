//! Private JSONL normalization and structural validation.

use serde_json::Value;

use crate::backend_live_projection::normalize_live_event;

use super::{BackendTelemetryError, LedgerRow};

pub(super) fn parse_rows(content: &str) -> Result<Vec<LedgerRow>, BackendTelemetryError> {
    let mut rows: Vec<LedgerRow> = content
        .lines()
        .enumerate()
        .filter(|(_, line)| !line.trim().is_empty())
        .map(|(index, line)| {
            let value: Value = serde_json::from_str(line).map_err(|source| {
                BackendTelemetryError::InvalidJson {
                    line: index + 1,
                    source,
                }
            })?;
            let row = serde_json::from_value(normalize_live_event(value)).map_err(|source| {
                BackendTelemetryError::InvalidJson {
                    line: index + 1,
                    source,
                }
            })?;
            validate_source_diagnostics(&row, index + 1)?;
            Ok(row)
        })
        .collect::<Result<_, _>>()?;
    carry_identity_forward(&mut rows);
    Ok(rows)
}

fn validate_source_diagnostics(row: &LedgerRow, line: usize) -> Result<(), BackendTelemetryError> {
    let Some(value) = row.regime_diagnostics.as_ref() else {
        return Ok(());
    };
    let invalid = |reason: String| BackendTelemetryError::InvalidSourceDiagnostics { line, reason };
    if value.authority != "telemetry_only" {
        return Err(invalid("authority must be telemetry_only".into()));
    }
    let primary = row
        .primary_regime
        .as_deref()
        .ok_or_else(|| invalid("outer primary regime is missing".into()))?;
    if value.confirmed_primary != primary {
        return Err(invalid(format!(
            "diagnostic confirmed regime {} differs from {primary}",
            value.confirmed_primary
        )));
    }
    if value.state_filtered != (value.raw_primary != value.confirmed_primary) {
        return Err(invalid("state_filtered is inconsistent".into()));
    }
    let ranks = [
        (value.raw_confidence, "raw confidence"),
        (value.adx_range_percentile_threshold, "ADX range threshold"),
        (value.adx_weak_percentile_threshold, "ADX weak threshold"),
    ];
    if let Some((_, label)) = ranks
        .iter()
        .find(|(number, _)| !number.is_finite() || !(0.0..=1.0).contains(number))
    {
        return Err(invalid(format!("{label} must be within [0, 1]")));
    }
    if value.adx_range_percentile_threshold >= value.adx_weak_percentile_threshold {
        return Err(invalid(
            "ADX range threshold must be below weak threshold".into(),
        ));
    }
    Ok(())
}

fn carry_identity_forward(rows: &mut [LedgerRow]) {
    let mut symbol = None;
    for row in rows {
        if row.symbol.is_some() {
            symbol.clone_from(&row.symbol);
        } else {
            row.symbol.clone_from(&symbol);
        }
    }
}
