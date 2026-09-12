//! Open-position entry-to-current regime drift widget.

use ratatui::{
    Frame,
    layout::Rect,
    text::{Line, Span},
    widgets::Paragraph,
};

use crate::app::App;
use crate::backend_cohort_trade_reflections::{
    CohortOpenTradeReflection, CohortTradeRegimeContext,
};
use crate::cohort_format::fill_time;
use crate::cohort_profit_lock_labels::{compact_profit_lock_label, profit_lock_label};
use crate::cohort_regime_ignored_exit::line as ignored_exit_line;
use crate::cohort_regime_lock::line as profit_lock_line;
use crate::cohort_regime_open_selection::selected_open_indices;
use crate::cohort_regime_path_format::{compact_bps, path_style, signed_bps, unsigned_bps};
use crate::cohort_regime_profit::profit_line;
use crate::cohort_regime_trail::line as trail_line;
use crate::cohort_widgets::panel;

/// Render every open lifecycle with the selected coin first.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let reflections = &app.backend.cohort_checkpoint.open_trade_reflections;
    let selected_symbol = app.selected_cohort_symbol();
    let selected = selected_open_indices(
        reflections.iter().map(|trade| trade.symbol.as_str()),
        selected_symbol,
    );
    let lines = if reflections.is_empty() {
        vec![Line::from(Span::styled(
            "NO OPEN LIFECYCLE REFLECTIONS",
            app.theme.muted,
        ))]
    } else {
        selected
            .iter()
            .copied()
            .flat_map(|index| trade_lines(app, &reflections[index], area.width))
            .collect()
    };
    let title = if let Some(trade) = reflections.get(selected.first().copied().unwrap_or(0)) {
        let clock = crate::cohort_open_hold::clock_labels(
            &trade.exit_plan,
            crate::cohort_open_hold::now_ms(),
        );
        format!(
            " OPEN SNAP // {} // {} ",
            clock.origin.replace(" CLOCK", ""),
            clock.evidence.replace("AGE ", "")
        )
    } else if area.width < 60 {
        " OPEN TRADE // REGIME DRIFT ".into()
    } else {
        " OPEN TRADE // ENTRY → CURRENT REGIME ".into()
    };
    frame.render_widget(Paragraph::new(lines).block(panel(title, app)), area);
}

fn trade_lines<'a>(
    app: &'a App,
    trade: &'a CohortOpenTradeReflection,
    width: u16,
) -> Vec<Line<'a>> {
    if width >= 65 {
        vec![
            trade_line(app, trade),
            assessment_line(app, trade),
            stop_line(app, trade),
            profit_line(app, trade, false),
            profit_lock_line(app, trade),
            target_line(app, trade),
            timer_line(app, trade),
            ignored_exit_line(app, trade, false),
            path_primary_line(app, trade),
            path_risk_line(app, trade),
            extension_path_line(app, trade),
            trail_line(app, trade),
        ]
    } else {
        vec![
            compact_trade_line(app, trade),
            compact_stop_timer_line(app, trade),
            profit_line(app, trade, true),
            target_line(app, trade),
            ignored_exit_line(app, trade, true),
            compact_path_line(app, trade),
            compact_extension_path_line(app, trade),
            profit_lock_line(app, trade),
            trail_line(app, trade),
        ]
    }
}

fn trade_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let hours = trade.holding_time_ms as f64 / 3_600_000.0;
    let side = if trade.side == "long" { "L" } else { "S" };
    let transition = format!(
        "S:{} C:{} → S:{} C:{}",
        state_code(&trade.entry_signal),
        state_code(&trade.entry_canonical),
        state_code(&trade.current_signal),
        state_code(&trade.current_canonical),
    );
    let pnl = trade.active_lifecycle_marked_net_pnl_usd;
    Line::from(vec![
        Span::styled(
            format!("{} {side} {hours:.1}h  ", trade.symbol),
            app.theme.header,
        ),
        Span::styled(transition, drift_style(app, trade)),
        Span::styled(
            format!("  NET {pnl:+.2}"),
            if pnl >= 0.0 {
                app.theme.bull
            } else {
                app.theme.bear
            },
        ),
    ])
}

