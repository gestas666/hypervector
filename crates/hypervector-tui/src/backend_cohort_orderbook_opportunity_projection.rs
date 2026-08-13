//! Validation and projection for order-book opportunity evidence.

use super::*;

pub(crate) fn project_provider_orderbook(
    raw: Option<&ObserverProviderOrderbookRaw>,
    pressure_clock: Option<&ObserverProviderPressureClockRaw>,
    signal_context: Option<&ObserverProviderSignalContextRaw>,
) -> Result<Option<CohortProviderOrderbookOpportunity>, String> {
    if raw.is_none() && pressure_clock.is_none() && signal_context.is_none() {
        return Ok(None);
    }
    let mut by_blocker = BTreeMap::new();
    if let Some(value) = raw {
        for (blocker, group) in &value.by_blocker {
            if blocker.trim().is_empty() {
                return Err("order-book opportunity blocker must be non-empty".into());
            }
            let mut by_side = BTreeMap::new();
            for (side, evidence) in &group.by_side {
                if !matches!(side.as_str(), "long" | "short") {
                    return Err("order-book opportunity side must be long or short".into());
                }
                by_side.insert(side.clone(), project_side(evidence)?);
            }
            by_blocker.insert(blocker.clone(), CohortOrderbookBlocker { by_side });
        }
    }
    Ok(Some(CohortProviderOrderbookOpportunity {
        by_blocker,
        pressure_clock: pressure_clock.map(project_pressure_clock).transpose()?,
        eligible_signal_context: signal_context.map(project_signal_context).transpose()?,
    }))
}

fn project_signal_context(
    raw: &ObserverProviderSignalContextRaw,
) -> Result<CohortEligibleSignalContext, String> {
    let pressure_stance = project_stance_counts(&raw.pressure_stance, raw.eligible_signals)?;
    let state_5m_stance = project_stance_counts(&raw.state_5m_stance, raw.eligible_signals)?;
    let context_15m_stance = project_stance_counts(&raw.context_15m_stance, raw.eligible_signals)?;
    Ok(CohortEligibleSignalContext {
        eligible_signals: raw.eligible_signals,
        pressure_stance,
        state_5m_stance,
        context_15m_stance,
        executable_bbo_markouts: raw
            .executable_bbo_markouts
            .as_ref()
            .map(project_eligible_bbo_markouts)
            .transpose()?,
    })
}

fn project_stance_counts(
    raw: &ObserverSignalStanceCountsRaw,
    expected: usize,
) -> Result<CohortSignalStanceCounts, String> {
    let total = raw
        .aligned
        .checked_add(raw.neutral)
        .and_then(|value| value.checked_add(raw.opposed))
        .and_then(|value| value.checked_add(raw.unavailable))
        .ok_or("eligible-signal stance count overflow")?;
    if total != expected {
        return Err("eligible-signal stance counts do not reconcile".into());
    }
    Ok(CohortSignalStanceCounts {
        aligned: raw.aligned,
        neutral: raw.neutral,
        opposed: raw.opposed,
        unavailable: raw.unavailable,
    })
}

pub(crate) fn validate_eligible_signal_context(
    raw: &ObserverEligibleSignalContextRaw,
    provider_keys: &BTreeSet<String>,
) -> Result<(), String> {
    let contract = &raw.contract;
    if !contract.report_only
        || contract.execution_authority != "none"
        || !contract.signals_are_annotations
        || contract.routing_or_fill_claimed
        || contract.thresholds_selected
        || contract.signal_eligibility_changed
    {
        return Err("eligible-signal context violates its report-only contract".into());
    }
    validate_signal_coverage(raw)?;
    let mut provider_total = 0_usize;
    for (key, value) in &raw.by_provider_symbol {
        if !provider_keys.contains(key) {
            return Err("eligible-signal provider is absent from the provider journal".into());
        }
        project_signal_context(value)?;
        provider_total = provider_total
            .checked_add(value.eligible_signals)
            .ok_or("eligible-signal provider count overflow")?;
    }
    if provider_total != raw.coverage.eligible_signals {
        return Err("eligible-signal provider totals disagree with coverage".into());
    }
    Ok(())
}

fn validate_signal_coverage(raw: &ObserverEligibleSignalContextRaw) -> Result<(), String> {
    let book_total = raw
        .coverage
        .book_matched
        .checked_add(raw.coverage.book_stale)
        .and_then(|value| value.checked_add(raw.coverage.book_missing))
        .ok_or("eligible-signal book coverage count overflow")?;
    if book_total != raw.coverage.eligible_signals {
        return Err("eligible-signal book coverage counts do not reconcile".into());
    }
    Ok(())
}

