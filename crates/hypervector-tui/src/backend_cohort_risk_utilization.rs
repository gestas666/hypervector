//! Validated projection of runtime sizing utilization evidence.

use serde::Deserialize;
use std::collections::BTreeMap;

const RISK_MODE: &str = "cohort_runtime_risk_utilization_v1";
const EPSILON: f64 = 1e-9;

/// One asset's configured and effective entry-sizing projection.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct CohortAssetRiskUtilization {
    pub configured_leverage: f64,
    pub configured_margin_fraction: f64,
    pub configured_max_notional_usd: f64,
    pub uncapped_notional_usd: f64,
    pub planned_notional_usd: f64,
    pub planned_margin_usd: f64,
    pub effective_margin_fraction: f64,
    pub notional_fraction_of_equity: f64,
    pub cap_utilization_ratio: f64,
    pub cap_binding: bool,
}

/// One provider-symbol policy plus its source attribution.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct CohortProviderRiskUtilization {
    #[serde(flatten)]
    pub sizing: CohortAssetRiskUtilization,
    pub sizing_source: String,
}

/// Report-only sizing utilization for the effective runtime profile.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortRiskUtilization {
    pub account_value_usd: f64,
    pub configured_assets: usize,
    pub cap_bound_assets: usize,
    pub configured_maximum_positions: usize,
    pub provider_symbols: usize,
    pub provider_symbol_overrides: usize,
    pub maximum_effective_margin_fraction: f64,
    pub by_asset: BTreeMap<String, CohortAssetRiskUtilization>,
    pub by_provider_symbol: BTreeMap<String, CohortProviderRiskUtilization>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RiskUtilizationEvidenceRaw {
    schema_version: u64,
    mode: String,
    contract: RiskUtilizationContractRaw,
    account_value_usd: f64,
    summary: RiskUtilizationSummaryRaw,
    by_asset: BTreeMap<String, CohortAssetRiskUtilization>,
    #[serde(default)]
    by_provider_symbol: BTreeMap<String, CohortProviderRiskUtilization>,
    #[serde(default)]
    by_provider_symbol_side: BTreeMap<String, CohortProviderRiskUtilization>,
}

#[derive(Debug, Deserialize)]
struct RiskUtilizationContractRaw {
    report_only: bool,
    execution_authority: String,
    performance_gate: bool,
    balance_gate: bool,
    automatic_sizing_change: bool,
}

#[derive(Debug, Deserialize)]
struct RiskUtilizationSummaryRaw {
    configured_assets: usize,
    #[serde(default)]
    executable_assets: Option<usize>,
    cap_bound_assets: usize,
    configured_maximum_positions: usize,
    #[serde(default)]
    provider_symbols: Option<usize>,
    #[serde(default)]
    provider_symbol_overrides: Option<usize>,
    #[serde(default)]
    provider_direction_overrides: Option<usize>,
    maximum_simultaneous_effective_margin_fraction: f64,
}

pub(crate) fn project_risk_utilization(
    raw: Option<RiskUtilizationEvidenceRaw>,
) -> Result<Option<CohortRiskUtilization>, String> {
    let Some(evidence) = raw else {
        return Ok(None);
    };
    validate(&evidence)?;
    Ok(Some(CohortRiskUtilization {
        account_value_usd: evidence.account_value_usd,
        configured_assets: evidence.summary.configured_assets,
        cap_bound_assets: evidence.summary.cap_bound_assets,
        configured_maximum_positions: evidence.summary.configured_maximum_positions,
        provider_symbols: evidence.summary.provider_symbols.unwrap_or(0),
        provider_symbol_overrides: evidence.summary.provider_symbol_overrides.unwrap_or(0),
        maximum_effective_margin_fraction: evidence
            .summary
            .maximum_simultaneous_effective_margin_fraction,
        by_asset: evidence.by_asset,
        by_provider_symbol: evidence.by_provider_symbol,
    }))
}

fn validate(evidence: &RiskUtilizationEvidenceRaw) -> Result<(), String> {
    let contract = &evidence.contract;
    let summary = &evidence.summary;
    let count = evidence.by_asset.len();
    let execution_symbols = execution_symbols(evidence)?;
    if evidence.schema_version != 1
        || evidence.mode != RISK_MODE
        || !contract.report_only
        || contract.execution_authority != "none"
        || contract.performance_gate
        || contract.balance_gate
        || contract.automatic_sizing_change
        || !positive(evidence.account_value_usd)
        || count == 0
        || summary.configured_assets != count
        || summary.cap_bound_assets > count
        || summary.configured_maximum_positions < execution_symbols.len()
    {
        return Err("checkpoint risk-utilization evidence is invalid".into());
    }
    validate_assets(evidence, &execution_symbols)?;
    validate_provider_sizing(evidence)
}

fn validate_assets(
    evidence: &RiskUtilizationEvidenceRaw,
    execution_symbols: &BTreeMap<String, ()>,
) -> Result<(), String> {
    let account = evidence.account_value_usd;
    for (symbol, asset) in &evidence.by_asset {
        if symbol.trim().is_empty() || !asset_valid(asset, account) {
            return Err("checkpoint asset risk-utilization evidence is invalid".into());
        }
    }
    let cap_bound = evidence
        .by_asset
        .values()
        .filter(|asset| asset.cap_binding)
        .count();
    let maximum = maximum_margin(evidence, execution_symbols)?;
    if cap_bound != evidence.summary.cap_bound_assets
        || !nearly_equal(
            maximum,
            evidence
                .summary
                .maximum_simultaneous_effective_margin_fraction,
        )
    {
        return Err("checkpoint risk-utilization summary is inconsistent".into());
    }
    Ok(())
}