fn assessment_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let entry_structure = score_text(trade.entry_structure_support_score);
    let structure = score_text(trade.structure_support_score);
    let component = score_text(trade.component_alignment_score);
    let movement = trade
        .movement_strength
        .map_or_else(|| "N/A".into(), |value| format!("{:.0}%", value * 100.0));
    let hold = maximum_hold_label(&trade.maximum_hold_context);
    Line::from(vec![
        Span::raw("  "),
        Span::styled(
            format!(
                "ENTRY {entry_structure} {}",
                stance_label(&trade.entry_structure_stance)
            ),
            assessment_style(app, trade.entry_structure_support_score),
        ),
        Span::styled(
            format!(
                "  |  NOW {structure} {}",
                stance_label(&trade.structure_stance)
            ),
            assessment_style(app, trade.structure_support_score),
        ),
        Span::styled(format!("  |  TMR {hold}"), app.theme.gold),
        Span::styled(
            format!(
                "  |  COMP {component} {}",
                stance_label(&trade.component_stance)
            ),
            assessment_style(app, trade.component_alignment_score),
        ),
        Span::styled(format!("  |  MOVE {movement}"), app.theme.gold),
    ])
}

fn compact_trade_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let hours = trade.holding_time_ms as f64 / 3_600_000.0;
    let side = if trade.side == "long" { "L" } else { "S" };
    let structure = score_text(trade.structure_support_score);
    let entry_structure = score_text(trade.entry_structure_support_score);
    Line::from(Span::styled(
        format!(
            "{} {side} {hours:.1}h N{:+.2} E{entry_structure}→R{structure} {}",
            trade.symbol,
            trade.active_lifecycle_marked_net_pnl_usd,
            compact_opposite_exit_label(&trade.exit_plan.opposite_intent_exit_scope),
        ),
        drift_style(app, trade),
    ))
}

fn stop_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let stop = match (trade.protective_stop_oid, trade.protective_stop_price) {
        (Some(oid), Some(price)) => format!("LAST STOP #{oid} @{price:.2}"),
        _ => "STOP N/A".into(),
    };
    Line::from(Span::styled(stop, app.theme.bull))
}

fn target_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let target = match (
        trade.target_order_oid,
        trade.target_order_price,
        trade.target_directional_distance_bps,
    ) {
        (Some(oid), Some(price), Some(distance)) => {
            format!("TGT#{oid} @{price:.2} {distance:.1}bps")
        }
        _ => "TGT N/A".into(),
    };
    let relation = entry_mechanism_label(&trade.entry_signal);
    Line::from(Span::styled(
        format!("{target} | {relation}"),
        app.theme.gold,
    ))
}

fn entry_mechanism_label(context: &CohortTradeRegimeContext) -> String {
    let breakout = compact_side(context.breakout_side.as_deref());
    let structure = compact_side(context.structural_direction.as_deref());
    let relation = context
        .breakout_side_relation
        .as_deref()
        .unwrap_or("unavailable")
        .to_uppercase();
    format!("BK:{breakout} STR:{structure} {relation}")
}

fn compact_side(side: Option<&str>) -> &'static str {
    match side {
        Some("long") => "L",
        Some("short") => "S",
        _ => "?",
    }
}

fn compact_stop_timer_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let stop = match (trade.protective_stop_oid, trade.protective_stop_price) {
        (Some(oid), Some(price)) => format!("S#{oid}@{price:.2}"),
        _ => "S:N/A".into(),
    };
    let policy = if trade.exit_plan.maximum_hold_policy == "fixed" {
        "FIX"
    } else {
        "SOFT"
    };
    Line::from(Span::styled(
        format!(
            "{stop} {} {} {policy}{}",
            compact_recipe_exit_label(&trade.exit_plan.provider_recipe_exit_policy),
            compact_profit_lock_label(&trade.exit_plan),
            remaining_label(trade.exit_plan.remaining_time_ms, trade.exit_plan.expired),
        ),
        app.theme.bull,
    ))
}

