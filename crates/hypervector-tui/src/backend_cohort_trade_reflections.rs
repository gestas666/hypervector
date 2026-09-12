//! Strict read-only projection of lifecycle regime reflection evidence.
pub use crate::backend_cohort_closed_path::CohortTradeExitPath;
use crate::backend_cohort_closed_path::{RawExitPath, project_exit_paths};
pub use crate::backend_cohort_entry_followthrough::CohortTradeEntryFollowthroughPath;
use crate::backend_cohort_entry_followthrough::{
    RawEntryFollowthroughPath, project_entry_followthrough_paths,
};
pub use crate::backend_cohort_exit_plan::CohortOpenExitPlan;
use crate::backend_cohort_exit_plan::{RawOpenExitPlan, project_open_exit_plan};
pub use crate::backend_cohort_extension_path::CohortOpenExtensionPath;
use crate::backend_cohort_extension_path::{RawOpenExtensionPath, project_open_extension_path};
pub use crate::backend_cohort_hold_capture::CohortCompletedHoldCapture;
use crate::backend_cohort_hold_capture::{RawCompletedHoldCapture, project_completed_hold_capture};
use crate::backend_cohort_ignored_provider_exit::{
    RawClosedIgnoredProviderExit, RawIgnoredProviderExit, project as project_ignored_provider_exit,
    project_closed as project_closed_ignored_provider_exit,
};
use crate::backend_cohort_open_path::{RawOpenPath, project_open_path};
use crate::backend_cohort_open_post_soft_trail::{
    RawOpenPostSoftTrail, project as project_open_trail,
};
use crate::backend_cohort_open_profit_lock::{
    RawOpenProfitLock, project as project_open_profit_lock,
};
use crate::backend_cohort_open_profit_protection::{
    RawOpenProfitProtection, project as project_open_profit_protection,
};
pub use crate::backend_cohort_open_trade_reflection::CohortOpenTradeReflection;
use crate::backend_cohort_provider_contract_outcomes::{
    RawProviderContractOutcomeEvidence, project_outcome_count,
};
use crate::backend_cohort_regime_assessment::{
    RawRegimeAssessment, ReflectionContract, validate_contract,
    validate_optional_regime_assessment, validate_regime_assessment,
};
pub use crate::backend_cohort_regime_opposition::CohortRegimeOppositionEpisode;
use crate::backend_cohort_regime_opposition::{
    RawRegimeOppositionEpisode, project_regime_opposition,
};
pub use crate::backend_cohort_timer_context::{
    CohortTimerContextEvidence, CohortTimerProviderEvidence,
};
use crate::backend_cohort_timer_context::{RawTimerContextEvidence, project_timer_context};
use crate::backend_cohort_trade_performance::{
    CohortTradePerformance, RawTradePerformance, project_trade_performance,
};
use crate::backend_cohort_trade_reflection_values::{
    RawExecutionLeg, RawMarkedEconomics, RawProtectiveStop, RawRegimeDrift, RawTargetOrder,
    project_protective_stop, project_target_order,
};
use serde::Deserialize;
use std::collections::{BTreeMap, HashSet};

#[path = "backend_cohort_trade_reflection_models.rs"]
mod models;
#[path = "backend_cohort_trade_reflections_projection.rs"]
mod projection;

pub use models::{CohortTradeReflection, CohortTradeRegimeContext};
use projection::{apply_open_identity, project_context, validate_identity, validate_open_identity};
pub(crate) use projection::{
    project_open_trade_reflections, project_trade_reflections, provider_contract_outcome_count,
};

type ProjectedTradeReflections = (
    Option<bool>,
    Vec<CohortTradeReflection>,
    Vec<CohortTradeReflection>,
    Option<CohortTimerContextEvidence>,
    Option<CohortTradePerformance>,
);
#[derive(Debug, Deserialize)]
pub(crate) struct TradeReflectionEvidence {
    contract: ReflectionContract,
    closed_trades: usize,
    context_coverage: ContextCoverage,
    #[serde(default)]
    maximum_hold_context_journal: Option<RawTimerContextEvidence>,
    #[serde(default)]
    performance: Option<RawTradePerformance>,
    #[serde(default)]
    all_time_live: Option<AllTimeTradeReflectionEvidence>,
    #[serde(default)]
    provider_contract_history: Option<RawProviderContractOutcomeEvidence>,
    trades: Vec<RawTradeReflection>,
}

