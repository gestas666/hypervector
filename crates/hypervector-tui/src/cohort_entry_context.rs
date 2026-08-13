//! Effective-versus-staged entry-context labels for the cohort profile.

use crate::app::App;

pub(crate) fn effective_entry_context(app: &App) -> String {
    let policy = app
        .backend
        .cohort
        .providers
        .get(app.selected_cohort_provider_index)
        .and_then(|provider| {
            app.selected_cohort_symbol()
                .and_then(|symbol| provider.entry_context_overrides.get(symbol))
        });
    entry_context_scope(policy.map(String::as_str)).into()
}

pub(crate) fn staged_entry_context(app: &App) -> String {
    let Some(provider) = app
        .backend
        .cohort
        .providers
        .get(app.selected_cohort_provider_index)
    else {
        return "N/A".into();
    };
    let Some(symbol) = app.selected_cohort_symbol() else {
        return "N/A".into();
    };
    let Some(generation) = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
    else {
        return effective_entry_context(app);
    };
    let Some(overrides) = generation.current_entry_context_overrides.as_ref() else {
        return if generation.matches_runtime {
            effective_entry_context(app)
        } else {
            "NOT REPORTED".into()
        };
    };
    let key = format!("{}|{symbol}", provider.strategy_id);
    entry_context_scope(overrides.get(&key).map(String::as_str)).into()
}

fn entry_context_scope(policy: Option<&str>) -> &'static str {
    match policy {
        Some("dual_mtf_not_opposed") => "DUAL-MTF NOT OPPOSED",
        Some(_) => "UNKNOWN POLICY",
        None => "SOURCE CONTRACT",
    }
}

#[cfg(test)]
mod tests {
    use super::entry_context_scope;

    #[test]
    fn entry_context_scope_names_the_configured_eth_rule() {
        assert_eq!(
            entry_context_scope(Some("dual_mtf_not_opposed")),
            "DUAL-MTF NOT OPPOSED",
        );
        assert_eq!(entry_context_scope(None), "SOURCE CONTRACT");
    }
}
