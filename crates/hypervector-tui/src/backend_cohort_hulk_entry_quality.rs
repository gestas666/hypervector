//! Strict projection of report-only Hulk entry-quality annotations.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;

const MODE: &str = "cohort_hulk_entry_quality_mechanism_v1";
const SCOPE: &str = "all_live_history_mixed_profiles";
const STRATEGY_ID: &str = "hulk_expansion_bidirectional_tuned_v2";
const QUALITY_CLASSES: [&str; 4] = ["flow_and_volume", "one_of_two", "neither", "unavailable"];
const SIDES: [&str; 2] = ["long", "short"];
const MONEY_TOLERANCE: f64 = 0.000_001;

/// Resolved lifecycle results for one frozen quality annotation.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortHulkEntryQualitySummary {
    pub trades: usize,
    pub wins: usize,
    pub losses: usize,
    pub breakeven: usize,
    pub net_pnl_usd: f64,
    pub mean_net_return_on_margin_pct: Option<f64>,
    pub normalized_profit_factor: Option<f64>,
}

/// Directional partition of resolved Hulk entry-quality evidence.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortHulkEntryQualitySide {
    pub closed_trades: usize,
    pub closed_by_quality: BTreeMap<String, CohortHulkEntryQualitySummary>,
}

/// One unresolved open lifecycle and its point-in-time entry annotation.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortHulkEntryQualityOpen {
    pub symbol: String,
    pub side: String,
    pub quality: String,
    pub flow_direction: Option<i64>,
    pub volume_ratio: Option<f64>,
    pub marked_net_pnl_usd: Option<f64>,
}

