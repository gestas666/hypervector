//! Interactive restart-only profile editor for the shared cohort.

use ratatui::{
    Frame,
    layout::{Constraint, Layout, Rect},
    text::{Line, Span},
    widgets::{Cell, Paragraph, Row, Table, TableState},
};

use crate::app::App;
use crate::backend_cohort::{CohortAssetConfig, CohortProviderExecutionContract};
use crate::cohort_config_identity::{identity_lines, scope_matrix_lines, staged_provider_scope};
use crate::cohort_config_state::CohortConfigEditor;
use crate::cohort_detail_scroll::bounded_paragraph;
use crate::cohort_entry_context::{effective_entry_context, staged_entry_context};
use crate::cohort_format::money;
use crate::cohort_growth_preflight::growth_preflight_lines;
use crate::cohort_operator::CohortAssetStageRequest;
use crate::cohort_router_format::{direction_scope, human_token};
use crate::cohort_sizing_evidence::{
    asset_ioc_cap_line, asset_sizing_line, staged_provider_sizing_line,
};
use crate::cohort_widgets::{panel, provider_alias, render_empty};

/// Render effective values beside a complete restart-only draft profile.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let (identity_height, editor_height) = if area.height < 32 { (6, 14) } else { (8, 15) };
    let sections = Layout::vertical([
        Constraint::Length(identity_height),
        Constraint::Length(editor_height),
        Constraint::Min(9),
    ])
    .split(area);
    render_identity(frame, app, sections[0]);
    let Some(editor) = app.cohort_config_editor.as_ref() else {
        render_empty(
            frame,
            app,
            sections[1],
            " RESTART PROFILE EDITOR ",
            "Backend did not report a complete editable profile",
        );
        render_context(frame, app, None, sections[2]);
        return;
    };
    render_editor(frame, app, editor, sections[1]);
    render_context(frame, app, Some(editor), sections[2]);
}

fn render_identity(frame: &mut Frame, app: &App, area: Rect) {
    frame.render_widget(
        Paragraph::new(identity_lines(app))
            .block(panel(" RESTART PROFILE EDITOR // FAIL-CLOSED ", app)),
        area,
    );
}

fn render_editor(frame: &mut Frame, app: &App, editor: &CohortConfigEditor, area: Rect) {
    let rows = editor_rows(app, editor);
    let table = Table::new(
        rows,
        [
            Constraint::Length(31),
            Constraint::Length(24),
            Constraint::Length(24),
            Constraint::Min(16),
        ],
    )
    .column_spacing(1)
    .header(Row::new(["SETTING", "EFFECTIVE", "LOCAL EDIT", "CONTROL"]).style(app.theme.header))
    .row_highlight_style(app.theme.highlight)
    .highlight_symbol("▸ ")
    .block(panel(
        " LOCAL EDIT DRAFT // ACTIVE-RUNTIME COPY // SEPARATE FROM PENDING PROFILE ",
        app,
    ));
    let mut state = TableState::default().with_selected(Some(app.cohort_config_selected_index));
    frame.render_stateful_widget(table, area, &mut state);
}

fn editor_rows(app: &App, editor: &CohortConfigEditor) -> Vec<Row<'static>> {
    let selected_asset = editor.assets.get(app.selected_cohort_symbol_index);
    let effective_asset = app
        .backend
        .cohort
        .asset_configs
        .get(app.selected_cohort_symbol_index);
    let effective_runtime = app.backend.cohort.runtime.as_ref();
    let mut rows = vec![
        setting_row(
            "POSITION SLOTS",
            app.backend.cohort.maximum_concurrent_positions.to_string(),
            editor.maximum_positions.to_string(),
            "1 PER ASSET",
        ),
        setting_row(
            "POLL INTERVAL",
            effective_runtime.map_or_else(
                || "N/A".into(),
                |value| format!("{:.0}s", value.poll_seconds),
            ),
            format!("{:.0}s", editor.poll_seconds),
            "+/- 1s",
        ),
    ];
    rows.extend(asset_rows(effective_asset, selected_asset));
    rows.extend(action_rows(app, editor));
    rows
}

fn action_rows(app: &App, editor: &CohortConfigEditor) -> [Row<'static>; 4] {
    [
        setting_row(
            "PROVIDER / COIN SCOPE",
            effective_scope(app),
            draft_scope(app, editor),
            "ENTER toggle",
        ),
        setting_row(
            "ENTRY CONTEXT",
            effective_entry_context(app),
            staged_entry_context(app),
            "PROFILE RULE",
        ),
        setting_row(
            "VALIDATE & STAGE NEW PROFILE",
            "NO RUNTIME CHANGE".into(),
            if editor.dirty {
                "READY".into()
            } else {
                "UNCHANGED".into()
            },
            "ENTER",
        ),
        setting_row(
            "DISCARD DRAFT",
            "EFFECTIVE VALUES".into(),
            "RESTORE".into(),
            "ENTER",
        ),
    ]
}

