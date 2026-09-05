//! Strict projection of report-only modeled-versus-live execution evidence.

use std::collections::BTreeMap;

use serde::Deserialize;

/// Aggregate and provider-level execution-contract parity evidence.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortFrictionParity {
    pub provider_symbols: usize,
    pub runtime_shape_aligned: usize,
    pub contract_mismatch: usize,
    pub unsupported_contract: usize,
    pub runtime_contract_missing: usize,
    pub provider_symbols_with_entry_fills: usize,
    pub by_provider_symbol: BTreeMap<String, CohortProviderFrictionParity>,
}

/// Compact TUI projection for one exact provider-symbol mapping.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortProviderFrictionParity {
    pub parity_state: String,
    pub mismatches: Vec<String>,
    pub modeled_entry_liquidity: Option<String>,
    pub modeled_entry_fee_bps: Option<f64>,
    pub modeled_entry_slippage_bps: Option<f64>,
    pub modeled_stop_bps: Option<f64>,
    pub modeled_maximum_hold_seconds: Option<u64>,
    pub modeled_target_policy: Option<String>,
    pub modeled_evidence_source: Option<String>,
    pub runtime_entry_liquidity: Option<String>,
    pub runtime_entry_order: Option<String>,
    pub runtime_stop_bps: Option<f64>,
    pub runtime_maximum_hold_seconds: Option<u64>,
    pub runtime_target_policy: Option<String>,
    pub runtime_provider_recipe_exit_policy: String,
    pub entry_fills: usize,
    pub observed_fee_mean_bps: Option<f64>,
    pub observed_slippage_mean_bps: Option<f64>,
    pub observed_latency_mean_ms: Option<f64>,
    pub fee_mean_minus_modeled_bps: Option<f64>,
    pub slippage_mean_minus_modeled_bps: Option<f64>,
    pub runtime_contract_source: Option<String>,
    pub modeled_stop_description: Option<String>,
    pub modeled_hold_description: Option<String>,
    pub modeled_target_description: Option<String>,
    pub runtime_stop_description: Option<String>,
    pub runtime_hold_description: Option<String>,
    pub runtime_target_description: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct FrictionParityEvidence {
    contract: ReportOnlyContract,
    summary: FrictionParitySummary,
    by_provider_symbol: BTreeMap<String, ProviderFrictionEvidence>,
}

#[derive(Debug, Deserialize)]
struct ReportOnlyContract {
    report_only: bool,
    performance_gate: bool,
    automatic_pause: bool,
    automatic_retuning: bool,
    execution_authority: String,
}

#[derive(Debug, Deserialize)]
struct FrictionParitySummary {
    provider_symbols: usize,
    runtime_shape_aligned: usize,
    contract_mismatch: usize,
    unsupported_contract: usize,
    runtime_contract_missing: usize,
    provider_symbols_with_entry_fills: usize,
}

#[derive(Debug, Deserialize)]
struct ProviderFrictionEvidence {
    parity_state: String,
    mismatches: Vec<String>,
    modeled_contract: Option<ModeledContractEvidence>,
    runtime_contract: Option<RuntimeContractEvidence>,
    #[serde(default)]
    runtime_contract_source: Option<String>,
    observed_entry: ObservedEntryEvidence,
    strategy_edge_identifiable: bool,
    execution_effect: String,
}

#[derive(Debug, Deserialize)]
struct ModeledContractEvidence {
    entry_liquidity: String,
    entry_fee_bps: f64,
    entry_slippage_bps: Option<f64>,
    stop_bps: Option<f64>,
    #[serde(default)]
    stop_policy: Option<String>,
    #[serde(default)]
    minimum_stop_bps: Option<f64>,
    #[serde(default)]
    maximum_stop_bps: Option<f64>,
    maximum_hold_seconds: Option<u64>,
    #[serde(default)]
    maximum_hold_policy: Option<String>,
    #[serde(default)]
    hard_maximum_hold_seconds: Option<u64>,
    target_policy: String,
    #[serde(default)]
    target_liquidity: Option<String>,
    #[serde(default)]
    target_bps: Option<f64>,
    #[serde(default)]
    target_r_multiple: Option<f64>,
    evidence_source: String,
}

