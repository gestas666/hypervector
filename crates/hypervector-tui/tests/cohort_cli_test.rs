use clap::Parser;
use hypervector_tui::CliArgs;

#[test]
fn cli_accepts_an_explicit_read_only_checkpoint_path() {
    let args = CliArgs::try_parse_from([
        "tui-regime-detector",
        "--backend-ledger",
        "data/live/bidirectional_cohort/decisions.jsonl",
        "--cohort-checkpoint",
        "data/runtime/bidirectional_cohort/latest_checkpoint.json",
    ])
    .expect("checkpoint argument");

    assert_eq!(
        args.cohort_checkpoint
            .expect("configured checkpoint")
            .to_string_lossy(),
        "data/runtime/bidirectional_cohort/latest_checkpoint.json"
    );
}

#[test]
fn cli_accepts_an_explicit_growth_preflight_path() {
    let args = CliArgs::try_parse_from([
        "tui-regime-detector",
        "--growth-preflight",
        "data/runtime/bidirectional_cohort/latest_growth_5000_preflight.json",
    ])
    .expect("growth preflight argument");

    assert_eq!(
        args.growth_preflight
            .expect("configured growth preflight")
            .to_string_lossy(),
        "data/runtime/bidirectional_cohort/latest_growth_5000_preflight.json"
    );
}

#[test]
fn cli_accepts_router_as_the_initial_operator_screen() {
    let args = CliArgs::try_parse_from(["tui-regime-detector", "--initial-tab", "2"])
        .expect("initial tab argument");

    assert_eq!(args.initial_tab, 2);
    assert!(CliArgs::try_parse_from(["tui-regime-detector", "--initial-tab", "8",]).is_ok());
    assert!(CliArgs::try_parse_from(["tui-regime-detector", "--initial-tab", "9",]).is_ok());
    assert!(CliArgs::try_parse_from(["tui-regime-detector", "--initial-tab", "10",]).is_err());
}

#[test]
fn cli_accepts_an_explicit_detached_lifecycle() {
    let args = CliArgs::try_parse_from(["tui-regime-detector", "--detached-lifecycle"])
        .expect("detached-lifecycle argument");

    assert!(args.detached_lifecycle);
}