fn asset_rows(
    effective: Option<&CohortAssetConfig>,
    draft: Option<&CohortAssetStageRequest>,
) -> [Row<'static>; 5] {
    [
        setting_row(
            "LEVERAGE",
            effective.map_or_else(|| "N/A".into(), |value| format!("{:.1}x", value.leverage)),
            draft.map_or_else(|| "N/A".into(), |value| format!("{:.1}x", value.leverage)),
            "+/- 1x",
        ),
        setting_row(
            "MARGIN FRACTION",
            effective.map_or_else(
                || "N/A".into(),
                |value| format!("{:.1}%", value.margin_fraction * 100.0),
            ),
            draft.map_or_else(
                || "N/A".into(),
                |value| format!("{:.1}%", value.margin_fraction * 100.0),
            ),
            "+/- 1%",
        ),
        setting_row(
            "MAX NOTIONAL",
            effective.map_or_else(|| "N/A".into(), |value| money(value.max_notional_usd)),
            draft.map_or_else(|| "N/A".into(), |value| money(value.max_notional_usd)),
            "+/- $5",
        ),
        setting_row(
            "LEGACY STOP FALLBACK",
            effective.map_or_else(|| "N/A".into(), |value| format!("{:.0}bps", value.stop_bps)),
            draft.map_or_else(|| "N/A".into(), |value| format!("{:.0}bps", value.stop_bps)),
            "+/- 10bps",
        ),
        setting_row(
            "LEGACY HOLD FALLBACK",
            effective.map_or_else(
                || "N/A".into(),
                |value| format!("{}h", value.maximum_hold_seconds / 3_600),
            ),
            draft.map_or_else(
                || "N/A".into(),
                |value| format!("{}h", value.maximum_hold_seconds / 3_600),
            ),
            "+/- 1h",
        ),
    ]
}

fn setting_row(name: &str, effective: String, draft: String, control: &str) -> Row<'static> {
    Row::new(vec![
        Cell::from(name.to_string()),
        Cell::from(effective),
        Cell::from(draft),
        Cell::from(control.to_string()),
    ])
}

fn effective_scope(app: &App) -> String {
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
    if !provider
        .execution_symbols
        .as_ref()
        .is_some_and(|symbols| symbols.iter().any(|value| value == symbol))
    {
        return "OBSERVE ONLY".into();
    }
    direction_scope(Some(
        provider
            .execution_side_overrides
            .get(symbol)
            .unwrap_or(&provider.sides),
    ))
}

fn draft_scope(app: &App, editor: &CohortConfigEditor) -> String {
    if let Some(scope) = staged_provider_scope(app) {
        return scope;
    }
    let Some(provider) = editor.providers.get(app.selected_cohort_provider_index) else {
        return "N/A".into();
    };
    let Some(symbol) = app.selected_cohort_symbol() else {
        return "N/A".into();
    };
    if provider
        .execution_symbols
        .iter()
        .any(|value| value == symbol)
    {
        let sides = app
            .backend
            .cohort
            .providers
            .get(app.selected_cohort_provider_index)
            .map(|value| {
                value
                    .execution_side_overrides
                    .get(symbol)
                    .unwrap_or(&value.sides)
            });
        direction_scope(sides)
    } else {
        "OBSERVE ONLY".into()
    }
}

fn render_context(frame: &mut Frame, app: &App, editor: Option<&CohortConfigEditor>, area: Rect) {
    const FOOTER_ROWS: u16 = 2;
    let mut lines = context_lines(app, editor);
    let Some(safety) = lines.pop() else {
        return;
    };
    let block = panel(" PROFILE SCOPE // AUDITED REQUEST STATUS ", app);
    let inner = block.inner(area);
    let rows = inner.height.saturating_sub(FOOTER_ROWS);
    let offset = u16::try_from(app.cohort_config_context_offset).unwrap_or(u16::MAX);
    let (paragraph, total, maximum) = bounded_paragraph(lines, inner.width, rows, offset);
    app.cohort_config_context_max_scroll
        .set(usize::from(maximum));
    app.cohort_config_context_page_rows.set(usize::from(rows));
    let start = usize::from(offset.min(maximum));
    let end = (start + usize::from(rows)).min(total);
    let omitted = total.saturating_sub(end - start);
    let footer = vec![
        Line::from(format!(
            "CONTENT WINDOW {}-{end} / {total} // {omitted} LINES OMITTED // [PgUp/PgDn] Scope",
            start + 1,
        )),
        safety,
    ];
    frame.render_widget(block, area);
    frame.render_widget(paragraph, Rect::new(inner.x, inner.y, inner.width, rows));
    frame.render_widget(
        Paragraph::new(footer),
        Rect::new(inner.x, inner.y + rows, inner.width, inner.height - rows),
    );
}

