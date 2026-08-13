//! Labels and compact context text for frozen forward challengers.

use crate::backend_cohort_forward_challenger::{
    CohortForwardOneBlockerChallenger, CohortForwardPayoffGeometry,
};
use crate::backend_cohort_forward_entry_context::{
    CohortForwardContext15mSummary, CohortForwardEntryContextSummary,
};

pub(crate) fn experiment_title(forward: &CohortForwardOneBlockerChallenger) -> String {
    let (symbol, candidate) = identity(forward);
    title(symbol, candidate, forward.target_proxy_bps.is_some())
}

pub(crate) fn title(symbol: &str, candidate: &str, has_target: bool) -> String {
    match candidate {
        "btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1" => {
            "FROZEN FWD BTC HULK FLOW60".into()
        }
        "sol_aligned_range_relaxed_fixed60_bidirectional_v1" => "FROZEN FWD SOL ALIGN60".into(),
        "hype_range_absorption_fixed60_bidirectional_v1" => "FROZEN FWD HYPE ABSORB60".into(),
        "hype_hulk_squeeze_relaxed_fixed60_bidirectional_v1" => "FROZEN FWD HYPE HULK SQZ60".into(),
        "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1" => {
            "FROZEN FWD HYPE BK ALIGN60".into()
        }
        "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1" => {
            "FROZEN FWD SOL BK ALIGN60".into()
        }
        _ if has_target => format!("FROZEN FWD {symbol} T20+60"),
        _ if symbol == "HYPE" => "FROZEN FWD HYPE 60+15".into(),
        _ => format!("FROZEN FWD {symbol} FIXED60"),
    }
}

pub(crate) fn experiment_detail_title(forward: &CohortForwardOneBlockerChallenger) -> String {
    let (symbol, candidate) = identity(forward);
    detail_title(symbol, candidate, forward.target_proxy_bps.is_some())
}

pub(crate) fn detail_title(symbol: &str, candidate: &str, has_target: bool) -> String {
    match candidate {
        "btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1" => {
            "FROZEN BTC HULK MONEY-FLOW RELAXATION 60M".into()
        }
        "sol_aligned_range_relaxed_fixed60_bidirectional_v1" => {
            "FROZEN SOL ALIGNED-BOOK RANGE RELAXATION 60M".into()
        }
        "hype_range_absorption_fixed60_bidirectional_v1" => {
            "FROZEN HYPE OPPOSED-BOOK RANGE ABSORPTION 60M".into()
        }
        "hype_hulk_squeeze_relaxed_fixed60_bidirectional_v1" => {
            "FROZEN HYPE HULK SQUEEZE-RELAXED FIXED 60M".into()
        }
        "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1" => {
            "FROZEN HYPE ALIGNED-BOOK BREAKOUT RELAXATION 60M".into()
        }
        "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1" => {
            "FROZEN SOL ALIGNED-BOOK BREAKOUT RELAXATION 60M".into()
        }
        _ if has_target => "FROZEN POST-CUTOFF T20 + 60M FALLBACK".into(),
        _ if symbol == "HYPE" => "FROZEN POST-CUTOFF 60M HOLD + 15M BUFFER".into(),
        _ => "FROZEN POST-CUTOFF FIXED 60M OBSERVER".into(),
    }
}

pub(crate) fn payoff_geometry_text(value: &CohortForwardPayoffGeometry) -> String {
    let break_even = value.break_even_target_rate_pct.map_or_else(
        || "B/E TARGET UNDEFINED".into(),
        |rate| format!("B/E TARGET {rate:.1}%"),
    );
    let fallback = if value.fixed_horizon_changes_realized_distribution {
        "60M FALLBACK CHANGES OUTCOMES"
    } else {
        "BINARY BRACKET ONLY"
    };
    format!(
        "BRACKET NET T{:+.1} / S{:+.1}bps // {break_even} // {fallback}",
        value.estimated_target_net_bps, value.estimated_stop_net_bps,
    )
}

pub(crate) fn entry_context_text(value: &CohortForwardEntryContextSummary) -> String {
    format!(
        "5M ENTRY CONTEXT OBS {}/{} // ALIGNED N{} {:+.1} // OPPOSED N{} {:+.1} // NEUTRAL N{} {:+.1}bps",
        value.state_5m_observed,
        value.state_5m_observed + value.state_5m_missing,
        value.aligned.resolved,
        value.aligned.total_net_return_bps,
        value.opposed.resolved,
        value.opposed.total_net_return_bps,
        value.neutral.resolved,
        value.neutral.total_net_return_bps,
    )
}

pub(crate) fn context_15m_text(value: &CohortForwardContext15mSummary) -> String {
    format!(
        "15M CONTEXT OBS {}/{} // ALIGNED N{} {:+.1} // OPPOSED N{} {:+.1} // NEUTRAL N{} {:+.1}bps // REPORT ONLY",
        value.context_15m_observed,
        value.context_15m_observed + value.context_15m_missing,
        value.aligned.resolved,
        value.aligned.total_net_return_bps,
        value.opposed.resolved,
        value.opposed.total_net_return_bps,
        value.neutral.resolved,
        value.neutral.total_net_return_bps,
    )
}

fn identity(forward: &CohortForwardOneBlockerChallenger) -> (&str, &str) {
    forward
        .portfolio_journal
        .as_ref()
        .map_or(("UNKNOWN", ""), |journal| {
            (
                journal.symbol.as_str(),
                journal.candidate_strategy_id.as_str(),
            )
        })
}
