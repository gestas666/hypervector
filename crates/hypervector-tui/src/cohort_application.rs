//! Cohort-specific selection and fail-closed operator interaction state.

use std::path::PathBuf;

use chrono::Utc;

use crate::app::App;
use crate::backend_telemetry::BackendConnectionState;
use crate::cohort_config_state::{CONFIG_ROW_COUNT, CohortConfigEditor};
use crate::cohort_operator::{
    CohortOperatorAction, CohortOperatorDraft, new_request_id, write_operator_request,
    write_profile_stage_request,
};
use crate::cohort_widgets::provider_alias;

fn provider_execution_sides<'a>(
    provider: &'a crate::backend_cohort::CohortProvider,
    symbol: &str,
) -> Option<&'a [String]> {
    let executable = provider
        .execution_symbols
        .as_ref()
        .is_some_and(|symbols| symbols.iter().any(|value| value == symbol));
    if !executable {
        return None;
    }
    Some(
        provider
            .execution_side_overrides
            .get(symbol)
            .unwrap_or(&provider.sides),
    )
}

impl App {
    /// Configure the local inbox used only by an already-armed Python backend.
    pub fn set_cohort_command_inbox(&mut self, path: Option<PathBuf>) {
        self.cohort_command_inbox = path;
    }

    /// Return the currently selected execution-eligible provider.
    pub fn selected_cohort_provider(&self) -> Option<&crate::backend_cohort::CohortProvider> {
        self.backend
            .cohort
            .providers
            .get(self.selected_cohort_provider_index)
    }

    /// Return an execution-authorized manual side for the current route.
    pub(crate) fn selected_cohort_operator_side(&self) -> Option<&str> {
        let symbol = self.selected_cohort_symbol()?;
        let sides = provider_execution_sides(self.selected_cohort_provider()?, symbol)?;
        if sides.iter().any(|side| side == &self.cohort_operator_side) {
            return Some(self.cohort_operator_side.as_str());
        }
        sides.first().map(String::as_str)
    }

    /// Open the selected coin's read-only strategy chart inspector.
    pub fn toggle_cohort_chart_modal(&mut self) {
        self.cohort_detail_scroll = 0;
        if self.selected_cohort_symbol().is_some() {
            self.select_available_chart_provider();
            self.show_cohort_chart_modal = !self.show_cohort_chart_modal;
        }
    }

    /// Cycle through configured providers that observe the selected chart coin.
    pub fn cycle_cohort_chart_provider(&mut self, delta: isize) {
        self.cohort_detail_scroll = 0;
        let eligible = self.chart_provider_indices();
        if eligible.is_empty() {
            return;
        }
        let current = eligible
            .iter()
            .position(|index| *index == self.selected_cohort_chart_provider_index)
            .unwrap_or(0);
        let next = current.saturating_add_signed(delta).min(eligible.len() - 1);
        self.selected_cohort_chart_provider_index = eligible[next];
    }

    fn select_available_chart_provider(&mut self) {
        let eligible = self.chart_provider_indices();
        if self.chart_provider_has_evaluation(self.selected_cohort_chart_provider_index) {
            return;
        }
        let preferred = eligible
            .iter()
            .find(|index| self.chart_provider_has_evaluation(**index))
            .or_else(|| eligible.first());
        if let Some(index) = preferred {
            self.selected_cohort_chart_provider_index = *index;
        }
    }

    fn chart_provider_has_evaluation(&self, provider_index: usize) -> bool {
        let Some(provider) = self.backend.cohort.providers.get(provider_index) else {
            return false;
        };
        let Some(symbol) = self.selected_cohort_symbol() else {
            return false;
        };
        self.backend.cohort.evaluations.iter().any(|evaluation| {
            evaluation.strategy_id == provider.strategy_id && evaluation.symbol == symbol
        })
    }

    fn chart_provider_indices(&self) -> Vec<usize> {
        let Some(symbol) = self.selected_cohort_symbol() else {
            return Vec::new();
        };
        self.backend
            .cohort
            .providers
            .iter()
            .enumerate()
            .filter(|(_, provider)| provider.symbols.iter().any(|value| value == symbol))
            .map(|(index, _)| index)
            .collect()
    }

