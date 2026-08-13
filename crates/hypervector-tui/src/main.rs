//! Main entrypoint for Quant TA & Microstructure Regime Detector Cockpit.

use std::io;
use std::time::Duration;

use clap::Parser;
use color_eyre::Result;
use crossterm::{
    event::{self, DisableMouseCapture, Event, KeyCode, KeyEventKind},
    execute,
    style::Print,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::Terminal;
use ratatui::backend::CrosstermBackend;

use hypervector_tui::backend_growth_preflight::GrowthPreflightSource;
use hypervector_tui::backend_hip3_roster::Hip3RosterSource;
use hypervector_tui::backend_hype_l2_observer::HypeL2ObserverSource;
use hypervector_tui::terminal_mouse::click_capture_sequence;
use hypervector_tui::{
    app::App, backend_telemetry::BackendTelemetrySource, cli_args::CliArgs,
    cohort_navigation::resolve_tab_navigation, data_loader::load_snapshots_with_metadata, ui,
};

type CockpitTerminal = Terminal<CrosstermBackend<io::Stdout>>;

fn main() -> Result<()> {
    color_eyre::install()?;
    let (
        mut app,
        mut backend_source,
        mut l2_source,
        mut hip3_source,
        mut growth_source,
        refresh_ms,
    ) = prepare_app();
    let mut terminal = start_terminal()?;
    let result = run_app(
        &mut terminal,
        &mut app,
        &mut backend_source,
        &mut l2_source,
        &mut hip3_source,
        &mut growth_source,
        refresh_ms,
    );
    restore_terminal(&mut terminal)?;
    if let Err(error) = result {
        eprintln!("Error running regime cockpit TUI: {error:?}");
    }
    Ok(())
}

fn prepare_app() -> (
    App,
    BackendTelemetrySource,
    HypeL2ObserverSource,
    Hip3RosterSource,
    GrowthPreflightSource,
    u64,
) {
    let mut args = CliArgs::parse();
    let decisions_path = args.backend_ledger.clone().unwrap_or_else(|| {
        args.data_root
            .join("paper")
            .join("decisions")
            .join("decisions.jsonl")
    });
    let mut backend_source = BackendTelemetrySource::with_checkpoint_path(
        decisions_path,
        args.cohort_checkpoint.clone(),
    );
    let mut l2_source = HypeL2ObserverSource::new(args.hype_l2_observer_status.clone());
    let hip3_path = args.hip3_roster_status.clone().or_else(|| {
        Some(
            args.data_root
                .join("runtime")
                .join("research")
                .join("hip3_roster_latest.json"),
        )
    });
    let mut hip3_source = Hip3RosterSource::new(hip3_path);
    let mut growth_source = GrowthPreflightSource::new(args.growth_preflight.clone());
    let initial_backend = refresh_sources(
        &mut backend_source,
        &mut l2_source,
        &mut hip3_source,
        &mut growth_source,
    );
    if let Some(symbol) = initial_backend.symbol.as_ref() {
        args.symbol = symbol.clone();
    }
    let (snapshots, is_synthetic) = load_snapshots_with_metadata(&args);
    let mut app = App::new(
        args.symbol,
        args.timeframe,
        snapshots,
        args.live,
        is_synthetic,
    );
    app.detached_lifecycle = args.detached_lifecycle;
    app.active_tab = args.initial_tab - 1;
    app.set_cohort_command_inbox(args.cohort_command_inbox.clone());
    app.apply_backend_telemetry(initial_backend);
    (
        app,
        backend_source,
        l2_source,
        hip3_source,
        growth_source,
        args.refresh_ms,
    )
}

fn refresh_sources(
    backend_source: &mut BackendTelemetrySource,
    l2_source: &mut HypeL2ObserverSource,
    hip3_source: &mut Hip3RosterSource,
    growth_source: &mut GrowthPreflightSource,
) -> hypervector_tui::backend_telemetry::BackendTelemetrySnapshot {
    let mut snapshot = backend_source.refresh();
    snapshot.hype_l2_observer = l2_source.refresh();
    snapshot.hip3_roster = hip3_source.refresh();
    snapshot.growth_preflight = growth_source.refresh();
    snapshot
}

fn start_terminal() -> Result<CockpitTerminal> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(
        stdout,
        DisableMouseCapture,
        EnterAlternateScreen,
        Print(click_capture_sequence())
    )?;
    let backend = CrosstermBackend::new(stdout);
    Ok(Terminal::new(backend)?)
}

