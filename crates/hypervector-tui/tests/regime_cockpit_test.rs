//! Unit tests for Quant TA & Microstructure Regime Detector Cockpit.

use hypervector_tui::{
    app::App,
    backend_telemetry::parse_backend_telemetry,
    config_view::backend_config_rows,
    data_loader::{generate_synthetic_history, parse_snapshot_json},
    model::{EngineConfig, RegimeSnapshot, RegimeState, SplitPositionMode},
};
use ratatui::{Terminal, backend::TestBackend, style::Color};

include!("support/regime_cockpit_visual.rs");
include!("support/regime_cockpit_backend.rs");
