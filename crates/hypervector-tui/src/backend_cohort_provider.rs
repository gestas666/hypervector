//! Fail-closed semantic validation for cohort provider declarations.

use crate::backend_cohort::CohortProvider;

const SOURCE_FOLLOW_ID: &str = "hypervelocity_source_follow_bidirectional_5m_v1";
const HYPE_BREAKOUT_ID: &str = "hype_breakout_onset_bidirectional_v1";
const BTC_STRUCTURAL_ID: &str = "btc_structural_continuation_fixed60_bidirectional_v1";

/// Validate specialized provider source contracts without imposing authority policy.
pub(crate) fn validate_specialized_providers(providers: &[CohortProvider]) -> Result<(), String> {
    validate_source_follow_provider(providers)?;
    validate_hype_breakout_provider(providers)?;
    validate_btc_structural_provider(providers)?;
    validate_hype_relaxed_providers(providers)
}

/// Validate the measured source observer's immutable no-execution contract.
pub(crate) fn validate_source_follow_provider(providers: &[CohortProvider]) -> Result<(), String> {
    let Some(provider) = providers
        .iter()
        .find(|provider| provider.strategy_id == SOURCE_FOLLOW_ID)
    else {
        return Ok(());
    };
    let profile_present = provider
        .source_profile
        .as_deref()
        .is_some_and(|value| !value.trim().is_empty());
    if provider.symbols != ["BTC"] || provider.timeframe != "5m" || !profile_present {
        return Err("cohort source-follow provider contract is invalid".into());
    }
    Ok(())
}

fn validate_hype_breakout_provider(providers: &[CohortProvider]) -> Result<(), String> {
    let Some(provider) = providers
        .iter()
        .find(|provider| provider.strategy_id == HYPE_BREAKOUT_ID)
    else {
        return Ok(());
    };
    let v39_core_scope = provider.symbols == ["BTC", "ETH", "SOL"];
    if !provider.symbols.iter().any(|symbol| symbol == "HYPE") && !v39_core_scope
        || provider.timeframe != "1m"
        || provider.source_profile.is_some()
    {
        return Err("cohort HT-Breakout provider contract is invalid".into());
    }
    Ok(())
}

fn validate_btc_structural_provider(providers: &[CohortProvider]) -> Result<(), String> {
    let Some(provider) = providers
        .iter()
        .find(|provider| provider.strategy_id == BTC_STRUCTURAL_ID)
    else {
        return Ok(());
    };
    let execution_valid = provider
        .execution_symbols
        .as_deref()
        .is_some_and(|symbols| symbols.is_empty() || symbols == ["BTC"]);
    if provider.symbols != ["BTC"]
        || provider.timeframe != "1m"
        || provider.source_profile.is_some()
        || !execution_valid
    {
        return Err("cohort BTC structural provider contract is invalid".into());
    }
    Ok(())
}

