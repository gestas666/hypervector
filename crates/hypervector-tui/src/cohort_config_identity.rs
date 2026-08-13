//! Effective and pending restart-profile identity for the cohort config screen.

use std::collections::{BTreeMap, BTreeSet};

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::cohort_config_exit::pending_provider_exit_label;
use crate::cohort_config_state::CohortConfigEditor;
use crate::cohort_widgets::provider_alias;

type ProviderScopes = BTreeMap<String, BTreeSet<String>>;
const BIDIRECTIONAL_SIDES_PER_ROUTE: usize = 2;

/// Build owned identity lines so checkpoint refreshes cannot borrow stale text.
pub(crate) fn identity_lines(app: &App) -> Vec<Line<'static>> {
    let draft = app
        .cohort_config_editor
        .as_ref()
        .map_or(
            "UNAVAILABLE",
            |editor| if editor.dirty { "DIRTY" } else { "CLEAN" },
        );
    let source = app
        .backend
        .cohort
        .config_source_path
        .as_deref()
        .unwrap_or("not reported");
    let mut lines = vec![
        Line::from(vec![
            Span::raw("EFFECTIVE BACKEND  "),
            Span::styled(source.to_string(), app.theme.cyan),
            Span::raw("  //  DRAFT "),
            Span::styled(
                draft.to_string(),
                if draft == "DIRTY" {
                    app.theme.gold
                } else {
                    app.theme.bull
                },
            ),
        ]),
        run_backup_line(app),
    ];
    lines.extend(pending_restart_lines(app));
    lines.push(pending_caps_line(app));
    lines.push(pending_exit_line(app));
    lines
}

fn run_backup_line(app: &App) -> Line<'static> {
    let mut spans = vec![
        Span::raw("RUN "),
        Span::styled(
            app.backend.run_id.as_deref().unwrap_or("N/A").to_string(),
            app.theme.muted,
        ),
        Span::raw("  //  "),
    ];
    match app.backend.cohort.prestart_backup.as_ref() {
        Some(backup) => {
            spans.push(Span::styled("PRESTART VERIFIED", app.theme.bull));
            spans.push(Span::raw(format!(
                "  MFT {}  SRC {} / {}",
                hash_prefix(&backup.manifest_sha256),
                backup.implementation_file_count,
                hash_prefix(&backup.implementation_sha256),
            )));
        }
        None => spans.push(Span::styled(
            "PRESTART BACKUP UNAVAILABLE // CURRENT RUN PREDATES GATE",
            app.theme.gold,
        )),
    }
    Line::from(spans)
}

fn hash_prefix(value: &str) -> String {
    value.chars().take(12).collect()
}

fn pending_caps_line(app: &App) -> Line<'static> {
    let sizing = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
        .and_then(|generation| generation.current_asset_sizing.as_ref());
    let Some(sizing) = sizing else {
        return Line::from(
            "The TUI publishes an audited request; Python validates and owns activation.",
        );
    };
    let first = sizing.values().next().expect("validated non-empty sizing");
    let uniform = sizing.values().all(|asset| asset == first);
    let sizing_label = if uniform {
        format!(
            "{} ASSETS // LEV {:.1}x // MARGIN {:.2}%/ASSET // CAP ${:.0}/ASSET",
            sizing.len(),
            first.leverage,
            first.margin_fraction * 100.0,
            first.max_notional_usd
        )
    } else {
        sizing
            .iter()
            .map(|(symbol, asset)| format!("{symbol} ${:.0}", asset.max_notional_usd))
            .collect::<Vec<_>>()
            .join(" / ")
    };
    let prefix = if uniform {
        "NEXT SIZING "
    } else {
        "NEXT CAPS "
    };
    Line::from(vec![
        Span::raw(prefix),
        Span::styled(sizing_label, app.theme.cyan),
    ])
}

fn pending_exit_line(app: &App) -> Line<'static> {
    let Some((provider, exit)) = pending_provider_exit_label(app) else {
        return Line::from("PENDING PROFILE EXIT // NOT REPORTED");
    };
    Line::from(vec![
        Span::raw(format!("PENDING PROFILE EXIT {provider} // ")),
        Span::styled(exit, app.theme.gold),
    ])
}

