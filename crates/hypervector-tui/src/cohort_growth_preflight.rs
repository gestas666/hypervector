//! Read-only growth-profile sizing and venue-friction display.

use ratatui::text::Line;

use crate::app::App;
use crate::backend_growth_preflight::{GrowthPreflightAssetTelemetry, GrowthPreflightTelemetry};
use crate::cohort_format::money;

/// Render identity-bound $5k sizing evidence without implying live authority.
pub(crate) fn growth_preflight_lines(app: &App, symbol: &str) -> Vec<Line<'static>> {
    let preflight = &app.backend.growth_preflight;
    if !preflight.configured {
        return Vec::new();
    }
    if !preflight.available {
        return vec![Line::from(format!(
            "SIZING PREFLIGHT UNAVAILABLE // {}",
            preflight
                .issue
                .as_deref()
                .unwrap_or("NO VALIDATED EVIDENCE")
        ))];
    }
    if !matches_staged_identity(app, preflight) {
        return vec![Line::from(
            "SIZING PREFLIGHT IDENTITY MISMATCH // NOT APPLIED TO STAGED PROFILE",
        )];
    }
    vec![portfolio_line(preflight), asset_line(preflight, symbol)]
}

fn matches_staged_identity(app: &App, preflight: &GrowthPreflightTelemetry) -> bool {
    let Some(generation) = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
    else {
        return false;
    };
    preflight
        .candidate_profile_fingerprint
        .as_deref()
        .is_some_and(|value| value == generation.current_profile_fingerprint)
}

fn portfolio_line(preflight: &GrowthPreflightTelemetry) -> Line<'static> {
    let status = if preflight.stale {
        "STALE"
    } else if preflight.technically_ready_for_profile_transition == Some(true) {
        "READY"
    } else {
        "BLOCKED"
    };
    let reference = preflight
        .sizing_reference_equity_usd
        .map_or_else(|| "N/A".into(), reference_label);
    let slots = preflight
        .maximum_positions
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let margin = preflight
        .maximum_configured_margin_fraction
        .map_or_else(|| "N/A".into(), |value| format!("{:.1}%", value * 100.0));
    let blockers = if preflight.transition_blocking_assets.is_empty() {
        "NONE".into()
    } else {
        preflight.transition_blocking_assets.join(",")
    };
    Line::from(format!(
        "{reference} PREFLIGHT {status} // {slots} SLOTS // MAX MARGIN {margin} // BLOCKERS {blockers}"
    ))
}

fn reference_label(value: f64) -> String {
    if value >= 1_000.0 && value % 1_000.0 == 0.0 {
        return format!("${:.0}K", value / 1_000.0);
    }
    money(value)
}

fn asset_line(preflight: &GrowthPreflightTelemetry, symbol: &str) -> Line<'static> {
    let Some(asset) = preflight.assets.iter().find(|asset| asset.symbol == symbol) else {
        return Line::from(format!(
            "SIZING ASSET {symbol} // NOT INCLUDED IN CANDIDATE ROSTER"
        ));
    };
    Line::from(format!(
        "{} {:.1}% @ {:.1}x // {} → {} // FEE {} // L2 BUY {} / SELL {}bps",
        asset.symbol,
        asset.margin_fraction * 100.0,
        asset.leverage,
        money(asset.planned_margin_usd),
        money(asset.planned_notional_usd),
        fee_label(asset),
        cost_label(asset.buy_visible_cost_bps),
        cost_label(asset.sell_visible_cost_bps),
    ))
}

fn fee_label(asset: &GrowthPreflightAssetTelemetry) -> String {
    asset.one_way_taker_fee_bps.map_or_else(
        || asset.effective_fee_status.to_uppercase(),
        |value| format!("{value:.2}bps"),
    )
}

fn cost_label(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |cost| format!("{cost:.2}"))
}
