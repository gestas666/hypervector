//! Provider-specific route-authority labels for cohort cockpit views.

use crate::backend_cohort::CohortProvider;

pub(crate) fn provider_route_label(
    providers: &[CohortProvider],
    strategy_id: &str,
    symbol: &str,
    live_armed: Option<bool>,
) -> &'static str {
    let Some(provider) = providers.iter().find(|provider| {
        provider.strategy_id == strategy_id && provider.symbols.iter().any(|value| value == symbol)
    }) else {
        return "UNSCOPED";
    };
    let executable = provider
        .execution_symbols
        .as_ref()
        .is_some_and(|symbols| symbols.iter().any(|value| value == symbol));
    if executable {
        return if live_armed == Some(true) {
            "LIVE EXECUTABLE"
        } else {
            "CANARY EXECUTABLE"
        };
    }
    "OBSERVE ONLY"
}

/// Return the compact authority token used in dense setup tables.
pub(crate) fn provider_route_token(
    providers: &[CohortProvider],
    strategy_id: &str,
    symbol: &str,
    live_armed: Option<bool>,
) -> &'static str {
    match provider_route_label(providers, strategy_id, symbol, live_armed) {
        "LIVE EXECUTABLE" => "LIVE",
        "CANARY EXECUTABLE" => "CANARY",
        "OBSERVE ONLY" => "OBS",
        _ => "N/A",
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{provider_route_label, provider_route_token};
    use crate::backend_cohort::CohortProvider;

    fn providers() -> Vec<CohortProvider> {
        serde_json::from_value(json!([
            {
                "strategy_id": "eth_pullback",
                "symbols": ["ETH"],
                "sides": ["long", "short"],
                "priority": 10,
                "timeframe": "5m",
                "maximum_entry_delay_seconds": 60,
                "execution_symbols": ["ETH"]
            },
            {
                "strategy_id": "range_onset",
                "symbols": ["BTC", "SOL", "HYPE"],
                "sides": ["long", "short"],
                "priority": 20,
                "timeframe": "1h",
                "maximum_entry_delay_seconds": 60,
                "execution_symbols": ["SOL"]
            }
        ]))
        .expect("provider fixture")
    }

    #[test]
    fn distinguishes_live_canary_observe_and_unscoped_provider_routes() {
        let providers = providers();

        assert_eq!(
            provider_route_label(&providers, "eth_pullback", "ETH", Some(true)),
            "LIVE EXECUTABLE"
        );
        assert_eq!(
            provider_route_label(&providers, "range_onset", "SOL", Some(false)),
            "CANARY EXECUTABLE"
        );
        assert_eq!(
            provider_route_label(&providers, "range_onset", "BTC", Some(true)),
            "OBSERVE ONLY"
        );
        assert_eq!(
            provider_route_label(&providers, "eth_pullback", "BTC", Some(true)),
            "UNSCOPED"
        );
        assert_eq!(
            provider_route_token(&providers, "eth_pullback", "ETH", Some(true)),
            "LIVE"
        );
        assert_eq!(
            provider_route_token(&providers, "range_onset", "SOL", Some(false)),
            "CANARY"
        );
        assert_eq!(
            provider_route_token(&providers, "range_onset", "BTC", Some(true)),
            "OBS"
        );
    }
}
