//! Shared visual primitives for the bidirectional cohort cockpit.

use ratatui::{
    Frame,
    layout::Rect,
    style::Style,
    text::Line,
    widgets::{Block, BorderType, Borders, Paragraph},
};

use crate::app::App;
use crate::backend_cohort::CohortAssetSnapshot;
use crate::cohort_profit_lock_labels::plan_profit_lock_label;

pub(crate) const MIN_WIDTH: u16 = 100;
pub(crate) const MIN_HEIGHT: u16 = 28;
pub(crate) const WIDE_WIDTH: u16 = 165;
const HT_BREAKOUT_LEGACY_ID: &str = "hype_breakout_onset_bidirectional_v1";
const HT_BREAKOUT_ID: &str = "ht_breakout_bidirectional_v1";

/// Return the bounded page containing the selected backend item.
pub(crate) fn selected_page(
    total: usize,
    selected: usize,
    page_size: usize,
) -> (std::ops::Range<usize>, usize) {
    if total == 0 || page_size == 0 {
        return (0..0, 0);
    }
    let bounded = selected.min(total - 1);
    let start = (bounded / page_size) * page_size;
    let end = start.saturating_add(page_size).min(total);
    (start..end, bounded - start)
}

/// Format a one-based asset range without implying unavailable rows exist.
pub(crate) fn page_label(range: &std::ops::Range<usize>, total: usize) -> String {
    if range.is_empty() {
        "0-0 / 0".into()
    } else {
        format!("{}-{} / {total}", range.start + 1, range.end)
    }
}

/// Build the rounded, high-contrast panel used throughout the cohort view.
pub(crate) fn panel<'a>(title: impl Into<Line<'a>>, app: &App) -> Block<'a> {
    Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(app.theme.border)
        .title_style(app.theme.title)
}

/// Render an explicit empty or unavailable state instead of an ambiguous gap.
pub(crate) fn render_empty(frame: &mut Frame, app: &App, area: Rect, title: &str, message: &str) {
    frame.render_widget(
        Paragraph::new(message)
            .style(app.theme.muted)
            .centered()
            .block(panel(title, app)),
        area,
    );
}

/// Return a short operator label while retaining exact IDs in audit layouts.
pub(crate) fn provider_alias(strategy_id: &str) -> &str {
    if matches!(strategy_id, HT_BREAKOUT_LEGACY_ID | HT_BREAKOUT_ID) {
        "HT-Breakout"
    } else if strategy_id == "hip3_swing_ha_sp500_spcx_bidirectional_v2" {
        "HIP3 SWING IDX"
    } else if matches!(
        strategy_id,
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2"
            | "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
    ) {
        "HIP3 BK15 IDX"
    } else if strategy_id == "hip3_breakout_pressure_sp500_spcx_bidirectional_v1" {
        "HIP3 BK IDX"
    } else if strategy_id == "hip3_swing_ha_sndk_gold_brent_bidirectional_v1" {
        "HIP3 SWING CMD"
    } else if strategy_id == "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2" {
        "HIP3 BK15 CMD"
    } else if strategy_id == "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1" {
        "HIP3 BK CMD"
    } else if strategy_id == "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1" {
        "SPCX CASH OPEN"
    } else if strategy_id == "hip3_spcx_cash_session_fresh15_long_v4" {
        "SPCX CASH LONG"
    } else if strategy_id == "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3" {
        "SNDK BK15 SHORT"
    } else if strategy_id == "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v4" {
        "SNDK BK15 V4"
    } else if strategy_id == "eth_range_onset_long_dual_mtf_v2" {
        "ETH RANGE LONG"
    } else if strategy_id == "sol_range_onset_short_dual_mtf_v2" {
        "SOL RANGE SHORT"
    } else if strategy_id == "zec_donchian_20_10_atr20_long_v1" {
        "ZEC DONCHIAN L"
    } else if strategy_id == "hourly_band20_reentry_atr20_bidirectional_v1" {
        "HOURLY RECOVERY"
    } else if strategy_id == "hourly_donchian_20_10_atr20_bidirectional_v1" {
        "HOURLY CHANNEL20"
    } else if strategy_id == "hourly_donchian_20_10_atr20_strong_short_v1" {
        "CHANNEL20 STRONG"
    } else if strategy_id == "hourly_donchian_8_4_atr20_bidirectional_v1" {
        "HOURLY CHANNEL8"
    } else if strategy_id == "btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1" {
        "BTC HULK FLOW60"
    } else if strategy_id == "hulk_expansion_short_robust_v3" {
        "BTC HULK SHORT"
    } else if strategy_id == "liquidity_sweep_long_1h_stop60_v1" {
        "BTC SWEEP LONG"
    } else if strategy_id == "liquidity_sweep_long_1h_stop60_target60_v2" {
        "BTC SWEEP 60/60"
    } else if strategy_id.starts_with("hulk_") {
        "HULK EXPANSION"
    } else if strategy_id.starts_with("range_onset_") {
        "RANGE ONSET"
    } else if strategy_id.starts_with("hypervelocity_source_follow_") {
        "HV SOURCE 5M"
    } else if strategy_id == "btc_structural_continuation_fixed60_bidirectional_v1" {
        "BTC STRUCT 60"
    } else if strategy_id == "hype_range_absorption_fixed60_bidirectional_v1" {
        "HYPE ABSORB 60"
    } else if strategy_id == "eth_breakout_precompression_pullback_bidirectional_v1" {
        "ETH BK PULLBACK"
    } else if strategy_id == "hype_breakout_compression_pullback_bidirectional_v1" {
        "HYPE COMPRESSION"
    } else if strategy_id == "hype_breakout_compression_alignment_bidirectional_v2" {
        "HYPE ALIGN"
    } else if strategy_id == "hype_native_breakout_onset_bidirectional_v2" {
        "HYPE NATIVE"
    } else if strategy_id == "hype_breakout_relaxed_target20_60m_bidirectional_v3" {
        "HYPE T20+60"
    } else if strategy_id == "hype_breakout_relaxed_fixed60_matched_bidirectional_v4" {
        "HYPE MATCH 60"
    } else if strategy_id == "hype_breakout_relaxed_60m_bidirectional_v2" {
        "HYPE 60+15"
    } else if strategy_id.starts_with("hype_breakout_relaxed_") {
        "HYPE 60M RELAX"
    } else if strategy_id == "hype_breakout_retest_bidirectional_v2" {
        "BK RETEST V2"
    } else if strategy_id.starts_with("cohort_maximum_hold") {
        "MAX HOLD EXIT"
    } else {
        strategy_id
    }
}

