//! hypervector-tui binary — read-only condensed financial ops terminal.

use clap::Parser;
use color_eyre::eyre::Result;
use hypervector_tui::app::App;
use hypervector_tui::cli_args::CliArgs;

fn main() -> Result<()> {
    color_eyre::install()?;
    let args = CliArgs::parse();

    let mut terminal = ratatui::init();
    let app_result = App::new(args).run(&mut terminal);
    ratatui::restore();
    app_result
}