fn pending_restart_lines(app: &App) -> [Line<'static>; 2] {
    let Some(generation) = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()
    else {
        return [
            Line::from("PENDING RESTART PROFILE  UNAVAILABLE"),
            Line::from("CHECKPOINT DID NOT REPORT CONFIGURATION GENERATION"),
        ];
    };
    if generation.matches_runtime {
        return [
            Line::from("PENDING RESTART PROFILE  NONE // DISK MATCHES RUNTIME"),
            Line::from(format!("SOURCE {}", generation.source_path)),
        ];
    }
    let blockers = if generation.blocking_assets.is_empty() {
        "NONE".into()
    } else {
        generation.blocking_assets.join(",")
    };
    [
        Line::from(vec![
            Span::raw("PENDING RESTART PROFILE  "),
            Span::styled(generation.source_path.clone(), app.theme.gold),
        ]),
        Line::from(format!(
            "BLOCKED BY {blockers} // {} // AUTO RESTART {}",
            restart_label(&generation.restart_state),
            if generation.automatic_restart {
                "YES"
            } else {
                "NO"
            },
        )),
    ]
}

fn restart_label(state: &str) -> &'static str {
    match state {
        "wait_for_flat_and_no_orders" => "WAIT FOR FLAT + NO ORDERS",
        "candidate_flat_no_orders" => "FLAT + NO ORDERS VERIFIED",
        "not_required_current_configuration" => "NO RESTART REQUIRED",
        _ => "RESTART STATE UNAVAILABLE",
    }
}

pub(crate) fn staged_provider_scope(app: &App) -> Option<String> {
    let scopes = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()?
        .current_provider_execution_scopes
        .as_ref()?;
    let provider = app
        .backend
        .cohort
        .providers
        .get(app.selected_cohort_provider_index)?;
    let Some(symbols) = scopes.get(&provider.strategy_id) else {
        return Some("PROVIDER REMOVED".into());
    };
    let symbol = app.selected_cohort_symbol()?;
    Some(if symbols.iter().any(|value| value == symbol) {
        "EXECUTION ROUTE".into()
    } else {
        "OBSERVE ONLY".into()
    })
}

pub(crate) fn scope_matrix_lines<'a>(
    app: &'a App,
    editor: Option<&CohortConfigEditor>,
) -> Vec<Line<'a>> {
    if let Some(lines) = staged_scope_matrix_lines(app) {
        return lines;
    }
    let Some(editor) = editor else {
        return Vec::new();
    };
    let mut lines = vec![
        Line::from(""),
        Line::from(Span::styled(
            "EXECUTION SCOPE MATRIX // OBSERVE-ONLY PROVIDERS REMAIN VISIBLE",
            app.theme.header,
        )),
    ];
    lines.extend(editor.providers.iter().map(|provider| {
        let scope = if provider.execution_symbols.is_empty() {
            "OBSERVE ONLY".into()
        } else {
            provider.execution_symbols.join("/")
        };
        Line::from(format!(
            "{:<20}  {scope}",
            provider_alias(&provider.strategy_id)
        ))
    }));
    lines.push(live_arming_safety_line(app));
    lines
}

fn staged_scope_matrix_lines(app: &App) -> Option<Vec<Line<'static>>> {
    let generation = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()?;
    let staged = provider_scopes(generation.current_provider_execution_scopes.as_ref()?);
    let directions = generation.current_provider_execution_directions.as_ref();
    let effective = effective_provider_scopes(app);
    let (changes, removed, added) = scope_changes(app, &effective, &staged, directions);
    let side_scopes = staged_side_scope_label(&staged, directions);
    let mut lines = vec![
        Line::from(""),
        Line::from(Span::styled(
            "EXECUTION SCOPE MATRIX // EFFECTIVE -> NEXT",
            app.theme.header,
        )),
        Line::from(format!(
            "NEXT ASSETS {} // ROUTES EFFECTIVE {} // NEXT {} // {side_scopes} // REMOVE {removed} // ADD {added}",
            asset_count(&staged),
            route_count(&effective),
            route_count(&staged),
        )),
    ];
    if changes.is_empty() {
        lines.push(Line::from("NO PROVIDER OR ROUTE CHANGES"));
    } else {
        lines.extend(changes);
    }
    lines.push(live_arming_safety_line(app));
    Some(lines)
}

fn effective_provider_scopes(app: &App) -> ProviderScopes {
    app.backend
        .cohort
        .providers
        .iter()
        .map(|provider| {
            (
                provider.strategy_id.clone(),
                provider
                    .execution_symbols
                    .clone()
                    .unwrap_or_default()
                    .into_iter()
                    .collect(),
            )
        })
        .collect()
}

fn provider_scopes(scopes: &BTreeMap<String, Vec<String>>) -> ProviderScopes {
    scopes
        .iter()
        .map(|(strategy, symbols)| (strategy.clone(), symbols.iter().cloned().collect()))
        .collect()
}