fn compact_recipe_exit_label(policy: &str) -> &'static str {
    if policy == "honor" { "RX:H" } else { "RX:I" }
}

fn timer_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let plan = &trade.exit_plan;
    let timer = if plan.maximum_hold_policy == "extend_while_regime_supported" {
        let hard = plan
            .hard_deadline_timestamp_ms
            .map_or_else(|| "N/A".into(), fill_time);
        if plan.extension_active {
            format!("EXTENDED | HARD {hard}")
        } else {
            format!(
                "SOFT {} | EXTEND IF ALIGNED | HARD {hard}",
                fill_time(plan.soft_deadline_timestamp_ms)
            )
        }
    } else {
        format!("FIXED DUE {}", fill_time(plan.deadline_timestamp_ms))
    };
    Line::from(Span::styled(
        format!(
            "{timer} | {} | {} | SNAP LEFT {} | {} | {}",
            recipe_exit_label(&plan.provider_recipe_exit_policy),
            profit_lock_label(plan),
            remaining_label(plan.remaining_time_ms, plan.expired),
            maximum_hold_label(&trade.maximum_hold_context),
            opposite_exit_label(
                &plan.opposite_intent_exit_scope,
                &plan.opposite_intent_arbitration,
            ),
        ),
        app.theme.gold,
    ))
}

fn recipe_exit_label(policy: &str) -> &'static str {
    if policy == "honor" {
        "RECIPE EXIT HONOR"
    } else {
        "RECIPE EXIT IGNORE"
    }
}

fn compact_opposite_exit_label(scope: &str) -> &'static str {
    if scope == "selected_opposite_from_any_executable_provider_same_symbol" {
        "XPROV"
    } else {
        "X?"
    }
}

fn opposite_exit_label(scope: &str, arbitration: &str) -> &'static str {
    if scope == "selected_opposite_from_any_executable_provider_same_symbol"
        && arbitration == "regime_then_priority"
    {
        "OPP EXIT ANY PROVIDER REGIME>PRIORITY"
    } else {
        "OPP EXIT SCOPE N/A"
    }
}

fn remaining_label(milliseconds: u64, expired: bool) -> String {
    if expired {
        return "EXPIRED".into();
    }
    let seconds = milliseconds as f64 / 1_000.0;
    if seconds >= 3_600.0 {
        format!("{:.1}h", seconds / 3_600.0)
    } else if seconds >= 60.0 {
        format!("{:.0}m", seconds / 60.0)
    } else {
        format!("{seconds:.0}s")
    }
}

fn path_primary_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let path = &trade.path_since_entry;
    Line::from(Span::styled(
        format!(
            "PATH NOW {} | 1M CANDLE MFE {}",
            signed_bps(path.current_directional_return_bps),
            signed_bps(path.maximum_favorable_excursion_bps),
        ),
        path_style(app, path.status.as_str()),
    ))
}

fn path_risk_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let path = &trade.path_since_entry;
    Line::from(Span::styled(
        format!(
            "GIVE {} | 1M CANDLE MAE {} | BARS {} | {}",
            unsigned_bps(path.peak_giveback_bps),
            unsigned_bps(path.maximum_adverse_excursion_bps),
            path.completed_bars,
            opposition_label(trade),
        ),
        path_style(app, path.status.as_str()),
    ))
}

fn compact_path_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let path = &trade.path_since_entry;
    Line::from(Span::styled(
        format!(
            "N{} CMFE{} CMAE{} G{} {}",
            compact_bps(path.current_directional_return_bps, true),
            compact_bps(path.maximum_favorable_excursion_bps, true),
            compact_bps(path.maximum_adverse_excursion_bps, false),
            compact_bps(path.peak_giveback_bps, false),
            opposition_label(trade),
        ),
        if trade
            .regime_opposition
            .as_ref()
            .is_some_and(|value| value.current_active)
        {
            app.theme.bear
        } else {
            path_style(app, path.status.as_str())
        },
    ))
}