fn restore_terminal(terminal: &mut CockpitTerminal) -> Result<()> {
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        DisableMouseCapture,
        LeaveAlternateScreen
    )?;
    terminal.show_cursor()?;
    Ok(())
}

fn run_app<B: ratatui::backend::Backend>(
    terminal: &mut Terminal<B>,
    app: &mut App,
    backend_source: &mut BackendTelemetrySource,
    l2_source: &mut HypeL2ObserverSource,
    hip3_source: &mut Hip3RosterSource,
    growth_source: &mut GrowthPreflightSource,
    refresh_ms: u64,
) -> io::Result<()> {
    while !app.should_quit {
        app.apply_backend_telemetry(refresh_sources(
            backend_source,
            l2_source,
            hip3_source,
            growth_source,
        ));
        terminal.draw(|f| ui::draw(f, app))?;
        let timeout = Duration::from_millis((refresh_ms as f64 / app.playback_speed) as u64);
        if event::poll(timeout)? {
            handle_input(app, event::read()?);
        } else {
            app.on_tick();
        }
    }
    Ok(())
}

fn handle_input(app: &mut App, input: Event) {
    if overlays_closed(app)
        && let Some(tab) =
            resolve_tab_navigation(&input, app.active_tab, app.backend.is_multi_asset_cohort())
    {
        app.active_tab = tab;
        return;
    }
    if let Event::Key(key) = input
        && key.kind == KeyEventKind::Press
    {
        handle_key(app, key.code);
    }
}

fn overlays_closed(app: &App) -> bool {
    app.cohort_confirmation.is_none()
        && !app.show_help_overlay
        && !app.show_event_detail_modal
        && !app.show_trade_detail_modal
        && !app.show_cohort_setup_modal
        && !app.show_cohort_chart_modal
        && !app.show_cohort_fill_modal
        && !app.show_cohort_journal_modal
}

fn handle_key(app: &mut App, code: KeyCode) {
    if app.cohort_confirmation.is_some() {
        handle_confirmation_key(app, code);
    } else if app.show_help_overlay {
        if is_modal_close_key(code) || matches!(code, KeyCode::Char('?') | KeyCode::Char('h')) {
            app.show_help_overlay = false;
        }
    } else if app.show_cohort_chart_modal {
        handle_chart_modal_key(app, code);
    } else if app.show_cohort_setup_modal
        || app.show_cohort_fill_modal
        || app.show_cohort_journal_modal
    {
        if is_modal_close_key(code) {
            app.close_cohort_modals();
        }
    } else if app.show_event_detail_modal || app.show_trade_detail_modal {
        if is_modal_close_key(code) {
            app.show_event_detail_modal = false;
            app.show_trade_detail_modal = false;
        }
    } else {
        handle_primary_key(app, code);
    }
}

fn handle_chart_modal_key(app: &mut App, code: KeyCode) {
    match code {
        KeyCode::Down | KeyCode::Right | KeyCode::Char('j') => {
            app.cycle_cohort_chart_provider(1);
        }
        KeyCode::Up | KeyCode::Left | KeyCode::Char('k') => {
            app.cycle_cohort_chart_provider(-1);
        }
        code if is_modal_close_key(code) => app.close_cohort_modals(),
        _ => {}
    }
}

fn handle_confirmation_key(app: &mut App, code: KeyCode) {
    match code {
        KeyCode::Char('y') => app.submit_cohort_confirmation(),
        KeyCode::Char('q') | KeyCode::Esc | KeyCode::Char('n') => {
            app.cancel_cohort_confirmation();
        }
        _ => {}
    }
}

fn is_modal_close_key(code: KeyCode) -> bool {
    matches!(
        code,
        KeyCode::Char('q') | KeyCode::Esc | KeyCode::Enter | KeyCode::Char(' ')
    )
}

