//! Research-detail identity and execution-friction presentation.

use super::*;

pub(super) fn friction_cell<'a>(app: &App, item: &CohortObserverProviderEvidence) -> Cell<'a> {
    let Some(parity) = provider_friction(app, item) else {
        return Cell::from("N/A").style(app.theme.muted);
    };
    let (label, style) = match parity.parity_state.as_str() {
        "runtime_shape_aligned" => ("ALIGNED", app.theme.bull),
        "contract_mismatch" => ("MISMATCH", app.theme.bear),
        _ => ("UNKNOWN", app.theme.gold),
    };
    Cell::from(label).style(style)
}

pub(super) fn provider_friction<'a>(
    app: &'a App,
    item: &CohortObserverProviderEvidence,
) -> Option<&'a CohortProviderFrictionParity> {
    let key = format!("{}|{}", item.strategy_id, item.symbol);
    app.backend
        .cohort_checkpoint
        .friction_parity
        .as_ref()?
        .by_provider_symbol
        .get(&key)
}

pub(super) fn friction_detail<'a>(
    row: &'a CohortProviderFrictionParity,
    app: &App,
) -> Vec<Line<'a>> {
    let mismatch = mismatch_label(row);
    vec![
        Line::from(Span::styled(
            "EXECUTION CONTRACT PARITY // REPORT ONLY",
            app.theme.cyan,
        )),
        Line::from(format!(
            "STATE {} // DIFFERENCES {mismatch}",
            human_token(&row.parity_state)
        )),
        entry_line(row),
        fee_line(row),
        slippage_line(row),
        model_exit_line(row),
        runtime_exit_line(row),
        source_line(row),
    ]
}

fn mismatch_label(row: &CohortProviderFrictionParity) -> String {
    if row.mismatches.is_empty() {
        return "NONE".into();
    }
    row.mismatches
        .iter()
        .map(|item| human_token(item))
        .collect::<Vec<_>>()
        .join(" · ")
}

fn entry_line(row: &CohortProviderFrictionParity) -> Line<'static> {
    Line::from(format!(
        "ENTRY MODEL {} / LIVE {} {}",
        optional_token(row.modeled_entry_liquidity.as_deref()),
        optional_token(row.runtime_entry_liquidity.as_deref()),
        optional_token(row.runtime_entry_order.as_deref()),
    ))
}

fn fee_line(row: &CohortProviderFrictionParity) -> Line<'static> {
    Line::from(format!(
        "FEE MODEL {} / OBS {} / DELTA {}",
        optional_bps(row.modeled_entry_fee_bps),
        optional_bps(row.observed_fee_mean_bps),
        optional_signed_bps(row.fee_mean_minus_modeled_bps),
    ))
}

fn slippage_line(row: &CohortProviderFrictionParity) -> Line<'static> {
    Line::from(format!(
        "SLIP MODEL {} / OBS {} / DELTA {} // ACK {} // FILLS {}",
        optional_bps(row.modeled_entry_slippage_bps),
        optional_bps(row.observed_slippage_mean_bps),
        optional_signed_bps(row.slippage_mean_minus_modeled_bps),
        optional_ms(row.observed_latency_mean_ms),
        row.entry_fills,
    ))
}

fn model_exit_line(row: &CohortProviderFrictionParity) -> Line<'static> {
    Line::from(format!(
        "EXIT MODEL STOP {} HOLD {} TARGET {}",
        row.modeled_stop_description.as_deref().unwrap_or("N/A"),
        row.modeled_hold_description.as_deref().unwrap_or("N/A"),
        row.modeled_target_description.as_deref().unwrap_or("N/A"),
    ))
}

fn runtime_exit_line(row: &CohortProviderFrictionParity) -> Line<'static> {
    Line::from(format!(
        "LIVE STOP {} HOLD {} TARGET {} RECIPE EXIT {}",
        row.runtime_stop_description.as_deref().unwrap_or("N/A"),
        row.runtime_hold_description.as_deref().unwrap_or("N/A"),
        row.runtime_target_description.as_deref().unwrap_or("N/A"),
        row.runtime_provider_recipe_exit_policy.to_uppercase(),
    ))
}

fn source_line(row: &CohortProviderFrictionParity) -> Line<'static> {
    Line::from(format!(
        "MODEL SOURCE {} // RUNTIME SOURCE {}",
        row.modeled_evidence_source.as_deref().unwrap_or("N/A"),
        optional_token(row.runtime_contract_source.as_deref()),
    ))
}

fn optional_token(value: Option<&str>) -> String {
    value.map_or_else(|| "N/A".into(), human_token)
}

fn optional_bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.2}bps"))
}

fn optional_signed_bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.2}bps"))
}

fn optional_ms(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.0}ms"))
}

pub(super) fn detail_identity<'a>(
    item: &'a CohortObserverProviderEvidence,
    app: &App,
) -> Vec<Line<'a>> {
    let mut lines = vec![
        identity_title(item, app),
        Line::from(provider_identity_label(&item.strategy_id)),
    ];
    lines.push(Line::from(format!(
        "EVALUATIONS {}  //  FIRED {}  //  READINESS {}",
        item.readiness_evaluations,
        item.eligible_signals,
        item.readiness_fraction
            .map_or_else(|| "N/A".into(), |value| format!("{:.1}%", value * 100.0)),
    )));
    lines.push(Line::from(format!(
        "LATEST REASON {}  //  BLOCKERS {}",
        item.latest_reason.as_deref().unwrap_or("N/A"),
        blocker_label(item),
    )));
    lines.extend(scorecard_lines(item, app));
    lines
}

fn identity_title<'a>(item: &'a CohortObserverProviderEvidence, app: &App) -> Line<'a> {
    Line::from(vec![
        Span::styled(provider_alias(&item.strategy_id), app.theme.title),
        Span::raw(format!(
            "  //  {}  //  {}",
            item.symbol,
            item.latest_side.as_deref().unwrap_or("N/A").to_uppercase()
        )),
    ])
}

fn blocker_label(item: &CohortObserverProviderEvidence) -> String {
    if item.latest_blockers.is_empty() {
        return "NONE".into();
    }
    item.latest_blockers
        .iter()
        .map(|value| human_token(value))
        .collect::<Vec<_>>()
        .join(" · ")
}
