//! Latest closed-trade regime reflection widget for the regime cockpit.

use ratatui::{
    Frame,
    layout::Rect,
    style::Style,
    text::{Line, Span},
    widgets::Paragraph,
};

use crate::app::App;
use crate::backend_cohort_trade_reflections::{
    CohortTradeExitPath, CohortTradeReflection, CohortTradeRegimeContext,
};
use crate::cohort_widgets::panel;

/// Render the latest report-only lifecycle regime reflection.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let lines = app
        .backend
        .cohort_checkpoint
        .user_trade_reflections()
        .last()
        .map_or_else(
            || unavailable_lines(app),
            |trade| reflection_lines(app, trade, area.width < 55),
        );
    frame.render_widget(
        Paragraph::new(lines).block(panel(" LAST CLOSED // REGIME REFLECTION ", app)),
        area,
    );
}

fn unavailable_lines<'a>(app: &'a App) -> Vec<Line<'a>> {
    vec![
        Line::from(Span::styled("AWAITING CLOSED LIFECYCLE", app.theme.muted)),
        Line::from("Entry/exit regime join unavailable"),
        Line::from("Post-exit paths: N/A"),
    ]
}

fn reflection_lines<'a>(
    app: &'a App,
    trade: &'a CohortTradeReflection,
    compact: bool,
) -> Vec<Line<'a>> {
    vec![
        identity_line(app, trade, compact),
        context_line(
            app,
            "ENTRY",
            &trade.entry_signal,
            &trade.entry_canonical,
            trade.entry_structure_support_score,
        ),
        component_line(app, trade),
        context_line(
            app,
            "EXIT ",
            &trade.exit_signal,
            &trade.exit_canonical,
            None,
        ),
        path_line(app, trade, 5),
        path_line(app, trade, 60),
    ]
}

fn component_line<'a>(app: &'a App, trade: &CohortTradeReflection) -> Line<'a> {
    let score = trade.entry_component_alignment_score;
    let score_text = score.map_or_else(|| "N/A".into(), |value| format!("{value:+.2}"));
    let stance = match trade.entry_component_stance.as_str() {
        "aligned_with_position" => "ALIGNED",
        "opposing_position" => "OPPOSED",
        "mixed_or_transition" => "MIXED",
        _ => "UNAVAILABLE",
    };
    Line::from(Span::styled(
        format!("ENTRY COMPONENT {score_text} {stance}"),
        exit_context_style(app, score),
    ))
}

fn identity_line<'a>(app: &'a App, trade: &'a CohortTradeReflection, compact: bool) -> Line<'a> {
    let reason = trade
        .exit_reason
        .as_deref()
        .unwrap_or("unreported")
        .replace('_', " ")
        .to_uppercase();
    if compact {
        return compact_identity_line(app, trade, &reason);
    }
    Line::from(vec![
        Span::styled(
            format!("{} {}", trade.symbol, trade.side.to_uppercase()),
            side_style(app, &trade.side),
        ),
        Span::styled(
            format!("  NET {:+.2}  {reason}", trade.net_pnl_usd),
            pnl_style(app, trade.net_pnl_usd),
        ),
        Span::styled(
            format!("  CTX {}", exit_context_label(trade)),
            exit_context_style(app, trade.exit_structure_support_score),
        ),
        Span::styled(
            if trade.cross_provider_exit {
                "  XPROV"
            } else {
                "  OWN EXIT"
            },
            if trade.cross_provider_exit {
                app.theme.gold
            } else {
                app.theme.muted
            },
        ),
    ])
}

fn compact_identity_line<'a>(
    app: &'a App,
    trade: &'a CohortTradeReflection,
    reason: &str,
) -> Line<'a> {
    let side = if trade.side == "long" { "L" } else { "S" };
    let reason = match reason {
        "MAXIMUM HOLD SECONDS" | "MAXIMUM HOLD" => "MAXH",
        "PROTECTIVE STOP" => "STOP",
        _ => "EXIT",
    };
    let controller = if trade.cross_provider_exit {
        " XPRV"
    } else {
        " OWN"
    };
    Line::from(vec![
        Span::styled(
            format!("{} {side}", trade.symbol),
            side_style(app, &trade.side),
        ),
        Span::styled(
            format!(" {:+.2} {reason}", trade.net_pnl_usd),
            pnl_style(app, trade.net_pnl_usd),
        ),
        Span::styled(
            format!(" C:{}{controller}", compact_context_label(trade)),
            exit_context_style(app, trade.exit_structure_support_score),
        ),
    ])
}