    /// Cycle through providers that can execute the selected coin.
    pub fn cycle_cohort_provider(&mut self, delta: isize) {
        let Some(symbol) = self.selected_cohort_symbol().map(str::to_string) else {
            return;
        };
        let eligible = self
            .backend
            .cohort
            .providers
            .iter()
            .enumerate()
            .filter(|(_, provider)| {
                provider
                    .execution_symbols
                    .as_ref()
                    .is_some_and(|symbols| symbols.contains(&symbol))
            })
            .map(|(index, _)| index)
            .collect::<Vec<_>>();
        if eligible.is_empty() {
            return;
        }
        let current = eligible
            .iter()
            .position(|index| *index == self.selected_cohort_provider_index)
            .unwrap_or(0);
        let next = current.saturating_add_signed(delta).min(eligible.len() - 1);
        self.selected_cohort_provider_index = eligible[next];
    }

    /// Toggle the requested manual entry direction.
    pub fn toggle_cohort_operator_side(&mut self) {
        let sides = self
            .selected_cohort_symbol()
            .and_then(|symbol| provider_execution_sides(self.selected_cohort_provider()?, symbol))
            .map(<[String]>::to_vec);
        let Some(sides) = sides else {
            return;
        };
        let current = sides
            .iter()
            .position(|side| side == &self.cohort_operator_side)
            .unwrap_or(0);
        self.cohort_operator_side = sides[(current + 1) % sides.len()].clone();
    }

    /// Move between entry, close, and portfolio transition-drain controls.
    pub fn move_cohort_control_focus(&mut self, delta: isize) {
        self.cohort_control_focus = self
            .cohort_control_focus
            .saturating_add_signed(delta)
            .min(2);
    }

    /// Move down one bounded row in the restart-only profile editor.
    pub fn select_next_cohort_config(&mut self) {
        self.cohort_config_selected_index =
            (self.cohort_config_selected_index + 1).min(CONFIG_ROW_COUNT.saturating_sub(1));
    }

    /// Move up one bounded row in the restart-only profile editor.
    pub fn select_prev_cohort_config(&mut self) {
        self.cohort_config_selected_index = self.cohort_config_selected_index.saturating_sub(1);
    }

    /// Page through the audited scope context without changing the editable draft.
    pub fn page_cohort_config_context(&mut self, delta: isize) {
        let maximum = self.cohort_config_context_max_scroll.get();
        let page = self.cohort_config_context_page_rows.get() as isize;
        self.cohort_config_context_offset = self
            .cohort_config_context_offset
            .min(maximum)
            .saturating_add_signed(delta.saturating_mul(page))
            .min(maximum);
    }

    /// Adjust the selected numeric draft setting without mutating the running backend.
    pub fn adjust_cohort_config(&mut self, delta: f64) {
        let asset = self.selected_cohort_symbol_index;
        if let Some(editor) = self.cohort_config_editor.as_mut() {
            editor.adjust(self.cohort_config_selected_index, asset, delta);
        }
    }

    /// Cycle the provider whose per-coin execution scope is being edited.
    pub fn cycle_cohort_config_provider(&mut self, delta: isize) {
        let count = self.backend.cohort.providers.len();
        if count == 0 {
            self.selected_cohort_provider_index = 0;
            return;
        }
        self.selected_cohort_provider_index = self
            .selected_cohort_provider_index
            .saturating_add_signed(delta)
            .min(count - 1);
    }

    /// Toggle scope, stage a full profile, or discard the draft for the selected row.
    pub fn activate_cohort_config_row(&mut self) {
        self.cohort_notice = None;
        self.cohort_profile_request = None;
        match self.cohort_config_selected_index {
            7 => self.toggle_cohort_config_scope(),
            9 => self.stage_cohort_profile(),
            10 => self.discard_cohort_config_draft(),
            _ => self.cohort_notice = Some("USE +/- TO ADJUST THE SELECTED VALUE".into()),
        }
    }

    /// Summarize the selected provider/coin scope without exposing configuration internals.
    pub fn cohort_config_scope_summary(&self) -> Option<String> {
        let editor = self.cohort_config_editor.as_ref()?;
        let provider = editor.providers.get(self.selected_cohort_provider_index)?;
        let symbol = self.selected_cohort_symbol()?;
        let status = if provider
            .execution_symbols
            .iter()
            .any(|value| value == symbol)
        {
            "EXECUTION ENABLED"
        } else {
            "OBSERVE ONLY"
        };
        Some(format!(
            "{} // {symbol} // {status}",
            provider_alias(&provider.strategy_id)
        ))
    }

