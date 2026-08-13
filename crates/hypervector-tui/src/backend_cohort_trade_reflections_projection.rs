//! Collection-level trade-reflection projection and context validation.

use super::*;

pub(crate) fn provider_contract_outcome_count(
    evidence: Option<&TradeReflectionEvidence>,
) -> Result<Option<usize>, String> {
    project_outcome_count(evidence.and_then(|value| value.provider_contract_history.as_ref()))
}

pub(crate) fn project_trade_reflections(
    evidence: Option<TradeReflectionEvidence>,
    expected_closed_trades: usize,
) -> Result<ProjectedTradeReflections, String> {
    let Some(value) = evidence else {
        return Ok((None, Vec::new(), Vec::new(), None, None));
    };
    validate_contract(&value.contract)?;
    if value.closed_trades != value.trades.len() || value.closed_trades != expected_closed_trades {
        return Err("trade-reflection count disagrees with execution evidence".into());
    }
    let projected = value
        .trades
        .into_iter()
        .map(project_trade)
        .collect::<Result<Vec<_>, _>>()?;
    let timer = project_timer_context(value.maximum_hold_context_journal, expected_closed_trades)?;
    let performance = project_trade_performance(value.performance, expected_closed_trades)?;
    let all_time = project_all_time_reflections(value.all_time_live, &projected, &performance)?;
    Ok((
        Some(value.context_coverage.complete),
        projected,
        all_time,
        timer,
        performance,
    ))
}

fn project_all_time_reflections(
    evidence: Option<AllTimeTradeReflectionEvidence>,
    compatible: &[CohortTradeReflection],
    performance: &Option<CohortTradePerformance>,
) -> Result<Vec<CohortTradeReflection>, String> {
    let Some(value) = evidence else {
        return Ok(Vec::new());
    };
    if value.scope != "all_live_history" || value.closed_trades != value.trades.len() {
        return Err("all-time live trade-reflection evidence is inconsistent".into());
    }
    let projected = value
        .trades
        .into_iter()
        .map(project_trade)
        .collect::<Result<Vec<_>, _>>()?;
    let all_time_count = performance
        .as_ref()
        .and_then(|summary| summary.all_time_live.as_ref())
        .map(|summary| summary.total.closed_trades);
    if all_time_count != Some(projected.len()) || !contains_compatible(&projected, compatible) {
        return Err(
            "all-time live reflections disagree with performance or compatible history".into(),
        );
    }
    Ok(projected)
}

fn contains_compatible(
    all_time: &[CohortTradeReflection],
    compatible: &[CohortTradeReflection],
) -> bool {
    let identities = all_time
        .iter()
        .map(|trade| trade.lifecycle_id.as_str())
        .collect::<HashSet<_>>();
    identities.len() == all_time.len()
        && compatible
            .iter()
            .all(|trade| identities.contains(trade.lifecycle_id.as_str()))
}

pub(crate) fn project_open_trade_reflections(
    evidence: Option<OpenTradeReflectionEvidence>,
    expected_open_lifecycles: Option<usize>,
) -> Result<Vec<CohortOpenTradeReflection>, String> {
    let Some(value) = evidence else {
        return Ok(Vec::new());
    };
    validate_contract(&value.contract)?;
    if value.open_lifecycles != value.trades.len()
        || expected_open_lifecycles.is_some_and(|count| count != value.open_lifecycles)
    {
        return Err("open-trade reflection count disagrees with execution evidence".into());
    }
    value.trades.into_iter().map(project_open_trade).collect()
}

pub(super) fn validate_identity(raw: &RawTradeReflection) -> Result<(), String> {
    let invalid = raw.lifecycle_id.trim().is_empty()
        || raw.source_run_id.trim().is_empty()
        || raw
            .source_profile_fingerprint
            .as_ref()
            .is_some_and(|value| value.trim().is_empty())
        || raw.symbol.trim().is_empty()
        || raw.strategy_id.trim().is_empty()
        || raw
            .exit_controller_strategy_id
            .as_ref()
            .is_some_and(|value| value.trim().is_empty())
        || !matches!(raw.side.as_str(), "long" | "short")
        || !raw.net_pnl_usd.is_finite();
    if invalid {
        return Err("trade-reflection lifecycle identity is invalid".into());
    }
    Ok(())
}

pub(super) fn validate_open_identity(raw: &RawOpenTradeReflection) -> Result<(), String> {
    let economics = &raw.marked_economics;
    let invalid = raw.lifecycle_id.trim().is_empty()
        || raw.source_run_id.trim().is_empty()
        || raw.symbol.trim().is_empty()
        || raw.strategy_id.trim().is_empty()
        || !matches!(raw.side.as_str(), "long" | "short")
        || !economics.mark_price.is_finite()
        || economics.mark_price <= 0.0
        || !economics.active_lifecycle_marked_net_pnl_usd.is_finite();
    if invalid {
        return Err("open-trade reflection lifecycle identity is invalid".into());
    }
    Ok(())
}

pub(super) fn project_context(raw: RawRegimeContext) -> Result<CohortTradeRegimeContext, String> {
    if !matches!(raw.status.as_str(), "observed" | "unavailable") {
        return Err("trade-reflection regime context status is invalid".into());
    }
    if raw
        .confidence
        .is_some_and(|value| !value.is_finite() || !(0.0..=1.0).contains(&value))
    {
        return Err("trade-reflection regime confidence is invalid".into());
    }
    let entry_mechanism = project_entry_mechanism(raw.readiness)?;
    Ok(CohortTradeRegimeContext {
        status: raw.status,
        primary_regime: raw.primary_regime,
        state_1m: raw.state_1m,
        state_5m: raw.state_5m,
        context_15m: raw.context_15m,
        confidence: raw.confidence,
        breakout_side: entry_mechanism.0,
        structural_direction: entry_mechanism.1,
        breakout_side_relation: entry_mechanism.2,
    })
}

type EntryMechanism = (Option<String>, Option<String>, Option<String>);

fn project_entry_mechanism(
    readiness: Option<RawRegimeReadiness>,
) -> Result<EntryMechanism, String> {
    let Some(metrics) = readiness.and_then(|value| value.metrics) else {
        return Ok((None, None, None));
    };
    validate_optional_side(metrics.breakout_side.as_deref())?;
    validate_optional_side(metrics.structural_direction.as_deref())?;
    validate_relation(
        metrics.breakout_side.as_deref(),
        metrics.structural_direction.as_deref(),
        metrics.breakout_side_relation.as_deref(),
    )?;
    Ok((
        metrics.breakout_side,
        metrics.structural_direction,
        metrics.breakout_side_relation,
    ))
}

fn validate_optional_side(side: Option<&str>) -> Result<(), String> {
    if side.is_some_and(|value| !matches!(value, "long" | "short")) {
        return Err("trade-reflection entry mechanism side is invalid".into());
    }
    Ok(())
}

fn validate_relation(
    breakout: Option<&str>,
    structure: Option<&str>,
    relation: Option<&str>,
) -> Result<(), String> {
    match relation {
        None | Some("unavailable") => Ok(()),
        Some("aligned") if breakout.is_some() && breakout == structure => Ok(()),
        Some("opposed") if breakout.is_some() && structure.is_some() && breakout != structure => {
            Ok(())
        }
        _ => Err("trade-reflection entry mechanism relation is invalid".into()),
    }
}
