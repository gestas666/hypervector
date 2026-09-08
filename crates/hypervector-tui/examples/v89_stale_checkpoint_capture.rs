//! Render a frozen stale incident through the normal read-only telemetry source.

use std::{env, fs, path::Path};

use hypervector_tui::{
    App,
    backend_telemetry::{BackendConnectionState, BackendTelemetrySource},
};
use ratatui::{Terminal, backend::TestBackend};

fn main() -> Result<(), String> {
    let args: Vec<String> = env::args().collect();
    let [_, ledger, checkpoint, output]: [String; 4] = args.try_into().map_err(|_| {
        "Usage: v89_stale_checkpoint_capture FROZEN_LEDGER FROZEN_CHECKPOINT NEW_OUTPUT_DIR"
            .to_string()
    })?;
    let mut source =
        BackendTelemetrySource::with_checkpoint_path(ledger.into(), Some(checkpoint.into()));
    let snapshot = source.refresh();
    if snapshot.connection != BackendConnectionState::Stale
        || !snapshot.cohort_checkpoint.available
        || !snapshot.cohort_checkpoint.stale
    {
        return Err(format!(
            "Capture requires an available, stale checkpoint and stale backend: {}",
            snapshot.status_message
        ));
    }
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.detached_lifecycle = true;
    app.apply_backend_telemetry(snapshot);
    let output = Path::new(&output);
    fs::create_dir(output).map_err(|error| format!("Create new capture directory: {error}"))?;
    for (width, height) in [(100, 28), (120, 36), (160, 45)] {
        for tab in 0..9 {
            app.active_tab = tab;
            let screen = render(&app, width, height)?;
            let path = output.join(format!("view-{}-{width}x{height}.txt", tab + 1));
            fs::write(&path, screen)
                .map_err(|error| format!("Write {}: {error}", path.display()))?;
        }
    }
    println!("Rendered 27 frozen-data views; execution_authority=none");
    Ok(())
}

fn render(app: &App, width: u16, height: u16) -> Result<String, String> {
    let mut terminal = Terminal::new(TestBackend::new(width, height))
        .map_err(|error| format!("Create headless terminal: {error}"))?;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .map_err(|error| format!("Render frozen view: {error}"))?;
    let buffer = terminal.backend().buffer();
    Ok((0..height)
        .map(|y| {
            (0..width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n"))
}