/// Execution-incapable Hulk entry-quality evidence shown by the TUI.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortHulkEntryQuality {
    pub closed_trades: usize,
    pub attributable_closed_trades: usize,
    pub closed_by_quality: BTreeMap<String, CohortHulkEntryQualitySummary>,
    pub by_side: BTreeMap<String, CohortHulkEntryQualitySide>,
    pub open_observations: Vec<CohortHulkEntryQualityOpen>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct HulkEntryQualityRaw {
    schema_version: u64,
    mode: String,
    scope: String,
    strategy_id: String,
    current_stage: String,
    contract: ContractRaw,
    feature_contract: FeatureContractRaw,
    closed_trades: usize,
    attributable_closed_trades: usize,
    closed_by_quality: BTreeMap<String, SummaryRaw>,
    by_side: BTreeMap<String, SideRaw>,
    open_trades: usize,
    open_observations: Vec<OpenRaw>,
    predeclared_variants: VariantsRaw,
    limitations: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct ContractRaw {
    report_only: bool,
    execution_authority: String,
    execution_gate: bool,
    position_sizing_authority: bool,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
}

#[derive(Debug, Deserialize)]
struct FeatureContractRaw {
    source: String,
    money_flow_alignment: String,
    symmetric_long_short: bool,
    volume_support_minimum_ratio: f64,
    volume_threshold_origin: String,
}

#[derive(Debug, Deserialize)]
struct SummaryRaw {
    trades: usize,
    wins: usize,
    losses: usize,
    breakeven: usize,
    net_pnl_usd: f64,
    mean_net_return_on_margin_pct: Option<f64>,
    normalized_profit_factor: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct SideRaw {
    closed_trades: usize,
    closed_by_quality: BTreeMap<String, SummaryRaw>,
}

#[derive(Debug, Deserialize)]
struct OpenRaw {
    symbol: String,
    side: String,
    quality: String,
    status: String,
    flow_direction: Option<i64>,
    volume_ratio: Option<f64>,
    marked_net_pnl_usd: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct VariantsRaw {
    annotation: AnnotationVariantRaw,
    control: ControlVariantRaw,
    hard_gate: HardGateVariantRaw,
    scaled: ScaledVariantRaw,
}

#[derive(Debug, Deserialize)]
struct AnnotationVariantRaw {
    entry: String,
    execution: String,
}

#[derive(Debug, Deserialize)]
struct ControlVariantRaw {
    entry: String,
    size_multiplier: f64,
}

#[derive(Debug, Deserialize)]
struct HardGateVariantRaw {
    execution: String,
    requires: String,
}

#[derive(Debug, Deserialize)]
struct ScaledVariantRaw {
    execution: String,
    flow_and_volume: f64,
    one_of_two: f64,
    neither: f64,
}

/// Validate and project report-only Hulk entry-quality evidence.
pub(crate) fn project_hulk_entry_quality(
    raw: Option<HulkEntryQualityRaw>,
) -> Result<Option<CohortHulkEntryQuality>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_envelope(&raw)?;
    let closed_by_quality = project_summaries(raw.closed_by_quality)?;
    let attributed = summary_trade_count(&closed_by_quality);
    if raw.closed_trades < raw.attributable_closed_trades
        || attributed != raw.attributable_closed_trades
    {
        return Err("Hulk entry-quality closed attribution is inconsistent".into());
    }
    let by_side = project_sides(raw.by_side)?;
    validate_side_totals(&closed_by_quality, &by_side, attributed)?;
    let open_observations = project_open(raw.open_observations)?;
    if open_observations.len() != raw.open_trades {
        return Err("Hulk entry-quality open attribution is inconsistent".into());
    }
    Ok(Some(CohortHulkEntryQuality {
        closed_trades: raw.closed_trades,
        attributable_closed_trades: raw.attributable_closed_trades,
        closed_by_quality,
        by_side,
        open_observations,
    }))
}

fn validate_envelope(raw: &HulkEntryQualityRaw) -> Result<(), String> {
    let contract = &raw.contract;
    let feature = &raw.feature_contract;
    let valid = raw.schema_version == 1
        && raw.mode == MODE
        && raw.scope == SCOPE
        && raw.strategy_id == STRATEGY_ID
        && raw.current_stage == "annotation_only"
        && contract.report_only
        && contract.execution_authority == "none"
        && !contract.execution_gate
        && !contract.position_sizing_authority
        && !contract.runtime_strategy_changed
        && !contract.automatic_strategy_changes
        && feature.source == "entry_decision_readiness_metrics"
        && feature.money_flow_alignment == "direction_sign_equals_position_side"
        && feature.symmetric_long_short
        && near(feature.volume_support_minimum_ratio, 1.0)
        && feature.volume_threshold_origin == "untuned_relative_volume_baseline"
        && variants_are_frozen(&raw.predeclared_variants)
        && !raw.limitations.is_empty()
        && raw.limitations.iter().all(|item| !item.trim().is_empty());
    if !valid {
        return Err("Hulk entry-quality contract is invalid".into());
    }
    Ok(())
}

fn variants_are_frozen(raw: &VariantsRaw) -> bool {
    raw.annotation.entry == "unchanged"
        && raw.annotation.execution == "active_stage"
        && raw.control.entry == "unchanged"
        && near(raw.control.size_multiplier, 1.0)
        && raw.hard_gate.execution == "disabled"
        && raw.hard_gate.requires == "flow_and_volume"
        && raw.scaled.execution == "disabled"
        && near(raw.scaled.flow_and_volume, 1.0)
        && near(raw.scaled.one_of_two, 0.5)
        && near(raw.scaled.neither, 0.25)
}

fn project_summaries(
    raw: BTreeMap<String, SummaryRaw>,
) -> Result<BTreeMap<String, CohortHulkEntryQualitySummary>, String> {
    require_exact_keys(&raw, &QUALITY_CLASSES, "quality")?;
    raw.into_iter()
        .map(|(key, value)| Ok((key, project_summary(value)?)))
        .collect()
}

fn project_summary(raw: SummaryRaw) -> Result<CohortHulkEntryQualitySummary, String> {
    let mean_valid = match (raw.trades, raw.mean_net_return_on_margin_pct) {
        (0, None) => true,
        (0, Some(_)) => false,
        (_, Some(value)) => value.is_finite(),
        (_, None) => false,
    };
    let profit_factor_valid = match (raw.losses, raw.normalized_profit_factor) {
        (0, None) => true,
        (0, Some(_)) => false,
        (_, Some(value)) => value.is_finite() && value >= 0.0,
        (_, None) => false,
    };
    if raw.wins + raw.losses + raw.breakeven != raw.trades
        || !raw.net_pnl_usd.is_finite()
        || !mean_valid
        || !profit_factor_valid
    {
        return Err("Hulk entry-quality summary is inconsistent".into());
    }
    Ok(CohortHulkEntryQualitySummary {
        trades: raw.trades,
        wins: raw.wins,
        losses: raw.losses,
        breakeven: raw.breakeven,
        net_pnl_usd: raw.net_pnl_usd,
        mean_net_return_on_margin_pct: raw.mean_net_return_on_margin_pct,
        normalized_profit_factor: raw.normalized_profit_factor,
    })
}

fn project_sides(
    raw: BTreeMap<String, SideRaw>,
) -> Result<BTreeMap<String, CohortHulkEntryQualitySide>, String> {
    require_exact_keys(&raw, &SIDES, "side")?;
    raw.into_iter()
        .map(|(key, value)| {
            let summaries = project_summaries(value.closed_by_quality)?;
            if summary_trade_count(&summaries) != value.closed_trades {
                return Err("Hulk entry-quality side count is inconsistent".into());
            }
            Ok((
                key,
                CohortHulkEntryQualitySide {
                    closed_trades: value.closed_trades,
                    closed_by_quality: summaries,
                },
            ))
        })
        .collect()
}

fn validate_side_totals(
    total: &BTreeMap<String, CohortHulkEntryQualitySummary>,
    sides: &BTreeMap<String, CohortHulkEntryQualitySide>,
    attributed: usize,
) -> Result<(), String> {
    if sides.values().map(|side| side.closed_trades).sum::<usize>() != attributed {
        return Err("Hulk entry-quality directional count is inconsistent".into());
    }
    for quality in QUALITY_CLASSES {
        let expected = &total[quality];
        let directional = SIDES.map(|side| &sides[side].closed_by_quality[quality]);
        if directional.iter().map(|value| value.trades).sum::<usize>() != expected.trades
            || directional.iter().map(|value| value.wins).sum::<usize>() != expected.wins
            || directional.iter().map(|value| value.losses).sum::<usize>() != expected.losses
            || directional
                .iter()
                .map(|value| value.breakeven)
                .sum::<usize>()
                != expected.breakeven
            || !near(
                directional.iter().map(|value| value.net_pnl_usd).sum(),
                expected.net_pnl_usd,
            )
        {
            return Err("Hulk entry-quality directional economics are inconsistent".into());
        }
    }
    Ok(())
}

fn project_open(raw: Vec<OpenRaw>) -> Result<Vec<CohortHulkEntryQualityOpen>, String> {
    raw.into_iter()
        .map(|value| {
            validate_open(&value)?;
            Ok(CohortHulkEntryQualityOpen {
                symbol: value.symbol,
                side: value.side,
                quality: value.quality,
                flow_direction: value.flow_direction,
                volume_ratio: value.volume_ratio,
                marked_net_pnl_usd: value.marked_net_pnl_usd,
            })
        })
        .collect()
}

fn validate_open(raw: &OpenRaw) -> Result<(), String> {
    let flow_valid = raw
        .flow_direction
        .is_none_or(|value| (-1..=1).contains(&value));
    let volume_valid = raw
        .volume_ratio
        .is_none_or(|value| value.is_finite() && value >= 0.0);
    let pnl_valid = raw.marked_net_pnl_usd.is_none_or(f64::is_finite);
    let derived = match (raw.flow_direction, raw.volume_ratio) {
        (Some(flow), Some(volume)) => {
            let aligned = (raw.side == "long" && flow > 0) || (raw.side == "short" && flow < 0);
            match (aligned, volume >= 1.0) {
                (true, true) => "flow_and_volume",
                (true, false) | (false, true) => "one_of_two",
                (false, false) => "neither",
            }
        }
        _ => "unavailable",
    };
    if raw.symbol.trim().is_empty()
        || !SIDES.contains(&raw.side.as_str())
        || raw.status != "unresolved"
        || !flow_valid
        || !volume_valid
        || !pnl_valid
        || raw.quality != derived
    {
        return Err("Hulk entry-quality open observation is invalid".into());
    }
    Ok(())
}

fn require_exact_keys<T, const N: usize>(
    raw: &BTreeMap<String, T>,
    expected: &[&str; N],
    label: &str,
) -> Result<(), String> {
    let observed = raw.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = expected.iter().copied().collect::<BTreeSet<_>>();
    if observed != expected {
        return Err(format!("Hulk entry-quality {label} coverage is incomplete"));
    }
    Ok(())
}

fn summary_trade_count(raw: &BTreeMap<String, CohortHulkEntryQualitySummary>) -> usize {
    raw.values().map(|value| value.trades).sum()
}

fn near(left: f64, right: f64) -> bool {
    left.is_finite() && right.is_finite() && (left - right).abs() <= MONEY_TOLERANCE
}