/// Format a provider identity without exposing a legacy alias source to operators.
pub(crate) fn provider_identity_label(strategy_id: &str) -> String {
    if matches!(strategy_id, HT_BREAKOUT_LEGACY_ID | HT_BREAKOUT_ID) {
        format!("OPERATOR PROVIDER  {}", provider_alias(strategy_id))
    } else {
        format!("EXACT PROVIDER ID  {strategy_id}")
    }
}

/// Format venue stop protection directly from backend position and stop facts.
pub(crate) fn protection_label(asset: &CohortAssetSnapshot) -> String {
    if let Some(label) = crate::cohort_protective_progress::protection_override(asset) {
        return label.into();
    }
    match (
        asset.position_side.as_deref(),
        asset.stop_oid,
        asset.target_oid,
    ) {
        (None, _, _) => "FLAT".into(),
        (Some(_), Some(stop), Some(target)) => {
            let ids = format!("S{stop}/T{target}");
            if let Some(price) = asset.target_price {
                let priced = format!("{ids}@{}", compact_price(price));
                if priced.chars().count() <= 20 {
                    priced
                } else {
                    ids
                }
            } else {
                ids
            }
        }
        (Some(_), Some(stop), None) => format!("STOP #{stop}"),
        (Some(_), None, _) => "STOP MISSING".into(),
    }
}

/// Summarize the persisted provider and maximum hold for an open position.
pub(crate) fn execution_plan_label(asset: &CohortAssetSnapshot) -> String {
    if asset.position_side.is_none() {
        return "-".into();
    }
    let Some(plan) = &asset.execution_plan else {
        return "LEGACY PLAN".into();
    };
    let provider = if plan.strategy_id.starts_with("hulk_") {
        "HK"
    } else if plan.strategy_id.starts_with("eth_range_onset_") {
        "ER"
    } else if plan.strategy_id.starts_with("sol_range_onset_") {
        "SR"
    } else if plan.strategy_id.starts_with("zec_donchian_") {
        "ZD"
    } else if plan.strategy_id.starts_with("hip3_spcx_cash_session_") {
        "SC"
    } else if plan.strategy_id.starts_with("range_onset_") {
        "RG"
    } else if plan.strategy_id.starts_with("hypervelocity_source_follow_") {
        "SF"
    } else if matches!(
        plan.strategy_id.as_str(),
        HT_BREAKOUT_LEGACY_ID | HT_BREAKOUT_ID
    ) {
        "HT"
    } else if plan.strategy_id.starts_with("hype_breakout_") {
        "HB"
    } else if plan.strategy_id.starts_with("hip3_swing_ha_") {
        "H3S"
    } else if plan.strategy_id.starts_with("hip3_breakout_pressure_") {
        "H3B"
    } else if plan.strategy_id.starts_with("hip3_spcx_cash_open_") {
        "CO"
    } else {
        "CU"
    };
    let recipe_exit = if plan.provider_recipe_exit_policy == "honor" {
        "H"
    } else {
        "I"
    };
    let profit_lock = if plan.adaptive_exit_policy == "regime_book_profit_retention_v1" {
        "AD".into()
    } else if plan.adaptive_exit_policy == "regime_flip_floor_retention_v2" {
        if plan.breakeven_stop_target == "floor" {
            "AD2F".into()
        } else {
            "AD2".into()
        }
    } else {
        plan_profit_lock_label(
            &plan.profit_lock_policy,
            plan.profit_lock_activation_bps,
            plan.profit_lock_floor_bps,
            plan.profit_lock_giveback_bps,
        )
    };
    let soft_hours = plan.maximum_hold_seconds / 3_600;
    if plan.maximum_hold_policy == "extend_while_regime_supported" {
        return plan.hard_maximum_hold_seconds.map_or_else(
            || format!("{provider}{soft_hours}H?/{recipe_exit}/{profit_lock}"),
            |hard| {
                format!(
                    "{provider}{soft_hours}>{}H/{recipe_exit}/{profit_lock}",
                    hard / 3_600
                )
            },
        );
    }
    format!("{provider}{soft_hours}H/{recipe_exit}/{profit_lock}")
}