    /// Validate display-visible prerequisites before showing confirmation.
    pub fn prepare_cohort_confirmation(&mut self) {
        self.cohort_notice = None;
        self.cohort_profile_request = None;
        match self.build_cohort_draft() {
            Ok(draft) => self.cohort_confirmation = Some(draft),
            Err(message) => self.cohort_notice = Some(message),
        }
    }

    /// Atomically submit the confirmed request without holding venue credentials.
    pub fn submit_cohort_confirmation(&mut self) {
        let Some(draft) = self.cohort_confirmation.take() else {
            return;
        };
        let result = self.write_cohort_draft(&draft);
        self.cohort_notice = Some(match result {
            Ok(request_id) => format!("REQUEST {request_id} SUBMITTED // AWAIT BACKEND ACK"),
            Err(message) => format!("REQUEST NOT SUBMITTED // {message}"),
        });
    }

    /// Cancel an unsubmitted operator operation.
    pub fn cancel_cohort_confirmation(&mut self) {
        self.cohort_confirmation = None;
        self.cohort_notice = Some("OPERATOR ACTION CANCELED // NO REQUEST WRITTEN".into());
    }

    fn build_cohort_draft(&self) -> Result<CohortOperatorDraft, String> {
        if self.backend.connection != BackendConnectionState::Connected {
            return Err("backend is not connected".into());
        }
        if !cohort_backend_accepts_operator_requests(self) {
            return Err("backend is not live armed".into());
        }
        if self.cohort_command_inbox.is_none() {
            return Err("launcher did not configure an operator inbox".into());
        }
        if self.cohort_control_focus == 2 {
            return Ok(CohortOperatorDraft {
                symbol: "MULTI".into(),
                action: CohortOperatorAction::TransitionDrain,
            });
        }
        let symbol = self
            .selected_cohort_symbol()
            .ok_or_else(|| "no cohort symbol is selected".to_string())?;
        let asset = self
            .backend
            .cohort
            .assets
            .iter()
            .find(|asset| asset.symbol == symbol);
        let action = if self.cohort_control_focus == 1 {
            if asset
                .and_then(|value| value.position_side.as_ref())
                .is_none()
            {
                return Err("manual close requires an open backend position".into());
            }
            CohortOperatorAction::ManualClose
        } else {
            self.manual_entry_action(symbol, asset)?
        };
        Ok(CohortOperatorDraft {
            symbol: symbol.into(),
            action,
        })
    }

    fn manual_entry_action(
        &self,
        symbol: &str,
        asset: Option<&crate::backend_cohort::CohortAssetSnapshot>,
    ) -> Result<CohortOperatorAction, String> {
        if asset
            .and_then(|value| value.position_side.as_ref())
            .is_some()
        {
            return Err("manual entry requires a flat backend position".into());
        }
        let provider = self
            .selected_cohort_provider()
            .ok_or_else(|| "no provider is selected".to_string())?;
        let executable = provider
            .execution_symbols
            .as_ref()
            .is_some_and(|symbols| symbols.iter().any(|value| value == symbol));
        if !executable {
            return Err("selected provider cannot execute this coin".into());
        }
        let side = self
            .selected_cohort_operator_side()
            .ok_or_else(|| "selected provider has no authorized entry side".to_string())?;
        Ok(CohortOperatorAction::ManualEnter {
            provider: provider.strategy_id.clone(),
            side: side.into(),
        })
    }

    fn write_cohort_draft(&self, draft: &CohortOperatorDraft) -> Result<String, String> {
        if self.backend.connection != BackendConnectionState::Connected {
            return Err("backend is not connected".into());
        }
        if !cohort_backend_accepts_operator_requests(self) {
            return Err("backend is not live armed".into());
        }
        let inbox = self
            .cohort_command_inbox
            .as_ref()
            .ok_or_else(|| "operator inbox is unavailable".to_string())?;
        let run_id = self
            .backend
            .run_id
            .as_deref()
            .ok_or_else(|| "backend run identity is unavailable".to_string())?;
        let profile = self
            .backend
            .profile_fingerprint
            .as_deref()
            .ok_or_else(|| "backend profile fingerprint is unavailable".to_string())?;
        let request_id = new_request_id();
        write_operator_request(inbox, run_id, profile, draft, Utc::now(), &request_id)
            .map_err(|error| error.to_string())?;
        Ok(request_id)
    }

