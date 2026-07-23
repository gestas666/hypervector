//! File and CLI adapters (read-only).

pub mod paths;

mod cli_probe;
mod jsonl;

pub use cli_probe::{
    load_fixture_json, probe_json, probe_status, AllowedSubcommand, CLI_ALLOWLIST, CLI_FORBIDDEN,
};
pub use jsonl::load_decision_rows;
pub use paths::{assert_ledger_segment, decisions_path, resolve_tape_path, PathError};