fn scope_changes(
    app: &App,
    effective: &ProviderScopes,
    staged: &ProviderScopes,
    directions: Option<&BTreeMap<String, Vec<String>>>,
) -> (Vec<Line<'static>>, usize, usize) {
    let providers = effective
        .keys()
        .chain(staged.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut removed_routes = 0;
    let mut added_routes = 0;
    let mut changes = Vec::new();
    for strategy in providers {
        let before = effective.get(&strategy).cloned().unwrap_or_default();
        let after = staged.get(&strategy).cloned().unwrap_or_default();
        let removed = before.difference(&after).cloned().collect::<Vec<_>>();
        let added = after.difference(&before).cloned().collect::<Vec<_>>();
        removed_routes += removed.len();
        added_routes += added.len();
        let rank = scope_change_rank(
            effective.contains_key(&strategy),
            staged.contains_key(&strategy),
            &added,
        );
        let line = scope_change_line(
            app,
            &strategy,
            (&before, effective.contains_key(&strategy)),
            (&after, staged.contains_key(&strategy)),
            &removed,
            &added,
            directions,
        );
        changes.push((rank, strategy, line));
    }
    changes.sort_by(|left, right| (left.0, &left.1).cmp(&(right.0, &right.1)));
    (
        changes.into_iter().map(|(_, _, line)| line).collect(),
        removed_routes,
        added_routes,
    )
}

fn scope_change_rank(before: bool, after: bool, added: &[String]) -> u8 {
    if !before && after {
        0
    } else if !added.is_empty() {
        1
    } else if before && after {
        2
    } else {
        3
    }
}

fn scope_change_line(
    app: &App,
    strategy: &str,
    before: (&BTreeSet<String>, bool),
    after: (&BTreeSet<String>, bool),
    removed: &[String],
    added: &[String],
    directions: Option<&BTreeMap<String, Vec<String>>>,
) -> Line<'static> {
    let mut text = format!(
        "{:<20} EFFECTIVE {} -> NEXT {}",
        provider_alias(strategy),
        scope_label(before.0, before.1, "ABSENT"),
        scope_label(after.0, after.1, "REMOVED"),
    );
    if !removed.is_empty() {
        text.push_str(&format!(" // REMOVE {}", removed.join("/")));
    }
    if !added.is_empty() {
        text.push_str(&format!(" // ADD {}", added.join("/")));
    }
    if after.1 {
        let labels = direction_labels(strategy, after.0, directions);
        if !labels.is_empty() {
            text.push_str(&format!(" // SIDES {}", labels.join(",")));
        }
    }
    Line::from(Span::styled(text, app.theme.gold))
}

fn direction_labels(
    strategy: &str,
    symbols: &BTreeSet<String>,
    directions: Option<&BTreeMap<String, Vec<String>>>,
) -> Vec<String> {
    let Some(values) = directions else {
        return Vec::new();
    };
    symbols
        .iter()
        .filter_map(|symbol| {
            values
                .get(&format!("{strategy}|{symbol}"))
                .map(|sides| format!("{symbol}:{}", sides.join("+")))
        })
        .collect()
}

fn scope_label(symbols: &BTreeSet<String>, exists: bool, absent: &str) -> String {
    if !exists {
        absent.into()
    } else if symbols.is_empty() {
        "OBSERVE ONLY".into()
    } else {
        symbols.iter().cloned().collect::<Vec<_>>().join("/")
    }
}

fn route_count(scopes: &ProviderScopes) -> usize {
    scopes.values().map(BTreeSet::len).sum()
}

fn asset_count(scopes: &ProviderScopes) -> usize {
    scopes
        .values()
        .flat_map(|symbols| symbols.iter())
        .collect::<BTreeSet<_>>()
        .len()
}

fn staged_side_scope_label(
    scopes: &ProviderScopes,
    directions: Option<&BTreeMap<String, Vec<String>>>,
) -> String {
    if let Some(values) = directions {
        return format!(
            "SIDE SCOPES {}",
            values.values().map(Vec::len).sum::<usize>()
        );
    }
    if scopes
        .keys()
        .all(|strategy| strategy.contains("_bidirectional_"))
    {
        return format!(
            "SIDE SCOPES {}",
            route_count(scopes) * BIDIRECTIONAL_SIDES_PER_ROUTE
        );
    }
    "SIDE SCOPES UNREPORTED".into()
}

fn live_arming_safety_line(app: &App) -> Line<'static> {
    Line::from(Span::styled(
        "LIVE ARMING IS CLI-ONLY AND STILL REQUIRES BOTH EXPLICIT RISK FLAGS",
        app.theme.gold,
    ))
}