fn validate_hype_relaxed_providers(providers: &[CohortProvider]) -> Result<(), String> {
    for provider in providers.iter().filter(|provider| {
        matches!(
            provider.strategy_id.as_str(),
            "hype_breakout_relaxed_60m_bidirectional_v2"
                | "hype_breakout_relaxed_target20_60m_bidirectional_v3"
                | "hype_breakout_relaxed_fixed60_matched_bidirectional_v4"
        )
    }) {
        let execution_valid = provider
            .execution_symbols
            .as_deref()
            .is_some_and(|symbols| symbols.is_empty() || symbols == ["HYPE"]);
        if provider.symbols != ["HYPE"]
            || provider.timeframe != "1m"
            || provider.source_profile.is_some()
            || !execution_valid
        {
            return Err("cohort HYPE relaxed provider contract is invalid".into());
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::validate_specialized_providers;
    use crate::backend_cohort::CohortProvider;

    #[test]
    fn breakout_observer_accepts_cross_asset_coverage_with_hype_only_execution() {
        let provider = CohortProvider {
            strategy_id: "hype_breakout_onset_bidirectional_v1".into(),
            symbols: ["BTC", "ETH", "SOL", "HYPE"].map(str::to_string).to_vec(),
            sides: ["long", "short"].map(str::to_string).to_vec(),
            priority: 40,
            timeframe: "1m".into(),
            maximum_entry_delay_seconds: 60,
            execution_symbols: Some(vec!["HYPE".into()]),
            execution_side_overrides: Default::default(),
            entry_context_overrides: Default::default(),
            sizing_overrides: Default::default(),
            source_profile: None,
            execution: None,
        };

        validate_specialized_providers(&[provider]).expect("valid observer expansion");
    }

    #[test]
    fn breakout_v14_accepts_exact_all_asset_execution_scope() {
        let symbols = ["BTC", "ETH", "SOL", "HYPE"].map(str::to_string).to_vec();
        let provider = CohortProvider {
            strategy_id: "hype_breakout_onset_bidirectional_v1".into(),
            symbols: symbols.clone(),
            sides: ["long", "short"].map(str::to_string).to_vec(),
            priority: 40,
            timeframe: "1m".into(),
            maximum_entry_delay_seconds: 60,
            execution_symbols: Some(symbols),
            execution_side_overrides: Default::default(),
            entry_context_overrides: Default::default(),
            sizing_overrides: Default::default(),
            source_profile: None,
            execution: None,
        };

        validate_specialized_providers(&[provider]).expect("valid v14 execution scope");
    }

    #[test]
    fn breakout_v39_accepts_core_assets_after_hype_moves_to_compression() {
        let symbols = ["BTC", "ETH", "SOL"].map(str::to_string).to_vec();
        let provider = CohortProvider {
            strategy_id: "hype_breakout_onset_bidirectional_v1".into(),
            symbols: symbols.clone(),
            sides: ["long", "short"].map(str::to_string).to_vec(),
            priority: 40,
            timeframe: "1m".into(),
            maximum_entry_delay_seconds: 60,
            execution_symbols: Some(symbols),
            execution_side_overrides: Default::default(),
            entry_context_overrides: Default::default(),
            sizing_overrides: Default::default(),
            source_profile: None,
            execution: None,
        };

        validate_specialized_providers(&[provider]).expect("valid v39 core scope");
    }

    #[test]
    fn candidate_providers_accept_only_their_exact_symbol_and_clock() {
        let btc = provider(
            "btc_structural_continuation_fixed60_bidirectional_v1",
            "BTC",
            "1m",
            Some("BTC"),
        );
        let hype = provider(
            "hype_breakout_relaxed_fixed60_matched_bidirectional_v4",
            "HYPE",
            "1m",
            Some("HYPE"),
        );

        validate_specialized_providers(&[btc, hype]).expect("exact candidates");
    }

    #[test]
    fn btc_candidate_rejects_widened_symbol_scope() {
        let mut btc = provider(
            "btc_structural_continuation_fixed60_bidirectional_v1",
            "BTC",
            "1m",
            Some("BTC"),
        );
        btc.symbols.push("ETH".into());

        let error = validate_specialized_providers(&[btc]).expect_err("widened BTC scope");

        assert!(error.contains("BTC structural"));
    }

    #[test]
    fn canonical_hype_may_remain_observation_only() {
        let provider = provider("hype_breakout_onset_bidirectional_v1", "HYPE", "1m", None);

        validate_specialized_providers(&[provider]).expect("observe-only HYPE source");
    }

    fn provider(
        strategy_id: &str,
        symbol: &str,
        timeframe: &str,
        execution_symbol: Option<&str>,
    ) -> CohortProvider {
        CohortProvider {
            strategy_id: strategy_id.into(),
            symbols: vec![symbol.into()],
            sides: ["long", "short"].map(str::to_string).to_vec(),
            priority: 35,
            timeframe: timeframe.into(),
            maximum_entry_delay_seconds: 60,
            execution_symbols: Some(execution_symbol.map(str::to_string).into_iter().collect()),
            execution_side_overrides: Default::default(),
            entry_context_overrides: Default::default(),
            sizing_overrides: Default::default(),
            source_profile: None,
            execution: None,
        }
    }
}
