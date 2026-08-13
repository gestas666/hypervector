//! BTC 5m source-follow backend acceptance tests for the read-only TUI.

use hypervector_tui::{
    App, backend_telemetry::parse_backend_telemetry, config_view::backend_config_rows,
};
use ratatui::{Terminal, backend::TestBackend};

include!("support/btc_source_follow_contract.rs");
include!("support/btc_source_follow_measured.rs");