#[derive(Debug, Deserialize)]
struct AllTimeTradeReflectionEvidence {
    scope: String,
    closed_trades: usize,
    trades: Vec<RawTradeReflection>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct OpenTradeReflectionEvidence {
    contract: ReflectionContract,
    as_of_timestamp_ms: Option<u64>,
    open_lifecycles: usize,
    trades: Vec<RawOpenTradeReflection>,
}

#[derive(Debug, Deserialize)]
struct ContextCoverage {
    complete: bool,
}

#[derive(Debug, Deserialize)]
struct RawTradeReflection {
    lifecycle_id: String,
    source_run_id: String,
    #[serde(default)]
    source_profile_fingerprint: Option<String>,
    symbol: String,
    strategy_id: String,
    #[serde(default)]
    entry_strategy_id: Option<String>,
    #[serde(default)]
    exit_controller_strategy_id: Option<String>,
    #[serde(default)]
    cross_provider_exit: Option<bool>,
    side: String,
    exit_reason: Option<String>,
    net_pnl_usd: f64,
    #[serde(default)]
    entry: Option<RawExecutionLeg>,
    #[serde(default)]
    exit: Option<RawExecutionLeg>,
    #[serde(default)]
    protective_stop: Option<RawProtectiveStop>,
    #[serde(default)]
    holding_time_ms: Option<u64>,
    #[serde(default)]
    fees_usd: Option<f64>,
    #[serde(default)]
    funding_usd: Option<f64>,
    #[serde(default)]
    entry_margin_used_usd: Option<f64>,
    #[serde(default)]
    leverage: Option<f64>,
    #[serde(default)]
    price_return_pct: Option<f64>,
    #[serde(default)]
    net_return_on_margin_pct: Option<f64>,
    entry_context: RawContextPair,
    #[serde(default)]
    entry_regime_assessment: Option<RawRegimeAssessment>,
    exit_context: RawContextPair,
    exit_regime_assessment: RawRegimeAssessment,
    #[serde(default)]
    regime_opposition_episode: Option<RawRegimeOppositionEpisode>,
    #[serde(default)]
    entry_followthrough_path: BTreeMap<String, RawEntryFollowthroughPath>,
    #[serde(default)]
    completed_hold_capture: Option<RawCompletedHoldCapture>,
    #[serde(default)]
    ignored_provider_exit_outcome: Option<RawClosedIgnoredProviderExit>,
    post_exit_path: BTreeMap<String, RawExitPath>,
}

#[derive(Debug, Deserialize)]
struct RawOpenTradeReflection {
    lifecycle_id: String,
    source_run_id: String,
    symbol: String,
    strategy_id: String,
    side: String,
    #[serde(default)]
    protective_stop: Option<RawProtectiveStop>,
    #[serde(default)]
    profit_protection: Option<RawOpenProfitProtection>,
    #[serde(default)]
    target_order: Option<RawTargetOrder>,
    exit_plan: RawOpenExitPlan,
    path_since_entry: RawOpenPath,
    #[serde(default)]
    path_since_soft_deadline: Option<RawOpenExtensionPath>,
    #[serde(default)]
    post_soft_trail_challenger: Option<RawOpenPostSoftTrail>,
    #[serde(default)]
    open_profit_lock_challenger: Option<RawOpenProfitLock>,
    #[serde(default)]
    ignored_provider_exit_observer: Option<RawIgnoredProviderExit>,
    holding_time_ms: u64,
    entry_context: RawContextPair,
    #[serde(default)]
    entry_regime_assessment: Option<RawRegimeAssessment>,
    current_context: RawContextPair,
    regime_drift: RawRegimeDrift,
    regime_assessment: RawRegimeAssessment,
    #[serde(default)]
    regime_opposition_episode: Option<RawRegimeOppositionEpisode>,
    marked_economics: RawMarkedEconomics,
}

#[derive(Debug, Deserialize)]
struct RawContextPair {
    signal_provider: RawRegimeContext,
    canonical_regime: RawRegimeContext,
    #[serde(default)]
    exit_controller: Option<RawRegimeContext>,
}

#[derive(Debug, Deserialize)]
struct RawRegimeContext {
    status: String,
    primary_regime: Option<String>,
    state_1m: Option<String>,
    state_5m: Option<String>,
    context_15m: Option<String>,
    confidence: Option<f64>,
    #[serde(default)]
    readiness: Option<RawRegimeReadiness>,
}

#[derive(Debug, Deserialize)]
struct RawRegimeReadiness {
    #[serde(default)]
    metrics: Option<RawRegimeReadinessMetrics>,
}

#[derive(Debug, Deserialize)]
struct RawRegimeReadinessMetrics {
    #[serde(default)]
    breakout_side: Option<String>,
    #[serde(default)]
    structural_direction: Option<String>,
    #[serde(default)]
    breakout_side_relation: Option<String>,
}

fn project_trade(raw: RawTradeReflection) -> Result<CohortTradeReflection, String> {
    validate_identity(&raw)?;
    validate_optional_regime_assessment(raw.entry_regime_assessment.as_ref())?;
    validate_regime_assessment(&raw.exit_regime_assessment)?;
    let (controller, cross_provider_exit) = controller_identity(&raw)?;
    let mut projected = CohortTradeReflection::default();
    apply_closed_identity(&mut projected, &raw, controller, cross_provider_exit);
    apply_closed_economics(&mut projected, &raw);
    let stop = project_protective_stop(raw.protective_stop)?;
    projected.protective_stop_oid = stop.0;
    projected.protective_stop_price = stop.1;
    let paths = project_exit_paths(raw.post_exit_path)?;
    let followthrough = project_entry_followthrough_paths(raw.entry_followthrough_path)?;
    apply_closed_contexts(
        &mut projected,
        raw.entry_context,
        raw.entry_regime_assessment,
        raw.exit_context,
        raw.exit_regime_assessment,
    )?;
    projected.regime_opposition = project_regime_opposition(raw.regime_opposition_episode)?;
    projected.entry_followthrough_paths = followthrough;
    projected.completed_hold_capture = project_completed_hold_capture(raw.completed_hold_capture)?;
    projected.ignored_provider_exit_outcome =
        project_closed_ignored_provider_exit(raw.ignored_provider_exit_outcome)?;
    projected.post_exit_paths = paths;
    Ok(projected)
}

fn controller_identity(raw: &RawTradeReflection) -> Result<(String, bool), String> {
    let controller = raw
        .exit_controller_strategy_id
        .clone()
        .unwrap_or_else(|| raw.strategy_id.clone());
    let cross_provider = controller != raw.strategy_id;
    if raw.entry_strategy_id.as_deref().unwrap_or(&raw.strategy_id) != raw.strategy_id
        || raw
            .cross_provider_exit
            .is_some_and(|value| value != cross_provider)
    {
        return Err("trade-reflection controller attribution is inconsistent".into());
    }
    Ok((controller, cross_provider))
}

fn apply_closed_identity(
    projected: &mut CohortTradeReflection,
    raw: &RawTradeReflection,
    controller: String,
    cross_provider: bool,
) {
    projected.lifecycle_id = raw.lifecycle_id.clone();
    projected.source_run_id = raw.source_run_id.clone();
    projected.source_profile_fingerprint = raw.source_profile_fingerprint.clone();
    projected.symbol = raw.symbol.clone();
    projected.strategy_id = raw.strategy_id.clone();
    projected.exit_controller_strategy_id = controller;
    projected.cross_provider_exit = cross_provider;
    projected.side = raw.side.clone();
    projected.exit_reason = raw.exit_reason.clone();
}

fn apply_closed_economics(projected: &mut CohortTradeReflection, raw: &RawTradeReflection) {
    projected.net_pnl_usd = raw.net_pnl_usd;
    projected.entry_price = raw.entry.as_ref().map(|value| value.price);
    projected.exit_price = raw.exit.as_ref().map(|value| value.price);
    projected.entry_venue_timestamp_ms = raw.entry.as_ref().map(|value| value.venue_timestamp_ms);
    projected.exit_venue_timestamp_ms = raw.exit.as_ref().map(|value| value.venue_timestamp_ms);
    projected.holding_time_ms = raw.holding_time_ms;
    projected.fees_usd = raw.fees_usd;
    projected.funding_usd = raw.funding_usd;
    projected.entry_margin_used_usd = raw.entry_margin_used_usd;
    projected.leverage = raw.leverage;
    projected.price_return_pct = raw.price_return_pct;
    projected.net_return_on_margin_pct = raw.net_return_on_margin_pct;
}

fn apply_closed_contexts(
    projected: &mut CohortTradeReflection,
    entry: RawContextPair,
    entry_assessment: Option<RawRegimeAssessment>,
    exit: RawContextPair,
    exit_assessment: RawRegimeAssessment,
) -> Result<(), String> {
    projected.entry_signal = project_context(entry.signal_provider)?;
    projected.entry_canonical = project_context(entry.canonical_regime)?;
    apply_entry_assessment(projected, entry_assessment);
    projected.exit_signal = project_context(exit.signal_provider)?;
    projected.exit_canonical = project_context(exit.canonical_regime)?;
    projected.exit_controller =
        project_context(exit.exit_controller.unwrap_or_else(unavailable_raw_context))?;
    apply_exit_assessment(projected, exit_assessment);
    Ok(())
}

fn apply_entry_assessment(
    projected: &mut CohortTradeReflection,
    assessment: Option<RawRegimeAssessment>,
) {
    let Some(value) = assessment else {
        projected.entry_structure_stance = "unavailable".into();
        projected.entry_component_stance = "unavailable".into();
        projected.entry_maximum_hold_context = "unavailable".into();
        return;
    };
    projected.entry_structure_support_score = value.structure_support_score;
    projected.entry_structure_stance = value.structure_stance;
    projected.entry_component_alignment_score = value.component_alignment_score;
    projected.entry_component_stance = value.component_stance;
    projected.entry_movement_strength = value.movement_strength;
    projected.entry_maximum_hold_context = value.maximum_hold_context;
}

fn apply_exit_assessment(projected: &mut CohortTradeReflection, assessment: RawRegimeAssessment) {
    projected.exit_structure_support_score = assessment.structure_support_score;
    projected.exit_structure_stance = assessment.structure_stance;
    projected.exit_component_alignment_score = assessment.component_alignment_score;
    projected.exit_component_stance = assessment.component_stance;
    projected.exit_movement_strength = assessment.movement_strength;
    projected.exit_maximum_hold_context = assessment.maximum_hold_context;
}

fn unavailable_raw_context() -> RawRegimeContext {
    RawRegimeContext {
        status: "unavailable".into(),
        primary_regime: None,
        state_1m: None,
        state_5m: None,
        context_15m: None,
        confidence: None,
        readiness: None,
    }
}

struct OpenOrderInputs {
    stop: (Option<u64>, Option<f64>),
    target: Option<crate::backend_cohort_trade_reflection_values::ProjectedTargetOrder>,
    exit_plan: CohortOpenExitPlan,
    profit_protection: Option<RawOpenProfitProtection>,
    path_since_entry: RawOpenPath,
    path_since_soft_deadline: Option<RawOpenExtensionPath>,
    post_soft_trail: Option<RawOpenPostSoftTrail>,
    open_profit_lock: Option<RawOpenProfitLock>,
    ignored_provider_exit: Option<RawIgnoredProviderExit>,
}

fn project_open_trade(
    raw: RawOpenTradeReflection,
    as_of: Option<u64>,
) -> Result<CohortOpenTradeReflection, String> {
    validate_open_identity(&raw)?;
    validate_optional_regime_assessment(raw.entry_regime_assessment.as_ref())?;
    validate_regime_assessment(&raw.regime_assessment)?;
    let mut projected = CohortOpenTradeReflection::default();
    apply_open_identity(&mut projected, &raw);
    let stop = project_protective_stop(raw.protective_stop)?;
    let target = project_target_order(raw.target_order)?;
    let mut exit_plan = project_open_exit_plan(&raw.strategy_id, raw.exit_plan)?;
    exit_plan.bind_observation(as_of)?;
    apply_open_orders(
        &mut projected,
        OpenOrderInputs {
            stop,
            target,
            exit_plan,
            profit_protection: raw.profit_protection,
            path_since_entry: raw.path_since_entry,
            path_since_soft_deadline: raw.path_since_soft_deadline,
            post_soft_trail: raw.post_soft_trail_challenger,
            open_profit_lock: raw.open_profit_lock_challenger,
            ignored_provider_exit: raw.ignored_provider_exit_observer,
        },
    )?;
    apply_open_contexts(
        &mut projected,
        raw.entry_context,
        raw.entry_regime_assessment,
        raw.current_context,
        raw.regime_drift,
        raw.regime_assessment,
    )?;
    projected.regime_opposition = project_regime_opposition(raw.regime_opposition_episode)?;
    projected.mark_price = raw.marked_economics.mark_price;
    projected.active_lifecycle_marked_net_pnl_usd =
        raw.marked_economics.active_lifecycle_marked_net_pnl_usd;
    Ok(projected)
}

fn apply_open_orders(
    projected: &mut CohortOpenTradeReflection,
    inputs: OpenOrderInputs,
) -> Result<(), String> {
    let OpenOrderInputs {
        stop,
        target,
        exit_plan,
        profit_protection,
        path_since_entry,
        path_since_soft_deadline,
        post_soft_trail,
        open_profit_lock,
        ignored_provider_exit,
    } = inputs;
    projected.protective_stop_oid = stop.0;
    projected.protective_stop_price = stop.1;
    projected.profit_protection = project_open_profit_protection(profit_protection)?;
    projected.target_order_oid = target.as_ref().map(|value| value.oid);
    projected.target_order_price = target.as_ref().map(|value| value.limit_price);
    projected.target_directional_distance_bps =
        target.as_ref().map(|value| value.directional_distance_bps);
    projected.exit_plan = exit_plan;
    projected.path_since_entry = project_open_path(path_since_entry)?;
    projected.path_since_soft_deadline = path_since_soft_deadline
        .map(project_open_extension_path)
        .transpose()?;
    projected.post_soft_trail_challenger = project_open_trail(post_soft_trail)?;
    projected.open_profit_lock_challenger = project_open_profit_lock(open_profit_lock)?;
    projected.ignored_provider_exit_observer =
        project_ignored_provider_exit(ignored_provider_exit)?;
    Ok(())
}

fn apply_open_contexts(
    projected: &mut CohortOpenTradeReflection,
    entry: RawContextPair,
    entry_assessment: Option<RawRegimeAssessment>,
    current: RawContextPair,
    drift: RawRegimeDrift,
    assessment: RawRegimeAssessment,
) -> Result<(), String> {
    projected.entry_signal = project_context(entry.signal_provider)?;
    projected.entry_canonical = project_context(entry.canonical_regime)?;
    apply_open_entry_assessment(projected, entry_assessment);
    projected.current_signal = project_context(current.signal_provider)?;
    projected.current_canonical = project_context(current.canonical_regime)?;
    projected.signal_provider_changed = drift.signal_provider_changed;
    projected.canonical_regime_changed = drift.canonical_regime_changed;
    apply_open_assessment(projected, assessment);
    Ok(())
}

fn apply_open_entry_assessment(
    projected: &mut CohortOpenTradeReflection,
    assessment: Option<RawRegimeAssessment>,
) {
    let Some(value) = assessment else {
        projected.entry_structure_stance = "unavailable".into();
        return;
    };
    projected.entry_structure_support_score = value.structure_support_score;
    projected.entry_structure_stance = value.structure_stance;
}

fn apply_open_assessment(
    projected: &mut CohortOpenTradeReflection,
    assessment: RawRegimeAssessment,
) {
    projected.structure_support_score = assessment.structure_support_score;
    projected.structure_stance = assessment.structure_stance;
    projected.component_alignment_score = assessment.component_alignment_score;
    projected.component_stance = assessment.component_stance;
    projected.movement_strength = assessment.movement_strength;
    projected.maximum_hold_context = assessment.maximum_hold_context;
}
