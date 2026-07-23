//! hypervector-tui — read-only condensed financial ops terminal.
//!
//! Projects CLI/ledger truth (status, gates, KPIs, decision tape, regime).
//! No second strategy brain. No start/stop/arm. No secret values on screen.

pub mod app;
pub mod cli_args;
pub mod model;
pub mod read;
pub mod theme;
pub mod ui;

pub use app::{App, View};
pub use cli_args::{CliArgs, TapeMode};