fn context_lines<'a>(app: &'a App, editor: Option<&CohortConfigEditor>) -> Vec<Line<'a>> {
    let coin = app.selected_cohort_symbol().unwrap_or("N/A");
    let provider = app
        .backend
        .cohort
        .providers
        .get(app.selected_cohort_provider_index);
    let provider_name = provider
        .map(|value| provider_alias(&value.strategy_id))
        .unwrap_or("N/A");
    let source = provider
        .and_then(|value| value.source_profile.as_deref())
        .unwrap_or("backend built-in");
    let evidence = provider.and_then(|value| {
        app.backend
            .cohort
            .strategy_evidence
            .iter()
            .find(|record| record.strategy_id == value.strategy_id && record.symbol == coin)
    });
    let scope = editor
        .and_then(|_| app.cohort_config_scope_summary())
        .unwrap_or_else(|| "SCOPE UNAVAILABLE".into());
    let notice = crate::cohort_profile_request::notice(
        app,
        "No request pending. Changes remain local until VALIDATE & STAGE is selected.",
    );
    let wallet = configured_label(app.backend.wallet_configured);
    let signer = configured_label(app.backend.signing_key_configured);
    let mut lines = vec![
        Line::from(vec![
            Span::raw("SELECTED COIN "),
            Span::styled(coin.to_string(), app.theme.cyan),
            Span::raw("  //  PROVIDER "),
            Span::styled(provider_name.to_string(), app.theme.title),
        ]),
        Line::from(scope),
        Line::from(format!(
            "SOURCE {source}  //  {}",
            provider_contract(provider.and_then(|value| value.execution.as_ref()))
        )),
        Line::from(evidence.map_or_else(
            || "RESEARCH STATE NOT REPORTED BY THIS RUN".into(),
            |record| {
                format!(
                    "RESEARCH {} // CONF {} // {}",
                    human_token(&record.research_state),
                    record.confidence.to_uppercase(),
                    record.cadence,
                )
            },
        )),
        asset_sizing_line(app, coin),
        staged_provider_sizing_line(app, coin),
    ];
    lines.extend(asset_ioc_cap_line(app, coin));
    lines.extend([
        Line::from(format!(
            "CREDENTIALS  WALLET {wallet}  //  SIGNER {signer}  //  VALUES NEVER RENDERED"
        )),
        Line::from(vec![
            Span::styled("[←/→] COIN", app.theme.gold),
            Span::raw("  "),
            Span::styled("[p/P] PROVIDER", app.theme.gold),
            Span::raw("  "),
            Span::styled("[↑/↓] ROW  [+/-] VALUE  [ENTER] ACTION", app.theme.gold),
        ]),
        Line::from(Span::styled(notice.to_string(), app.theme.muted)),
    ]);
    lines.extend(growth_preflight_lines(app, coin));
    let mut scopes = scope_matrix_lines(app, editor);
    let safety = scopes.pop();
    lines.extend(scopes);
    lines.extend(identity_lines(app));
    lines.extend(safety);
    lines
}

fn provider_contract(value: Option<&CohortProviderExecutionContract>) -> String {
    let Some(contract) = value else {
        return "EXECUTION CONTRACT NOT REPORTED".into();
    };
    format!(
        "EXEC {} | STOP {} | TARGET {} | HOLD {} | RECIPE EXIT {} | LOCK {}",
        human_token(&contract.entry_liquidity),
        stop_contract(contract),
        target_contract(contract),
        hold_contract(contract),
        contract.provider_recipe_exit_policy.to_uppercase(),
        profit_lock_contract(contract),
    )
}

fn profit_lock_contract(contract: &CohortProviderExecutionContract) -> String {
    if contract.adaptive_exit_policy == "regime_book_profit_retention_v1" {
        return "ADAPTIVE REGIME/BOOK PROFIT RETENTION".into();
    }
    if contract.adaptive_exit_policy == "regime_flip_floor_retention_v2" {
        if contract.breakeven_stop_target == "floor" {
            return "ADAPTIVE REGIME-FLIP RATCHET / PROFIT FLOOR v2 / VENUE STOP TO FLOOR".into();
        }
        return "ADAPTIVE REGIME-FLIP RATCHET / PROFIT FLOOR v2".into();
    }
    if contract.profit_lock_policy == "none" {
        return "OFF".into();
    }
    if contract.profit_lock_policy == "btc_hulk_delayed_component_floor_v1" {
        return "DELAYED COMPONENT FLOOR".into();
    }
    if contract.profit_lock_policy == "btc_hulk_delayed_component_exit_v2" {
        return "FLOOR / REVERSAL CONTAINMENT".into();
    }
    match (
        contract.profit_lock_activation_bps,
        contract.profit_lock_floor_bps,
        contract.profit_lock_giveback_bps,
    ) {
        (Some(activation), Some(floor), Some(giveback)) => {
            format!("ON {activation:.0}/{floor:.0}/{giveback:.0}bps")
        }
        _ => "INVALID".into(),
    }
}

