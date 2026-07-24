//! Main entrypoint for Quant TA & Microstructure Regime Detector Cockpit.

use std::io;
use std::time::Duration;

use clap::Parser;
use color_eyre::Result;
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;

use hypervector_tui::{
    app::App,
    cli_args::CliArgs,
    data_loader::load_snapshots_with_metadata,
    ui,
};

fn main() -> Result<()> {
    color_eyre::install()?;
    let args = CliArgs::parse();

    let (snapshots, is_synthetic) = load_snapshots_with_metadata(&args);
    let mut app = App::new(args.symbol, args.timeframe, snapshots, args.live, is_synthetic);

    // Terminal Initialization
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let res = run_app(&mut terminal, &mut app, args.refresh_ms);

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
    refresh_ms: u64,
) -> io::Result<()> {
    while !app.should_quit {
        terminal.draw(|f| ui::draw(f, app))?;

        let timeout = Duration::from_millis((refresh_ms as f64 / app.playback_speed) as u64);
        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    if app.show_help_overlay {
                        match key.code {
                            KeyCode::Char('q') | KeyCode::Esc | KeyCode::Char('?') | KeyCode::Char('h') | KeyCode::Enter | KeyCode::Char(' ') => {
                                app.show_help_overlay = false;
                            }
                            _ => {}
                        }
                    } else if app.show_event_detail_modal {
                        match key.code {
                            KeyCode::Char('q') | KeyCode::Esc | KeyCode::Enter | KeyCode::Char(' ') => {
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
                            KeyCode::Char('4') => app.active_tab = 3,
                            KeyCode::Char('5') => app.active_tab = 4,
                            KeyCode::Char('?') | KeyCode::Char('h') => app.toggle_help_overlay(),
                            KeyCode::Enter => {
                                if app.active_tab == 4 {
                                    app.toggle_config_option();
                                } else {
                                    app.toggle_event_modal();
                                }
                            }
                            KeyCode::Char('+') | KeyCode::Char('=') => {
                                if app.active_tab == 4 {
                                    app.increase_config_value();
                                }
                            }
                            KeyCode::Char('-') => {
                                if app.active_tab == 4 {
                                    app.decrease_config_value();
                                }
                            }
                            KeyCode::Left => {
                                if app.active_tab == 4 {
                                    app.decrease_config_value();
                                } else {
                                    app.step_backward();
                                }
                            }
                            KeyCode::Right => {
                                if app.active_tab == 4 {
                                    app.increase_config_value();
                                } else {
                                    app.step_forward();
                                }
                            }
                            KeyCode::Down | KeyCode::Char('j') => {
                                if app.active_tab == 4 {
                                    app.select_next_config();
                                } else {
                                    app.select_next_event();
                                }
                            }
                            KeyCode::Up | KeyCode::Char('k') => {
                                if app.active_tab == 4 {
                                    app.select_prev_config();
                                } else {
                                    app.select_prev_event();
                                }
                            }
                            KeyCode::Char('s') => app.cycle_speed(),
                            KeyCode::Char('t') => app.cycle_timeframe(),
                            KeyCode::Char('r') => app.current_index = 0,
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