fn extension_path_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let Some(path) = trade.path_since_soft_deadline.as_ref() else {
        return Line::from(Span::styled("POST-SOFT N/A", app.theme.muted));
    };
    let label = if path.status == "observed" {
        format!(
            "POST-SOFT NOW {} | MFE {} | MAE {} | GIVE {} | BARS {}",
            signed_bps(path.current_directional_return_bps),
            unsigned_bps(path.maximum_favorable_excursion_bps),
            unsigned_bps(path.maximum_adverse_excursion_bps),
            unsigned_bps(path.peak_giveback_bps),
            path.completed_bars,
        )
    } else {
        extension_status_label(path)
    };
    Line::from(Span::styled(label, path_style(app, &path.status)))
}

fn compact_extension_path_line<'a>(app: &'a App, trade: &'a CohortOpenTradeReflection) -> Line<'a> {
    let Some(path) = trade.path_since_soft_deadline.as_ref() else {
        return Line::from(Span::styled("SOFT N/A", app.theme.muted));
    };
    let label = if path.status == "observed" {
        format!(
            "SOFT{} MFE{} MAE{} G{} {}B",
            compact_bps(path.current_directional_return_bps, true),
            compact_bps(path.maximum_favorable_excursion_bps, false),
            compact_bps(path.maximum_adverse_excursion_bps, false),
            compact_bps(path.peak_giveback_bps, false),
            path.completed_bars,
        )
    } else {
        extension_status_label(path)
    };
    Line::from(Span::styled(label, path_style(app, &path.status)))
}

fn extension_status_label(
    path: &crate::backend_cohort_trade_reflections::CohortOpenExtensionPath,
) -> String {
    match path.status.as_str() {
        "pending_soft_deadline" => {
            format!("SOFT PENDING {}", fill_time(path.boundary_timestamp_ms))
        }
        "awaiting_completed_bar" => format!(
            "SOFT{} // AWAITING COMPLETED BAR",
            compact_bps(path.current_directional_return_bps, true)
        ),
        "unavailable_boundary_close" => "SOFT BASELINE UNAVAILABLE".into(),
        _ => "SOFT PATH INVALID".into(),
    }
}

fn opposition_label(trade: &CohortOpenTradeReflection) -> String {
    trade.regime_opposition.as_ref().map_or_else(
        || "OPP N/A".into(),
        |value| {
            format!(
                "OPP {}/{}",
                value.current_consecutive_opposed, value.maximum_consecutive_opposed
            )
        },
    )
}

fn score_text(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |score| format!("{score:+.2}"))
}

fn stance_label(value: &str) -> &'static str {
    match value {
        "directionally_supported" | "aligned_with_position" => "SUPPORT",
        "directionally_opposed" | "opposing_position" => "AGAINST",
        "mixed_or_transition" => "MIXED",
        _ => "N/A",
    }
}

fn maximum_hold_label(value: &str) -> &'static str {
    match value {
        "still_directionally_supported" => "SUPPORT",
        "directionally_opposed" => "OPPOSE",
        "mixed_or_transition" => "MIXED",
        _ => "N/A",
    }
}

fn assessment_style(app: &App, score: Option<f64>) -> ratatui::style::Style {
    match score {
        Some(value) if value >= 0.5 => app.theme.bull,
        Some(value) if value <= -0.5 => app.theme.bear,
        Some(_) => app.theme.gold,
        None => app.theme.muted,
    }
}

fn state_code(context: &CohortTradeRegimeContext) -> &'static str {
    if context.status != "observed" {
        return "NA";
    }
    match context.primary_regime.as_deref() {
        Some("TREND_UP") => "TU",
        Some("TREND_DOWN") => "TD",
        Some("BREAKOUT") => "BK",
        Some("RANGE") => "RG",
        Some("TRANSITION") => "TR",
        _ => "NA",
    }
}

fn drift_style(app: &App, trade: &CohortOpenTradeReflection) -> ratatui::style::Style {
    match (
        trade.signal_provider_changed,
        trade.canonical_regime_changed,
    ) {
        (Some(false), Some(false)) => app.theme.bull,
        (Some(true), Some(true)) => app.theme.gold,
        (Some(_), Some(_)) => app.theme.carry,
        _ => app.theme.muted,
    }
}