fn maximum_margin(
    evidence: &RiskUtilizationEvidenceRaw,
    execution_symbols: &BTreeMap<String, ()>,
) -> Result<f64, String> {
    let mut margins = evidence
        .by_asset
        .iter()
        .filter(|(symbol, _)| execution_symbols.contains_key(*symbol))
        .map(|(symbol, asset)| (symbol.clone(), asset.effective_margin_fraction))
        .collect::<BTreeMap<_, _>>();
    update_provider_margins(&evidence.by_provider_symbol, &mut margins, 2)?;
    update_provider_margins(&evidence.by_provider_symbol_side, &mut margins, 3)?;
    let mut values = margins.into_values().collect::<Vec<_>>();
    values.sort_by(|left, right| right.total_cmp(left));
    Ok(values
        .iter()
        .take(evidence.summary.configured_maximum_positions)
        .sum())
}

fn update_provider_margins(
    rows: &BTreeMap<String, CohortProviderRiskUtilization>,
    margins: &mut BTreeMap<String, f64>,
    parts: usize,
) -> Result<(), String> {
    for (key, row) in rows {
        let symbol = provider_symbol(key, parts)?;
        let current = margins.get(symbol).copied().unwrap_or_default();
        margins.insert(
            symbol.to_owned(),
            current.max(row.sizing.effective_margin_fraction),
        );
    }
    Ok(())
}

fn execution_symbols(
    evidence: &RiskUtilizationEvidenceRaw,
) -> Result<BTreeMap<String, ()>, String> {
    let Some(expected) = evidence.summary.executable_assets else {
        return Ok(evidence
            .by_asset
            .keys()
            .cloned()
            .map(|key| (key, ()))
            .collect());
    };
    let mut symbols = BTreeMap::new();
    for key in evidence.by_provider_symbol.keys() {
        symbols.insert(provider_symbol(key, 2)?.to_owned(), ());
    }
    for key in evidence.by_provider_symbol_side.keys() {
        symbols.insert(provider_symbol(key, 3)?.to_owned(), ());
    }
    if symbols.len() != expected
        || symbols
            .keys()
            .any(|key| !evidence.by_asset.contains_key(key))
    {
        return Err("checkpoint executable risk scope is inconsistent".into());
    }
    Ok(symbols)
}

fn asset_valid(asset: &CohortAssetRiskUtilization, account: f64) -> bool {
    let expected_planned = asset
        .uncapped_notional_usd
        .min(asset.configured_max_notional_usd);
    let expected_margin = asset.planned_notional_usd / asset.configured_leverage;
    let expected_effective = expected_margin / account;
    let expected_notional = asset.planned_notional_usd / account;
    let expected_ratio = asset.planned_notional_usd / asset.uncapped_notional_usd;
    let positive_values = [
        asset.configured_leverage,
        asset.configured_margin_fraction,
        asset.configured_max_notional_usd,
        asset.uncapped_notional_usd,
        asset.planned_notional_usd,
        asset.planned_margin_usd,
        asset.effective_margin_fraction,
        asset.notional_fraction_of_equity,
        asset.cap_utilization_ratio,
    ]
    .into_iter()
    .all(positive);
    positive_values
        && asset.configured_margin_fraction <= 1.0
        && asset.effective_margin_fraction <= 1.0
        && asset.cap_utilization_ratio <= 1.0
        && nearly_equal(asset.planned_notional_usd, expected_planned)
        && nearly_equal(asset.planned_margin_usd, expected_margin)
        && nearly_equal(asset.effective_margin_fraction, expected_effective)
        && nearly_equal(asset.notional_fraction_of_equity, expected_notional)
        && nearly_equal(asset.cap_utilization_ratio, expected_ratio)
        && asset.cap_binding == (asset.uncapped_notional_usd > asset.configured_max_notional_usd)
}

fn validate_provider_sizing(evidence: &RiskUtilizationEvidenceRaw) -> Result<(), String> {
    let count = evidence.by_provider_symbol.len();
    let overrides = evidence
        .by_provider_symbol
        .values()
        .filter(|row| row.sizing_source == "provider_override")
        .count();
    let summary_matches = evidence.summary.provider_symbols.unwrap_or(0) == count
        && evidence.summary.provider_symbol_overrides.unwrap_or(0) == overrides
        && evidence.summary.provider_direction_overrides.unwrap_or(0)
            == evidence.by_provider_symbol_side.len();
    let rows_valid = evidence.by_provider_symbol.iter().all(|(key, row)| {
        provider_key_valid(key, 2)
            && matches!(
                row.sizing_source.as_str(),
                "asset_default" | "provider_override"
            )
            && asset_valid(&row.sizing, evidence.account_value_usd)
    });
    let direction_rows_valid = evidence.by_provider_symbol_side.iter().all(|(key, row)| {
        provider_key_valid(key, 3)
            && row.sizing_source == "provider_direction_override"
            && asset_valid(&row.sizing, evidence.account_value_usd)
    });
    if !summary_matches || !rows_valid || !direction_rows_valid {
        return Err("checkpoint provider risk-utilization evidence is invalid".into());
    }
    Ok(())
}

fn provider_symbol(value: &str, expected_parts: usize) -> Result<&str, String> {
    let parts = value.split('|').collect::<Vec<_>>();
    if parts.len() != expected_parts || parts.iter().any(|part| part.is_empty()) {
        return Err("checkpoint provider risk-utilization key is invalid".into());
    }
    Ok(parts[1])
}

fn provider_key_valid(value: &str, expected_parts: usize) -> bool {
    provider_symbol(value, expected_parts).is_ok()
}

fn positive(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn nearly_equal(left: f64, right: f64) -> bool {
    (left - right).abs() <= EPSILON * left.abs().max(right.abs()).max(1.0)
}