fn compact_context_label(trade: &CohortTradeReflection) -> &'static str {
    match trade.exit_maximum_hold_context.as_str() {
        "still_directionally_supported" => "SUP",
        "directionally_opposed" => "OPP",
        "mixed_or_transition" => "MIX",
        _ => "N/A",
    }
}

fn exit_context_label(trade: &CohortTradeReflection) -> &'static str {
    match trade.exit_maximum_hold_context.as_str() {
        "still_directionally_supported" => "SUPPORT",
        "directionally_opposed" => "OPPOSE",
        "mixed_or_transition" => "MIXED",
        _ => "N/A",
    }
}

fn exit_context_style(app: &App, score: Option<f64>) -> Style {
    match score {
        Some(value) if value >= 0.5 => app.theme.bull,
        Some(value) if value <= -0.5 => app.theme.bear,
        Some(_) => app.theme.gold,
        None => app.theme.muted,
    }
}

fn context_line<'a>(
    app: &'a App,
    label: &'a str,
    signal: &'a CohortTradeRegimeContext,
    canonical: &'a CohortTradeRegimeContext,
    alignment_score: Option<f64>,
) -> Line<'a> {
    let signal_state = context_state(signal);
    let canonical_state = context_state(canonical);
    let mut spans = vec![
        Span::styled(format!("{label} "), app.theme.header),
        Span::styled(format!("S:{signal_state}"), regime_style(app, signal_state)),
        Span::raw(" "),
        Span::styled(
            format!("C:{canonical_state}"),
            regime_style(app, canonical_state),
        ),
    ];
    if let Some(score) = alignment_score {
        spans.push(Span::styled(
            format!(" A{score:+.2}"),
            exit_context_style(app, Some(score)),
        ));
    }
    Line::from(spans)
}

fn path_line<'a>(app: &'a App, trade: &'a CohortTradeReflection, horizon: u16) -> Line<'a> {
    let Some(path) = trade.post_exit_paths.get(&horizon) else {
        return Line::from(Span::styled(
            format!("{horizon}M PATH N/A"),
            app.theme.muted,
        ));
    };
    let (text, style) = path_text(app, horizon, path);
    Line::from(Span::styled(text, style))
}

fn path_text(app: &App, horizon: u16, path: &CohortTradeExitPath) -> (String, Style) {
    if path.status != "resolved" {
        return (
            format!(
                "{horizon}M {}",
                path.status.replace('_', " ").to_uppercase()
            ),
            app.theme.muted,
        );
    }
    let bps = path.directional_close_return_bps.unwrap_or(0.0);
    let interpretation = match path.interpretation.as_deref() {
        Some("continued_original_direction") => "CONTINUED",
        Some("reversed_against_original_direction") => "REVERSED",
        Some("unchanged") => "UNCHANGED",
        _ => "UNRESOLVED",
    };
    let style = if interpretation == "REVERSED" {
        app.theme.bull
    } else if interpretation == "CONTINUED" {
        app.theme.gold
    } else {
        app.theme.muted
    };
    (format!("{horizon}M {bps:+.1}bps {interpretation}"), style)
}

fn context_state(context: &CohortTradeRegimeContext) -> &str {
    if context.status != "observed" {
        return "N/A";
    }
    context.primary_regime.as_deref().unwrap_or("N/A")
}

fn side_style(app: &App, side: &str) -> Style {
    if side == "long" {
        app.theme.bull
    } else {
        app.theme.bear
    }
}

fn pnl_style(app: &App, pnl: f64) -> Style {
    if pnl >= 0.0 {
        app.theme.bull
    } else {
        app.theme.bear
    }
}

fn regime_style(app: &App, state: &str) -> Style {
    match state {
        "TREND_UP" => app.theme.bull,
        "TREND_DOWN" => app.theme.bear,
        "BREAKOUT" => app.theme.cyan,
        "RANGE" => app.theme.coiling,
        "TRANSITION" => app.theme.carry,
        _ => app.theme.muted,
    }
}