fn handle_primary_key(app: &mut App, code: KeyCode) {
    match code {
        KeyCode::Char('q') | KeyCode::Esc => app.should_quit = true,
        KeyCode::Char('?') | KeyCode::Char('h') => app.toggle_help_overlay(),
        KeyCode::Enter => handle_enter(app),
        KeyCode::Char('+') | KeyCode::Char('=') => handle_adjustment(app, 1.0),
        KeyCode::Char('-') => handle_adjustment(app, -1.0),
        KeyCode::Left => handle_horizontal(app, -1),
        KeyCode::Right => handle_horizontal(app, 1),
        KeyCode::Down | KeyCode::Char('j') => handle_selection(app, true),
        KeyCode::Up | KeyCode::Char('k') => handle_selection(app, false),
        KeyCode::Char(' ') => app.toggle_play_pause(),
        KeyCode::Char('s') => app.cycle_speed(),
        KeyCode::Char('t') => app.cycle_timeframe(),
        KeyCode::Char('r') => app.reset_playhead(),
        KeyCode::Char('p') if cohort_tab(app, 6) => app.cycle_cohort_provider(1),
        KeyCode::Char('P') if cohort_tab(app, 6) => app.cycle_cohort_provider(-1),
        KeyCode::Char('p') if cohort_tab(app, 8) => app.cycle_cohort_config_provider(1),
        KeyCode::Char('P') if cohort_tab(app, 8) => app.cycle_cohort_config_provider(-1),
        KeyCode::PageDown if cohort_tab(app, 8) => app.page_cohort_config_context(1),
        KeyCode::PageUp if cohort_tab(app, 8) => app.page_cohort_config_context(-1),
        KeyCode::Char('d') if cohort_tab(app, 6) => app.toggle_cohort_operator_side(),
        _ => {}
    }
}

fn handle_enter(app: &mut App) {
    if cohort_tab(app, 1) {
        app.toggle_cohort_setup_modal();
    } else if cohort_tab(app, 2) {
        app.toggle_cohort_chart_modal();
    } else if cohort_tab(app, 4) {
        app.toggle_cohort_fill_modal();
    } else if cohort_tab(app, 5) {
        app.toggle_cohort_journal_modal();
    } else if cohort_tab(app, 6) {
        app.prepare_cohort_confirmation();
    } else if cohort_tab(app, 8) {
        app.activate_cohort_config_row();
    } else if !app.backend.is_multi_asset_cohort() && app.active_tab == 3 {
        app.toggle_config_option();
    } else if app.active_tab == 0 {
        app.toggle_trade_modal();
    } else if app.active_tab == 1 {
        app.toggle_event_modal();
    }
}

fn handle_adjustment(app: &mut App, delta: f64) {
    if cohort_tab(app, 8) {
        app.adjust_cohort_config(delta);
    } else if !app.backend.is_multi_asset_cohort() && app.active_tab == 3 {
        if delta > 0.0 {
            app.increase_config_value();
        } else {
            app.decrease_config_value();
        }
    }
}

fn handle_horizontal(app: &mut App, delta: isize) {
    if cohort_tab(app, 4) {
        app.move_cohort_trade_focus(delta);
    } else if app.backend.is_multi_asset_cohort() && matches!(app.active_tab, 0 | 2 | 3 | 6 | 7 | 8)
    {
        app.move_cohort_symbol(delta);
    } else if !app.backend.is_multi_asset_cohort() && app.active_tab == 3 {
        handle_adjustment(app, delta as f64);
    } else if delta > 0 {
        app.step_forward();
    } else {
        app.step_backward();
    }
}

fn handle_selection(app: &mut App, forward: bool) {
    match (app.backend.is_multi_asset_cohort(), app.active_tab, forward) {
        (true, 1, true) => app.select_next_cohort_setup(),
        (true, 1, false) => app.select_prev_cohort_setup(),
        (true, 4, true) => app.select_next_cohort_trade_record(),
        (true, 4, false) => app.select_prev_cohort_trade_record(),
        (true, 5, true) => app.select_next_cohort_journal(),
        (true, 5, false) => app.select_prev_cohort_journal(),
        (true, 6, true) => app.move_cohort_control_focus(1),
        (true, 6, false) => app.move_cohort_control_focus(-1),
        (true, 8, true) => app.select_next_cohort_config(),
        (true, 8, false) => app.select_prev_cohort_config(),
        (false, 3, true) => app.select_next_config(),
        (false, 3, false) => app.select_prev_config(),
        (_, 0, true) => app.select_next_trade(),
        (_, 0, false) => app.select_prev_trade(),
        (_, 1, true) => app.select_next_event(),
        (_, 1, false) => app.select_prev_event(),
        _ => {}
    }
}

fn cohort_tab(app: &App, tab: usize) -> bool {
    app.backend.is_multi_asset_cohort() && app.active_tab == tab
}