#[derive(Debug, Deserialize)]
struct RuntimeContractEvidence {
    entry_liquidity: String,
    entry_order: String,
    stop_bps: Option<f64>,
    #[serde(default)]
    stop_policy: Option<String>,
    #[serde(default)]
    minimum_stop_bps: Option<f64>,
    #[serde(default)]
    maximum_stop_bps: Option<f64>,
    maximum_hold_seconds: u64,
    #[serde(default)]
    maximum_hold_policy: Option<String>,
    #[serde(default)]
    hard_maximum_hold_seconds: Option<u64>,
    target_policy: String,
    #[serde(default)]
    target_liquidity: Option<String>,
    #[serde(default)]
    target_bps: Option<f64>,
    #[serde(default)]
    target_r_multiple: Option<f64>,
    #[serde(default = "ignored_provider_recipe_exit_policy")]
    provider_recipe_exit_policy: String,
}

#[derive(Debug, Deserialize)]
struct ObservedEntryEvidence {
    status: String,
    fills: usize,
    fee_rate_bps: NumericSummary,
    slippage_bps: NumericSummary,
    acknowledgement_latency_ms: NumericSummary,
    fee_mean_minus_modeled_bps: Option<f64>,
    slippage_mean_minus_modeled_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct NumericSummary {
    count: usize,
    mean: Option<f64>,
}

pub(crate) fn project_friction_parity(
    evidence: Option<&FrictionParityEvidence>,
) -> Result<Option<CohortFrictionParity>, String> {
    let Some(value) = evidence else {
        return Ok(None);
    };
    validate_contract(&value.contract)?;
    let projected = value
        .by_provider_symbol
        .iter()
        .map(|(key, row)| project_row(key, row).map(|projected| (key.clone(), projected)))
        .collect::<Result<BTreeMap<_, _>, _>>()?;
    validate_summary(&value.summary, &projected)?;
    Ok(Some(CohortFrictionParity {
        provider_symbols: value.summary.provider_symbols,
        runtime_shape_aligned: value.summary.runtime_shape_aligned,
        contract_mismatch: value.summary.contract_mismatch,
        unsupported_contract: value.summary.unsupported_contract,
        runtime_contract_missing: value.summary.runtime_contract_missing,
        provider_symbols_with_entry_fills: value.summary.provider_symbols_with_entry_fills,
        by_provider_symbol: projected,
    }))
}

fn project_row(
    key: &str,
    row: &ProviderFrictionEvidence,
) -> Result<CohortProviderFrictionParity, String> {
    validate_provider_key(key)?;
    validate_row(row)?;
    let modeled = row.modeled_contract.as_ref();
    let runtime = row.runtime_contract.as_ref();
    Ok(CohortProviderFrictionParity {
        parity_state: row.parity_state.clone(),
        mismatches: row.mismatches.clone(),
        modeled_entry_liquidity: modeled.map(|value| value.entry_liquidity.clone()),
        modeled_entry_fee_bps: modeled.map(|value| value.entry_fee_bps),
        modeled_entry_slippage_bps: modeled.and_then(|value| value.entry_slippage_bps),
        modeled_stop_bps: modeled.and_then(|value| value.stop_bps),
        modeled_maximum_hold_seconds: modeled.and_then(|value| value.maximum_hold_seconds),
        modeled_target_policy: modeled.map(|value| value.target_policy.clone()),
        modeled_evidence_source: modeled.map(|value| value.evidence_source.clone()),
        runtime_entry_liquidity: runtime.map(|value| value.entry_liquidity.clone()),
        runtime_entry_order: runtime.map(|value| value.entry_order.clone()),
        runtime_stop_bps: runtime.and_then(|value| value.stop_bps),
        runtime_maximum_hold_seconds: runtime.map(|value| value.maximum_hold_seconds),
        runtime_target_policy: runtime.map(|value| value.target_policy.clone()),
        runtime_provider_recipe_exit_policy: runtime
            .map_or_else(ignored_provider_recipe_exit_policy, |value| {
                value.provider_recipe_exit_policy.clone()
            }),
        entry_fills: row.observed_entry.fills,
        observed_fee_mean_bps: row.observed_entry.fee_rate_bps.mean,
        observed_slippage_mean_bps: row.observed_entry.slippage_bps.mean,
        observed_latency_mean_ms: row.observed_entry.acknowledgement_latency_ms.mean,
        fee_mean_minus_modeled_bps: row.observed_entry.fee_mean_minus_modeled_bps,
        slippage_mean_minus_modeled_bps: row.observed_entry.slippage_mean_minus_modeled_bps,
        runtime_contract_source: row.runtime_contract_source.clone(),
        modeled_stop_description: modeled.and_then(modeled_stop_description),
        modeled_hold_description: modeled.and_then(|value| {
            hold_description(
                value.maximum_hold_seconds,
                value.maximum_hold_policy.as_deref(),
                value.hard_maximum_hold_seconds,
            )
        }),
        modeled_target_description: modeled.map(|value| {
            target_description(
                &value.target_policy,
                value.target_liquidity.as_deref(),
                value.target_bps,
                value.target_r_multiple,
            )
        }),
        runtime_stop_description: runtime.and_then(runtime_stop_description),
        runtime_hold_description: runtime.and_then(|value| {
            hold_description(
                Some(value.maximum_hold_seconds),
                value.maximum_hold_policy.as_deref(),
                value.hard_maximum_hold_seconds,
            )
        }),
        runtime_target_description: runtime.map(|value| {
            target_description(
                &value.target_policy,
                value.target_liquidity.as_deref(),
                value.target_bps,
                value.target_r_multiple,
            )
        }),
    })
}

fn validate_contract(value: &ReportOnlyContract) -> Result<(), String> {
    if !value.report_only
        || value.performance_gate
        || value.automatic_pause
        || value.automatic_retuning
        || value.execution_authority != "none"
    {
        return Err("friction parity violates report-only contract".into());
    }
    Ok(())
}

fn validate_summary(
    value: &FrictionParitySummary,
    rows: &BTreeMap<String, CohortProviderFrictionParity>,
) -> Result<(), String> {
    let aligned = state_count(rows, "runtime_shape_aligned");
    let mismatched = state_count(rows, "contract_mismatch");
    let unsupported = state_count(rows, "unsupported_contract");
    let missing = state_count(rows, "runtime_contract_missing");
    let filled = rows.values().filter(|row| row.entry_fills > 0).count();
    if value.provider_symbols != rows.len()
        || value.runtime_shape_aligned != aligned
        || value.contract_mismatch != mismatched
        || value.unsupported_contract != unsupported
        || value.runtime_contract_missing != missing
        || value.provider_symbols_with_entry_fills != filled
    {
        return Err("friction parity summary does not match provider rows".into());
    }
    Ok(())
}

fn state_count(rows: &BTreeMap<String, CohortProviderFrictionParity>, state: &str) -> usize {
    rows.values()
        .filter(|row| row.parity_state == state)
        .count()
}

fn validate_row(value: &ProviderFrictionEvidence) -> Result<(), String> {
    let allowed = matches!(
        value.parity_state.as_str(),
        "runtime_shape_aligned"
            | "contract_mismatch"
            | "unsupported_contract"
            | "runtime_contract_missing"
    );
    let mismatch_shape = value.parity_state == "runtime_shape_aligned"
        && !value.mismatches.is_empty()
        || value.parity_state != "runtime_shape_aligned" && value.mismatches.is_empty();
    if !allowed
        || mismatch_shape
        || value.strategy_edge_identifiable
        || value.execution_effect != "report_only"
        || value.mismatches.iter().any(|item| item.trim().is_empty())
    {
        return Err("provider friction parity record is invalid".into());
    }
    validate_modeled(value.modeled_contract.as_ref())?;
    validate_runtime(value.runtime_contract.as_ref())?;
    validate_observed(&value.observed_entry)
}

fn validate_modeled(value: Option<&ModeledContractEvidence>) -> Result<(), String> {
    let Some(contract) = value else {
        return Ok(());
    };
    if !labels_present([
        &contract.entry_liquidity,
        &contract.target_policy,
        &contract.evidence_source,
    ]) || !nonnegative(contract.entry_fee_bps)
        || !optional_nonnegative(contract.entry_slippage_bps)
        || !optional_nonnegative(contract.stop_bps)
        || !optional_nonnegative(contract.minimum_stop_bps)
        || !optional_nonnegative(contract.maximum_stop_bps)
        || !optional_nonnegative(contract.target_bps)
        || !optional_nonnegative(contract.target_r_multiple)
        || contract.maximum_hold_seconds == Some(0)
        || (contract.maximum_hold_policy.as_deref() == Some("signal_exit_unbounded")
            && contract.maximum_hold_seconds.is_some())
        || (contract.maximum_hold_policy.as_deref() != Some("signal_exit_unbounded")
            && contract.maximum_hold_seconds.is_none())
    {
        return Err("modeled friction contract is invalid".into());
    }
    Ok(())
}

fn validate_runtime(value: Option<&RuntimeContractEvidence>) -> Result<(), String> {
    let Some(contract) = value else {
        return Ok(());
    };
    if !labels_present([
        &contract.entry_liquidity,
        &contract.entry_order,
        &contract.target_policy,
    ]) || !optional_nonnegative(contract.stop_bps)
        || !optional_nonnegative(contract.minimum_stop_bps)
        || !optional_nonnegative(contract.maximum_stop_bps)
        || !optional_nonnegative(contract.target_bps)
        || !optional_nonnegative(contract.target_r_multiple)
        || contract.maximum_hold_seconds == 0
        || !matches!(
            contract.provider_recipe_exit_policy.as_str(),
            "ignore" | "honor"
        )
    {
        return Err("runtime friction contract is invalid".into());
    }
    Ok(())
}

fn ignored_provider_recipe_exit_policy() -> String {
    "ignore".into()
}

fn modeled_stop_description(value: &ModeledContractEvidence) -> Option<String> {
    stop_description(
        value.stop_policy.as_deref(),
        value.stop_bps,
        value.minimum_stop_bps,
        value.maximum_stop_bps,
    )
}

fn runtime_stop_description(value: &RuntimeContractEvidence) -> Option<String> {
    stop_description(
        value.stop_policy.as_deref(),
        value.stop_bps,
        value.minimum_stop_bps,
        value.maximum_stop_bps,
    )
}

fn stop_description(
    policy: Option<&str>,
    fixed: Option<f64>,
    minimum: Option<f64>,
    maximum: Option<f64>,
) -> Option<String> {
    match policy {
        Some("none") => Some("NONE".into()),
        Some("fixed_bps") => fixed.map(|value| format!("FIXED {value:.2}bps")),
        Some("structural_clamped_bps") => minimum
            .zip(maximum)
            .map(|(low, high)| format!("STRUCT {low:.2}-{high:.2}bps")),
        Some(value) => Some(value.replace('_', " ").to_uppercase()),
        None => fixed.map(|value| format!("{value:.2}bps")),
    }
}

fn hold_description(
    seconds: Option<u64>,
    policy: Option<&str>,
    hard: Option<u64>,
) -> Option<String> {
    match (seconds, policy, hard) {
        (None, Some("signal_exit_unbounded"), None) => Some("SIGNAL EXIT / NO TIME CAP".into()),
        (Some(value), Some("extend_while_regime_supported"), Some(limit)) => {
            Some(format!("EXTEND {value}s -> HARD {limit}s"))
        }
        (Some(value), _, _) => Some(format!("FIXED {value}s")),
        _ => None,
    }
}

fn target_description(
    policy: &str,
    liquidity: Option<&str>,
    target_bps: Option<f64>,
    target_r_multiple: Option<f64>,
) -> String {
    let prefix = liquidity.map_or_else(String::new, |value| format!("{} ", value.to_uppercase()));
    match policy {
        "none" => "NONE".into(),
        "fixed_bps" => target_bps.map_or_else(
            || "FIXED TARGET N/A".into(),
            |value| format!("{prefix}{value:.2}bps"),
        ),
        "reward_risk" => target_r_multiple.map_or_else(
            || "REWARD/RISK N/A".into(),
            |value| format!("{prefix}{value:.2}R"),
        ),
        "absolute_anchor" => format!("{prefix}DYNAMIC PRIOR-CLOSE"),
        value => value.replace('_', " ").to_uppercase(),
    }
}

fn validate_observed(value: &ObservedEntryEvidence) -> Result<(), String> {
    let expected_status = if value.fills == 0 {
        "not_observed"
    } else {
        "observed"
    };
    if value.status != expected_status
        || value.fee_rate_bps.count != value.fills
        || !valid_summary(&value.fee_rate_bps, value.fills, nonnegative)
        || !valid_summary(&value.slippage_bps, value.fills, f64::is_finite)
        || !valid_summary(&value.acknowledgement_latency_ms, value.fills, nonnegative)
        || !optional_finite(value.fee_mean_minus_modeled_bps)
        || !optional_finite(value.slippage_mean_minus_modeled_bps)
    {
        return Err("observed friction evidence is invalid".into());
    }
    Ok(())
}

fn valid_summary(
    summary: &NumericSummary,
    maximum_count: usize,
    valid_mean: fn(f64) -> bool,
) -> bool {
    summary.count <= maximum_count
        && (summary.count == 0) == summary.mean.is_none()
        && summary.mean.is_none_or(valid_mean)
}

fn validate_provider_key(value: &str) -> Result<(), String> {
    let Some((strategy, symbol)) = value.split_once('|') else {
        return Err("friction parity key must be strategy|symbol".into());
    };
    if strategy.is_empty() || symbol.is_empty() || symbol.contains('|') {
        return Err("friction parity key must be strategy|symbol".into());
    }
    Ok(())
}

fn labels_present<const N: usize>(values: [&str; N]) -> bool {
    values.iter().all(|value| !value.trim().is_empty())
}

fn nonnegative(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}

fn optional_nonnegative(value: Option<f64>) -> bool {
    value.is_none_or(nonnegative)
}

fn optional_finite(value: Option<f64>) -> bool {
    value.is_none_or(f64::is_finite)
}
