//! Compact exposure warnings shared by all cohort screens.

use crate::app::App;
use crate::backend_cohort::CohortAssetSnapshot;
use crate::backend_cohort_trade_reflections::CohortOpenTradeReflection;
use crate::backend_telemetry::BackendConnectionState;
use crate::cohort_open_hold::{clock_labels, now_ms};

/// Report uncertain exit management without mixing different position identities.
pub(crate) fn warning(app: &App) -> Option<String> {
    let positions: Vec<_> = app
        .backend
        .cohort
        .assets
        .iter()
        .filter(|asset| asset.position_size_signed != 0.0)
        .collect();
    let trades = &app.backend.cohort_checkpoint.open_trade_reflections;
    let management = management_label(app);
    if app
        .backend
        .cohort
        .account
        .as_ref()
        .is_some_and(|a| a.open_position_count != positions.len())
    {
        return Some(format!(
            "POSITION EVIDENCE CONFLICT | {management} | CHECK ACCOUNT"
        ));
    }
    if positions.is_empty() && trades.is_empty() {
        return None;
    }
    if trades.is_empty() {
        return Some(format!(
            "LAST OPEN {} | HOLD DATA MISSING | AGE UNKNOWN | {management}",
            positions[0].symbol
        ));
    }
    if !same_positions(&positions, trades) {
        return Some(format!(
            "POSITION EVIDENCE CONFLICT | {management} | CHECK ACCOUNT"
        ));
    }
    valid_warning(app, trades, management)
}

fn valid_warning(
    app: &App,
    trades: &[CohortOpenTradeReflection],
    management: &str,
) -> Option<String> {
    let now = now_ms();
    let trade = trades.iter().min_by_key(|trade| {
        (
            !clock_labels(&trade.exit_plan, now).attention,
            trade.exit_plan.soft_deadline_timestamp_ms,
        )
    })?;
    let clock = clock_labels(&trade.exit_plan, now);
    let checkpoint = &app.backend.cohort_checkpoint;
    let attention = trades
        .iter()
        .any(|t| clock_labels(&t.exit_plan, now).attention);
    if !attention && management == "POLLING" && checkpoint.available && !checkpoint.stale {
        return None;
    }
    let others = if trades.len() > 1 {
        format!(" +{}", trades.len() - 1)
    } else {
        String::new()
    };
    Some(format!(
        "LAST OPEN {}{others} | {} | {} | {management}",
        trade.symbol, clock.evidence, clock.timer
    ))
}

fn same_positions(
    positions: &[&CohortAssetSnapshot],
    trades: &[CohortOpenTradeReflection],
) -> bool {
    positions.len() == trades.len()
        && positions.iter().all(|asset| {
            trades
                .iter()
                .filter(|trade| position_matches(asset, trade))
                .count()
                == 1
        })
}

fn position_matches(asset: &CohortAssetSnapshot, trade: &CohortOpenTradeReflection) -> bool {
    let side = if asset.position_size_signed > 0.0 {
        "long"
    } else {
        "short"
    };
    asset.position_size_signed.is_finite()
        && asset.symbol == trade.symbol
        && trade.side == side
        && asset
            .entry_oid
            .is_some_and(|oid| trade.lifecycle_id == format!("{}:{oid}", asset.symbol))
}

fn management_label(app: &App) -> &'static str {
    if app.backend.cohort_backend_is_stopped() {
        "LOCAL EXITS OFF"
    } else if app.backend.connection != BackendConnectionState::Connected {
        "LOCAL EXITS UNKNOWN"
    } else if app.backend.live_armed != Some(true) {
        "LOCAL EXITS UNARMED"
    } else {
        "POLLING"
    }
}