fn hold_contract(contract: &CohortProviderExecutionContract) -> String {
    let soft = contract.maximum_hold_seconds / 3_600;
    if contract.maximum_hold_policy != "extend_while_regime_supported" {
        return format!("{soft}H FIXED");
    }
    contract.hard_maximum_hold_seconds.map_or_else(
        || format!("{soft}H EXTEND / HARD N/A"),
        |hard| format!("{soft}H EXTEND WHILE ALIGNED / HARD {}H", hard / 3_600),
    )
}

fn stop_contract(contract: &CohortProviderExecutionContract) -> String {
    if contract.stop_policy == "fixed_bps" {
        return contract
            .stop_bps
            .map_or_else(|| "FIXED N/A".into(), |value| format!("{value:.0}bps"));
    }
    match (contract.minimum_stop_bps, contract.maximum_stop_bps) {
        (Some(minimum), Some(maximum)) => format!("STRUCT {minimum:.0}-{maximum:.0}bps"),
        _ => "STRUCT N/A".into(),
    }
}

fn target_contract(contract: &CohortProviderExecutionContract) -> String {
    match contract.target_policy.as_str() {
        "none" => "NONE".into(),
        "fixed_bps" => contract
            .target_bps
            .map_or_else(|| "FIXED N/A".into(), |value| format!("{value:.1}bps")),
        "reward_risk" => contract
            .target_r_multiple
            .map_or_else(|| "RR N/A".into(), |value| format!("{value:.1}R")),
        "absolute_anchor" => "DYNAMIC PRIOR-CLOSE".into(),
        _ => "UNKNOWN".into(),
    }
}

fn configured_label(value: Option<bool>) -> &'static str {
    match value {
        Some(true) => "CONFIGURED",
        Some(false) => "MISSING",
        None => "UNREPORTED",
    }
}

#[cfg(test)]
mod tests {
    use super::profit_lock_contract;
    use crate::backend_cohort::CohortProviderExecutionContract;

    #[test]
    fn specialized_btc_hulk_lock_is_not_labeled_invalid() {
        let contract = CohortProviderExecutionContract {
            entry_liquidity: "taker_ioc".into(),
            stop_policy: "structural_clamped_bps".into(),
            target_policy: "reward_risk".into(),
            maximum_hold_seconds: 86_400,
            stop_bps: None,
            minimum_stop_bps: Some(20.0),
            maximum_stop_bps: Some(75.0),
            target_bps: None,
            target_r_multiple: Some(3.0),
            safety_stop_overlay: false,
            maximum_hold_policy: "fixed".into(),
            hard_maximum_hold_seconds: None,
            provider_recipe_exit_policy: "ignore".into(),
            adaptive_exit_policy: "none".into(),
            breakeven_stop_target: "entry_offset".into(),
            profit_lock_policy: "btc_hulk_delayed_component_floor_v1".into(),
            profit_lock_activation_bps: None,
            profit_lock_floor_bps: None,
            profit_lock_giveback_bps: None,
        };

        assert_eq!(profit_lock_contract(&contract), "DELAYED COMPONENT FLOOR");
        let versioned = CohortProviderExecutionContract {
            adaptive_exit_policy: "none".into(),
            profit_lock_policy: "btc_hulk_delayed_component_exit_v2".into(),
            ..contract
        };
        assert_eq!(
            profit_lock_contract(&versioned),
            "FLOOR / REVERSAL CONTAINMENT"
        );
        let retention = CohortProviderExecutionContract {
            adaptive_exit_policy: "regime_flip_floor_retention_v2".into(),
            profit_lock_policy: "none".into(),
            ..versioned
        };
        assert_eq!(
            profit_lock_contract(&retention),
            "ADAPTIVE REGIME-FLIP RATCHET / PROFIT FLOOR v2"
        );
        let floor = CohortProviderExecutionContract {
            breakeven_stop_target: "floor".into(),
            ..retention
        };
        assert_eq!(
            profit_lock_contract(&floor),
            "ADAPTIVE REGIME-FLIP RATCHET / PROFIT FLOOR v2 / VENUE STOP TO FLOOR"
        );
    }
}