fn compact_price(price: f64) -> String {
    if price.abs() >= 1_000.0 {
        format!("{price:.0}")
    } else {
        format!("{price:.2}")
    }
}

/// Style venue stop protection for fast operator recognition.
pub(crate) fn protection_style(asset: &CohortAssetSnapshot, app: &App) -> Style {
    if asset.protective_exit_pending == Some(true)
        || asset.stop_protection.as_deref() == Some("missing")
    {
        return app.theme.gate_blocked;
    }
    match (asset.position_side.as_deref(), asset.stop_oid) {
        (None, _) => app.theme.muted,
        (Some(_), Some(_)) => app.theme.bull,
        (Some(_), None) => app.theme.gate_blocked,
    }
}

/// Style a long, short, or flat position without changing backend state.
pub(crate) fn position_style(asset: &CohortAssetSnapshot, app: &App) -> Style {
    match asset.position_side.as_deref() {
        Some("long") => app.theme.bull,
        Some("short") => app.theme.bear,
        _ => app.theme.muted,
    }
}

/// Return a widget-safe ratio without turning invalid telemetry into measured zero.
pub(crate) fn safe_ratio(numerator: f64, denominator: f64) -> Option<f64> {
    if denominator <= 0.0 || !numerator.is_finite() || !denominator.is_finite() {
        None
    } else {
        Some((numerator / denominator).clamp(0.0, 1.0))
    }
}

#[cfg(test)]
mod tests {
    use super::{execution_plan_label, provider_alias};
    use crate::backend_cohort::CohortAssetSnapshot;

    fn open_btc_hulk_snapshot() -> CohortAssetSnapshot {
        serde_json::from_value(serde_json::json!({
            "symbol": "BTC",
            "state": "OPEN",
            "direction_capability": ["long", "short"],
            "position_size_signed": -0.1,
            "position_side": "short",
            "entry_oid": 1,
            "stop_oid": 2,
            "target_oid": 3,
            "target_price": 75_000.0,
            "execution_plan": {
                "strategy_id": "hulk_expansion_short_robust_v3",
                "entry_liquidity": "taker_ioc",
                "stop_policy": "structural_clamped_bps",
                "target_policy": "reward_risk",
                "maximum_hold_seconds": 86_400,
                "stop_bps": null,
                "minimum_stop_bps": 20.0,
                "maximum_stop_bps": 75.0,
                "target_bps": null,
                "target_r_multiple": 3.0,
                "safety_stop_overlay": false,
                "stop_anchor": 78_000.0,
                "target_anchor": null,
                "maximum_hold_policy": "fixed",
                "hard_maximum_hold_seconds": null,
                "provider_recipe_exit_policy": "ignore",
                "profit_lock_policy": "btc_hulk_delayed_component_floor_v1",
                "profit_lock_activation_bps": null,
                "profit_lock_floor_bps": null,
                "profit_lock_giveback_bps": null
            },
            "last_fault": null,
            "mark_price": 77_000.0,
            "entry_price": 77_000.0,
            "liquidation_price": 80_000.0,
            "liquidation_distance_pct": 3.9,
            "margin_used_usd": 500.0,
            "position_value_usd": 10_000.0,
            "unrealized_pnl_usd": 0.0,
            "leverage": 20,
            "fees_net_usd": 4.32,
            "funding_net_usd": 0.0,
            "realized_pnl_usd": 0.0,
            "fill_count": 1
        }))
        .expect("fixture should deserialize")
    }

