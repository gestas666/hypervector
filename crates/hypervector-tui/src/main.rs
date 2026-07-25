//! Main entrypoint for Quant TA & Microstructure Regime Detector Cockpit.

use std::io;
use std::time::Duration;

use clap::Parser;
use color_eyre::Result;
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind},
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::Terminal;
use ratatui::backend::CrosstermBackend;

use hypervector_tui::{
    app::App, backend_telemetry::BackendTelemetrySource, cli_args::CliArgs,
    data_loader::load_snapshots_with_metadata, ui,
};

fn main() -> Result<()> {
    color_eyre::install()?;
    let args = CliArgs::parse();

    let (snapshots, is_synthetic) = load_snapshots_with_metadata(&args);
    let mut app = App::new(
        args.symbol,
        args.timeframe,
        snapshots,
        args.live,
        is_synthetic,
    );
    let decisions_path = args
        .data_root
        .join("paper")
        .join("decisions")
        .join("decisions.jsonl");
    let mut backend_source = BackendTelemetrySource::new(decisions_path);
    app.apply_backend_telemetry(backend_source.refresh());

    // Terminal Initialization
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let res = run_app(
        &mut terminal,
        &mut app,
        &mut backend_source,
        args.refresh_ms,
    );

    // Terminal Cleanup
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    if let Err(err) = res {
        eprintln!("Error running regime cockpit TUI: {err:?}");
    }

    Ok(())
}

fn run_app<B: ratatui::backend::Backend>(
    terminal: &mut Terminal<B>,
    app: &mut App,
    backend_source: &mut BackendTelemetrySource,
    refresh_ms: u64,
) -> io::Result<()> {
    while !app.should_quit {
        app.apply_backend_telemetry(backend_source.refresh());
        terminal.draw(|f| ui::draw(f, app))?;

        let timeout = Duration::from_millis((refresh_ms as f64 / app.playback_speed) as u64);
        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    if app.show_help_overlay {
                        match key.code {
                            KeyCode::Char('q')
                            | KeyCode::Esc
                            | KeyCode::Char('?')
                            | KeyCode::Char('h')
                            | KeyCode::Enter
                            | KeyCode::Char(' ') => {
                                app.show_help_overlay = false;
                            }
                            _ => {}
                        }
                    } else if app.show_event_detail_modal {
                        match key.code {
                            KeyCode::Char('q')
                            | KeyCode::Esc
                            | KeyCode::Enter
                            | KeyCode::Char(' ') => {
                                app.show_event_detail_modal = false;
                            }
                            _ => {}
                        }
                    } else {
                        match key.code {
                            KeyCode::Char('q') | KeyCode::Esc => app.should_quit = true,
                            KeyCode::Tab => app.toggle_tab(),
                            KeyCode::Char('1') => app.active_tab = 0,
                            KeyCode::Char('2') => app.active_tab = 1,
                            KeyCode::Char('3') => app.active_tab = 2,
                            KeyCode::Char('?') | KeyCode::Char('h') => app.toggle_help_overlay(),
                            KeyCode::Enter => {
                                if app.active_tab == 2 {
                                    app.toggle_config_option();
                                } else {
                                    app.toggle_event_modal();
                                }
                            }
                            KeyCode::Char('+') | KeyCode::Char('=') => {
                                if app.active_tab == 2 {
                                    app.increase_config_value();
                                }
                            }
                            KeyCode::Char('-') => {
                                if app.active_tab == 2 {
                                    app.decrease_config_value();
                                }
                            }
                            KeyCode::Left => {
                                if app.active_tab == 2 {
                                    app.decrease_config_value();
                                } else {
                                    app.step_backward();
                                }
                            }
                            KeyCode::Right => {
                                if app.active_tab == 2 {
                                    app.increase_config_value();
                                } else {
                                    app.step_forward();
                                }
                            }
                            KeyCode::Down | KeyCode::Char('j') => {
                                if app.active_tab == 2 {
                                    app.select_next_config();
                                } else {
                                    app.select_next_event();
                                }
                            }
                            KeyCode::Up | KeyCode::Char('k') => {
                                if app.active_tab == 2 {
                                    app.select_prev_config();
                                } else {
                                    app.select_prev_event();
                                }
                            }
                            KeyCode::Char(' ') => app.toggle_play_pause(),
                            KeyCode::Char('s') => app.cycle_speed(),
                            KeyCode::Char('t') => app.cycle_timeframe(),
                            KeyCode::Char('r') => app.reset_playhead(),
                            _ => {}
                        }
                    }
                }
            }
        } else {
            app.on_tick();
        }
    }
    Ok(())
}