fn project_pressure_clock(
    raw: &ObserverProviderPressureClockRaw,
) -> Result<CohortProviderPressureClock, String> {
    if raw.causal_book_available + raw.book_absent_or_stale != raw.pressure_unavailable_evaluations
    {
        return Err("provider pressure-clock coverage counts do not reconcile".into());
    }
    Ok(CohortProviderPressureClock {
        pressure_unavailable_evaluations: raw.pressure_unavailable_evaluations,
        causal_book_available: raw.causal_book_available,
        book_absent_or_stale: raw.book_absent_or_stale,
    })
}

pub(crate) fn validate_pressure_clock(
    raw: &ObserverOrderbookOpportunityRaw,
    provider_keys: &BTreeSet<String>,
) -> Result<(), String> {
    let Some(clock) = &raw.provider_pressure_clock else {
        return Ok(());
    };
    let expected = [
        clock.pressure_unavailable_evaluations,
        clock.causal_book_available,
        clock.book_absent_or_stale,
    ];
    let totals = clock
        .by_provider_symbol
        .iter()
        .try_fold([0_usize; 3], |totals, (key, value)| {
            accumulate_pressure(totals, key, value, provider_keys)
        })?;
    if totals != expected {
        return Err("pressure-clock totals disagree with provider rows".into());
    }
    Ok(())
}

fn accumulate_pressure(
    totals: [usize; 3],
    key: &str,
    value: &ObserverProviderPressureClockRaw,
    provider_keys: &BTreeSet<String>,
) -> Result<[usize; 3], String> {
    if !provider_keys.contains(key) {
        return Err("pressure-clock provider is absent from the provider journal".into());
    }
    project_pressure_clock(value)?;
    Ok([
        totals[0]
            .checked_add(value.pressure_unavailable_evaluations)
            .ok_or("pressure-clock coverage count overflow")?,
        totals[1]
            .checked_add(value.causal_book_available)
            .ok_or("pressure-clock coverage count overflow")?,
        totals[2]
            .checked_add(value.book_absent_or_stale)
            .ok_or("pressure-clock coverage count overflow")?,
    ])
}

fn project_side(raw: &ObserverOrderbookSideRaw) -> Result<CohortOrderbookSide, String> {
    let mut horizons = BTreeMap::new();
    for (label, evidence) in &raw.horizons {
        let horizon = horizon(label)?;
        let aligned = project_group(&evidence.aligned, true)?;
        let opposed = project_group(&evidence.opposed, false)?;
        if aligned.paths + opposed.paths != evidence.independent_resolved {
            return Err("order-book path groups disagree with independent count".into());
        }
        horizons.insert(
            horizon,
            CohortOrderbookHorizon {
                independent_resolved: evidence.independent_resolved,
                aligned,
                opposed,
            },
        );
    }
    Ok(CohortOrderbookSide { horizons })
}

fn horizon(label: &str) -> Result<u16, String> {
    let value = label
        .parse::<u16>()
        .map_err(|_| "order-book horizon must be positive minutes".to_string())?;
    if value == 0 {
        return Err("order-book horizon must be positive minutes".into());
    }
    Ok(value)
}

fn project_group(
    raw: &ObserverOrderbookGroupRaw,
    aligned: bool,
) -> Result<CohortOrderbookGroup, String> {
    validate_group_means(raw, aligned)?;
    let capture = project_opportunity_capture(Some(&raw.opportunity_capture), raw.paths)?
        .ok_or("order-book path group is missing capture evidence")?;
    Ok(CohortOrderbookGroup {
        paths: raw.paths,
        mean_directional_opi: raw.mean_directional_opi,
        mean_spread_bps: raw.mean_spread_bps,
        opportunity_capture: capture,
    })
}

fn validate_group_means(raw: &ObserverOrderbookGroupRaw, aligned: bool) -> Result<(), String> {
    if raw.paths == 0 {
        if raw.mean_directional_opi.is_some() || raw.mean_spread_bps.is_some() {
            return Err("empty order-book path group cannot carry means".into());
        }
        return Ok(());
    }
    let opi = raw
        .mean_directional_opi
        .filter(|value| value.is_finite())
        .ok_or("order-book path group requires finite OPI")?;
    let spread = raw
        .mean_spread_bps
        .filter(|value| value.is_finite() && *value >= 0.0)
        .ok_or("order-book path group requires nonnegative spread")?;
    if (aligned && opi <= 0.0) || (!aligned && opi > 0.0) || !spread.is_finite() {
        return Err("order-book path group contradicts its OPI alignment".into());
    }
    Ok(())
}