    #[test]
    fn execution_plan_shows_named_btc_profit_lock_as_enabled() {
        let label = execution_plan_label(&open_btc_hulk_snapshot());

        assert_eq!(label, "HK24H/I/DCF");
        assert!(label.chars().count() <= 12);
    }

    #[test]
    fn execution_plan_distinguishes_the_venue_floor_raise_target() {
        let mut snapshot = open_btc_hulk_snapshot();
        let plan = snapshot.execution_plan.as_mut().expect("fixture plan");
        plan.profit_lock_policy = "none".into();
        plan.adaptive_exit_policy = "regime_flip_floor_retention_v2".into();
        assert_eq!(plan.breakeven_stop_target, "entry_offset");
        assert_eq!(execution_plan_label(&snapshot), "HK24H/I/AD2");
        let plan = snapshot.execution_plan.as_mut().expect("fixture plan");
        plan.breakeven_stop_target = "floor".into();
        let label = execution_plan_label(&snapshot);
        assert_eq!(label, "HK24H/I/AD2F");
        assert!(label.chars().count() <= 12);
    }

    #[test]
    fn relaxed_hype_provider_has_a_compact_distinct_alias() {
        assert_eq!(
            provider_alias("hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2"),
            "HIP3 BK15 IDX"
        );
        assert_eq!(
            provider_alias("hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"),
            "HIP3 BK15 CMD"
        );
        assert_ne!(
            provider_alias("hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2"),
            provider_alias("hip3_breakout_pressure_sp500_spcx_bidirectional_v1")
        );
        assert_eq!(
            provider_alias("hype_breakout_relaxed_60m_bidirectional_v1"),
            "HYPE 60M RELAX"
        );
        assert_eq!(
            provider_alias("hype_breakout_relaxed_60m_bidirectional_v2"),
            "HYPE 60+15"
        );
        assert_eq!(
            provider_alias("eth_range_onset_long_dual_mtf_v2"),
            "ETH RANGE LONG"
        );
        assert_eq!(
            provider_alias("sol_range_onset_short_dual_mtf_v2"),
            "SOL RANGE SHORT"
        );
        assert_eq!(
            provider_alias("zec_donchian_20_10_atr20_long_v1"),
            "ZEC DONCHIAN L"
        );
        assert_eq!(
            provider_alias("hip3_spcx_cash_session_fresh15_long_v4"),
            "SPCX CASH LONG"
        );
        assert_eq!(
            provider_alias("hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3"),
            "SNDK BK15 SHORT"
        );
        assert_eq!(
            provider_alias("hip3_breakout_pressure_sndk_fresh15s_bidirectional_v4"),
            "SNDK BK15 V4"
        );
        assert_eq!(
            provider_alias("hype_breakout_relaxed_target20_60m_bidirectional_v3"),
            "HYPE T20+60"
        );
        assert_eq!(
            provider_alias("hype_breakout_onset_bidirectional_v1"),
            "HT-Breakout"
        );
        assert_eq!(
            provider_alias("ht_breakout_bidirectional_v1"),
            "HT-Breakout"
        );
        assert_eq!(
            provider_alias("hype_breakout_retest_bidirectional_v2"),
            "BK RETEST V2"
        );
        assert_eq!(
            provider_alias("hype_breakout_relaxed_fixed60_matched_bidirectional_v4"),
            "HYPE MATCH 60"
        );
        assert_eq!(
            provider_alias("btc_structural_continuation_fixed60_bidirectional_v1"),
            "BTC STRUCT 60"
        );
        assert_eq!(
            provider_alias("hype_range_absorption_fixed60_bidirectional_v1"),
            "HYPE ABSORB 60"
        );
        assert_eq!(
            provider_alias("btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1"),
            "BTC HULK FLOW60"
        );
        assert_eq!(
            provider_alias("eth_breakout_precompression_pullback_bidirectional_v1"),
            "ETH BK PULLBACK"
        );
        assert_eq!(
            provider_alias("hype_breakout_compression_pullback_bidirectional_v1"),
            "HYPE COMPRESSION"
        );
        assert_eq!(
            provider_alias("hype_native_breakout_onset_bidirectional_v2"),
            "HYPE NATIVE"
        );
        assert_eq!(
            provider_alias("liquidity_sweep_long_1h_stop60_target60_v2"),
            "BTC SWEEP 60/60"
        );
    }

    #[test]
    fn strong_short_channel_has_a_distinct_alias_within_the_column_budget() {
        let alias = provider_alias("hourly_donchian_20_10_atr20_strong_short_v1");
        assert_eq!(alias, "CHANNEL20 STRONG");
        assert_ne!(
            alias,
            provider_alias("hourly_donchian_20_10_atr20_bidirectional_v1")
        );
        assert!(alias.chars().count() <= 16);
    }
}