    fn toggle_cohort_config_scope(&mut self) {
        let Some(symbol) = self.selected_cohort_symbol().map(str::to_string) else {
            self.cohort_notice = Some("NO COHORT COIN IS SELECTED".into());
            return;
        };
        let Some(editor) = self.cohort_config_editor.as_mut() else {
            self.cohort_notice = Some("BACKEND CONFIGURATION IS UNAVAILABLE".into());
            return;
        };
        editor.toggle_provider_symbol(self.selected_cohort_provider_index, &symbol);
        self.cohort_notice = self.cohort_config_scope_summary();
    }

    fn stage_cohort_profile(&mut self) {
        let result = self.write_cohort_profile_stage();
        self.cohort_notice = Some(match result {
            Ok(request_id) => {
                self.cohort_profile_request =
                    crate::cohort_profile_request::ProfileRequest::from_backend(
                        &self.backend,
                        request_id.clone(),
                    );
                format!("STAGED PROFILE {request_id} SUBMITTED // BACKEND VALIDATION PENDING")
            }
            Err(message) => format!("PROFILE NOT STAGED // {message}"),
        });
    }

    fn write_cohort_profile_stage(&self) -> Result<String, String> {
        if self.backend.live_armed == Some(true) {
            return Err("DISARM LIVE EXECUTION BEFORE STAGING A RESTART PROFILE".into());
        }
        let editor = self
            .cohort_config_editor
            .as_ref()
            .ok_or_else(|| "backend configuration is unavailable".to_string())?;
        if !editor.dirty {
            return Err("draft is unchanged".into());
        }
        let inbox = self
            .cohort_command_inbox
            .as_ref()
            .ok_or_else(|| "launcher did not configure an operator inbox".to_string())?;
        let run_id = self
            .backend
            .run_id
            .as_deref()
            .ok_or_else(|| "backend run identity is unavailable".to_string())?;
        let profile = self
            .backend
            .profile_fingerprint
            .as_deref()
            .ok_or_else(|| "backend profile fingerprint is unavailable".to_string())?;
        let request_id = new_request_id();
        write_profile_stage_request(
            inbox,
            run_id,
            profile,
            &editor.request(),
            Utc::now(),
            &request_id,
        )
        .map_err(|error| error.to_string())?;
        Ok(request_id)
    }

    fn discard_cohort_config_draft(&mut self) {
        self.cohort_config_editor = CohortConfigEditor::from_backend(&self.backend.cohort);
        self.cohort_notice = Some("DRAFT DISCARDED // EFFECTIVE BACKEND VALUES RESTORED".into());
    }
}

/// Return whether fresh backend telemetry grants access to the local request inbox.
pub(crate) fn cohort_backend_accepts_operator_requests(app: &App) -> bool {
    app.backend.connection == BackendConnectionState::Connected
        && !app.backend.cohort_backend_is_stopped()
        && app.backend.live_armed == Some(true)
        && app.backend.execution_authority.as_deref() == Some("hyperliquid_mainnet")
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::provider_execution_sides;
    use crate::backend_cohort::CohortProvider;

    #[test]
    fn operator_sides_honor_symbol_override_and_execution_scope() {
        let provider = CohortProvider {
            strategy_id: "pressure".into(),
            symbols: vec!["xyz:SNDK".into(), "xyz:BRENTOIL".into()],
            sides: vec!["long".into(), "short".into()],
            priority: 1,
            timeframe: "15m".into(),
            maximum_entry_delay_seconds: 30,
            execution_symbols: Some(vec!["xyz:SNDK".into(), "xyz:BRENTOIL".into()]),
            execution_side_overrides: BTreeMap::from([("xyz:SNDK".into(), vec!["short".into()])]),
            entry_context_overrides: BTreeMap::new(),
            sizing_overrides: BTreeMap::new(),
            source_profile: None,
            execution: None,
        };

        assert_eq!(
            provider_execution_sides(&provider, "xyz:SNDK"),
            Some(&["short".into()][..])
        );
        assert_eq!(
            provider_execution_sides(&provider, "xyz:BRENTOIL"),
            Some(&["long".into(), "short".into()][..]),
        );
        assert_eq!(provider_execution_sides(&provider, "xyz:GOLD"), None);
    }
}
