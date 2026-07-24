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
                    match key.code {
                        KeyCode::Char('q') | KeyCode::Esc => app.should_quit = true,
                        KeyCode::Char(' ') => app.toggle_play_pause(),
                        KeyCode::Left => app.step_backward(),
                        KeyCode::Right => app.step_forward(),
                        KeyCode::Char('s') => app.cycle_speed(),
                        KeyCode::Char('t') => app.cycle_timeframe(),
                        KeyCode::Char('r') => app.current_index = 0,
                        _ => {}
                    }
                }
            }
        } else {
            app.on_tick();
        }
    }
    Ok(())
}
