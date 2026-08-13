from argparse import Namespace
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from requests import HTTPError


def test_funding_request_covers_the_current_hour_from_frozen_cutoff() -> None:
    module = _module()

    request = module._funding_request(  # type: ignore[attr-defined]
        datetime(2026, 8, 4, 19, 30, tzinfo=timezone.utc)
    )

    assert request.start == datetime(2026, 8, 4, 18, 0, tzinfo=timezone.utc)
    assert request.end == datetime(2026, 8, 4, 20, 0, tzinfo=timezone.utc)


def test_target20_experiment_has_a_new_prospective_cutoff() -> None:
    module = _module()

    experiment = module._experiment("v3-target20")  # type: ignore[attr-defined]

    assert experiment.candidate_strategy_id == (
        "hype_breakout_relaxed_target20_60m_bidirectional_v3"
    )
    assert experiment.cutoff_time_ms == 1_785_872_820_000
    assert experiment.target_proxy_bps == 20.0


def test_fixed_matched_experiment_reuses_target20_cutoff_without_target() -> None:
    """Matched-entry evidence must isolate exit policy from entry timing."""
    module = _module()

    experiment = module._experiment("v4-fixed-matched")  # type: ignore[attr-defined]

    assert experiment.candidate_strategy_id == (
        "hype_breakout_relaxed_fixed60_matched_bidirectional_v4"
    )
    assert experiment.cutoff_time_ms == 1_785_872_820_000
    assert experiment.target_proxy_bps is None


def test_btc_structural_experiment_has_a_fresh_independent_contract() -> None:
    """BTC continuation must not inherit HYPE identity or stop geometry."""
    module = _module()

    experiment = module._experiment(  # type: ignore[attr-defined]
        "v5-btc-structural-fixed"
    )

    assert experiment.candidate_strategy_id == (
        "btc_structural_continuation_fixed60_bidirectional_v1"
    )
    assert experiment.source_strategy_id == "range_onset_bidirectional_v1"
    assert experiment.symbol == "BTC"
    assert experiment.blocker == "awaiting_hourly_sma_cross"
    assert experiment.cutoff_time_ms == 1_785_886_080_000
    assert experiment.stop_proxy_bps == 60.0
    assert experiment.target_proxy_bps is None


def test_hype_hulk_squeeze_experiment_has_a_fresh_prospective_contract() -> None:
    """HYPE Hulk relaxation must start after discovery with bounded proxy risk."""
    module = _module()

    experiment = module._experiment(  # type: ignore[attr-defined]
        "v6-hype-hulk-squeeze-fixed"
    )

    assert experiment.candidate_strategy_id == (
        "hype_hulk_squeeze_relaxed_fixed60_bidirectional_v1"
    )
    assert experiment.source_strategy_id == "hulk_expansion_bidirectional_tuned_v2"
    assert experiment.symbol == "HYPE"
    assert experiment.blocker == "squeeze_not_armed"
    assert experiment.cutoff_time_ms == 1_785_891_480_000
    assert experiment.source_stop_policy == "structural_clamped_bps"
    assert experiment.source_stop_range_bps == (20.0, 75.0)
    assert experiment.stop_proxy_bps == 75.0
    assert experiment.target_proxy_bps is None


def test_hype_range_absorption_experiment_is_frozen_after_hypothesis_selection() -> (
    None
):
    """The opposed-OPI range challenger must exclude hypothesis-formation data."""
    module = _module()

    experiment = module._experiment(  # type: ignore[attr-defined]
        "v7-hype-range-absorption-fixed"
    )

    assert experiment.candidate_strategy_id == (
        "hype_range_absorption_fixed60_bidirectional_v1"
    )
    assert experiment.source_strategy_id == "range_onset_bidirectional_v1"
    assert experiment.symbol == "HYPE"
    assert experiment.blocker == "awaiting_hourly_sma_cross"
    assert experiment.cutoff_time_ms == 1_785_894_300_000
    assert experiment.stop_proxy_bps == 60.0
    assert experiment.opi_cohort == "opposed"


def test_sol_aligned_range_experiment_starts_after_its_discovery_window() -> None:
    """The SOL observer must freeze identity, aligned OPI, and future cutoff."""
    module = _module()

    experiment = module._experiment(  # type: ignore[attr-defined]
        "v8-sol-aligned-range-fixed"
    )

    assert experiment.candidate_strategy_id == (
        "sol_aligned_range_relaxed_fixed60_bidirectional_v1"
    )
    assert experiment.source_strategy_id == "range_onset_bidirectional_v1"
    assert experiment.symbol == "SOL"
    assert experiment.blocker == "awaiting_hourly_sma_cross"
    assert experiment.cutoff_time_ms == 1_785_901_500_000
    assert experiment.funding_start_time_ms == 1_785_901_500_000
    assert experiment.source_stop_policy == "fixed_bps"
    assert experiment.stop_proxy_bps == 60.0
    assert experiment.target_proxy_bps is None
    assert experiment.opi_cohort == "aligned"
    assert experiment.notional_usd == 75.0

    config = module.load_multi_asset_live_config(  # type: ignore[attr-defined]
        Path("configs/multi_asset_bidirectional_canary.toml"), mode="observe"
    )
    spec = module._frozen_spec(config, experiment)  # type: ignore[attr-defined]
    assert spec.execution_contract().as_payload()["opi_cohort"] == "aligned"
    assert spec.notional_usd == 75.0


def test_btc_hulk_flow_experiment_starts_after_hypothesis_selection() -> None:
    """BTC Hulk relaxation must measure only future paths at deployed sizing."""
    module = _module()

    experiment = module._experiment(  # type: ignore[attr-defined]
        "v9-btc-hulk-flow-fixed"
    )

    assert experiment.candidate_strategy_id == (
        "btc_hulk_money_flow_relaxed_fixed60_bidirectional_v1"
    )
    assert experiment.source_strategy_id == "hulk_expansion_bidirectional_tuned_v2"
    assert experiment.symbol == "BTC"
    assert experiment.blocker == "money_flow_not_aligned"
    assert experiment.cutoff_time_ms == 1_785_945_000_000
    assert experiment.funding_start_time_ms == 1_785_945_000_000
    assert experiment.source_stop_policy == "structural_clamped_bps"
    assert experiment.source_stop_range_bps == (20.0, 75.0)
    assert experiment.stop_proxy_bps == 75.0
    assert experiment.target_proxy_bps is None
    assert experiment.opi_cohort == "all"
    assert experiment.notional_usd == 25.0

    config = module.load_multi_asset_live_config(  # type: ignore[attr-defined]
        Path("configs/multi_asset_bidirectional_canary.toml"), mode="observe"
    )
    spec = module._frozen_spec(config, experiment)  # type: ignore[attr-defined]
    assert spec.execution_contract().as_payload()["opi_cohort"] == "all"
    assert spec.notional_usd == 25.0


def test_hype_aligned_breakout_relaxation_starts_after_v14_discovery() -> None:
    """HYPE aligned-book evidence must exclude the matrix that selected it."""
    module = _module()

    experiment = module._experiment(  # type: ignore[attr-defined]
        "v10-hype-aligned-breakout-relaxation-fixed"
    )

    assert experiment.candidate_strategy_id == (
        "hype_aligned_book_breakout_relaxation_fixed60_bidirectional_v1"
    )
    _assert_aligned_breakout_experiment(experiment, symbol="HYPE")


def test_spcx_swing_pivot_relaxation_starts_after_v25_discovery() -> None:
    """The HIP-3 pivot challenger must freeze exact identity after discovery."""
    module = _module()

    experiment = module._experiment(  # type: ignore[attr-defined]
        "v13-spcx-swing-pivot-fixed"
    )

    assert experiment.candidate_strategy_id == (
        "spcx_swing_pivot_relaxed_fixed60_bidirectional_v1"
    )
    assert experiment.source_strategy_id == (
        "hip3_swing_ha_sp500_spcx_bidirectional_v2"
    )
    assert experiment.symbol == "xyz:SPCX"
    assert experiment.blocker == "pivot_break_state_missing"
    assert experiment.cutoff_time_ms == 1_786_204_800_000
    assert experiment.funding_start_time_ms == 1_786_204_800_000
    assert experiment.source_stop_policy == "fixed_bps"
    assert experiment.stop_proxy_bps == 80.0
    assert experiment.target_proxy_bps is None
    assert experiment.opi_cohort == "aligned"
    assert experiment.notional_usd == 75.0
    assert experiment.source_authority == "executable"

    config = module.load_multi_asset_live_config(  # type: ignore[attr-defined]
        Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml"),
        mode="observe",
    )
    spec = module._frozen_spec(config, experiment)  # type: ignore[attr-defined]
    contract = spec.execution_contract().as_payload()
    assert contract["symbol"] == "xyz:SPCX"
    assert contract["minimum_available_time_ms"] == 1_786_204_800_000


def test_sol_aligned_breakout_relaxation_starts_after_v14_discovery() -> None:
    """SOL aligned-book evidence must exclude the matrix that selected it."""
    module = _module()

    experiment = module._experiment(  # type: ignore[attr-defined]
        "v11-sol-aligned-breakout-relaxation-fixed"
    )

    assert experiment.candidate_strategy_id == (
        "sol_aligned_book_breakout_relaxation_fixed60_bidirectional_v1"
    )
    _assert_aligned_breakout_experiment(experiment, symbol="SOL")

    config = module.load_multi_asset_live_config(  # type: ignore[attr-defined]
        Path(
            "configs/"
            "multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
        ),
        mode="observe",
    )
    spec = module._frozen_spec(config, experiment)  # type: ignore[attr-defined]
    assert spec.execution_contract().as_payload()["opi_cohort"] == "aligned"
    assert spec.notional_usd == 75.0


def _assert_aligned_breakout_experiment(experiment: object, *, symbol: str) -> None:
    """Assert the shared prospective contract for aligned breakout relaxations."""
    assert experiment.source_strategy_id == "hype_breakout_onset_bidirectional_v1"  # type: ignore[attr-defined]
    assert experiment.symbol == symbol  # type: ignore[attr-defined]
    assert experiment.blocker == "5m_not_breakout"  # type: ignore[attr-defined]
    assert experiment.cutoff_time_ms == 1_786_054_080_000  # type: ignore[attr-defined]
    assert experiment.funding_start_time_ms == 1_786_054_080_000  # type: ignore[attr-defined]
    assert experiment.source_stop_policy == "fixed_bps"  # type: ignore[attr-defined]
    assert experiment.source_stop_range_bps is None  # type: ignore[attr-defined]
    assert experiment.stop_proxy_bps == 80.0  # type: ignore[attr-defined]
    assert experiment.target_proxy_bps is None  # type: ignore[attr-defined]
    assert experiment.opi_cohort == "aligned"  # type: ignore[attr-defined]
    assert experiment.notional_usd == 75.0  # type: ignore[attr-defined]


def test_parser_accepts_the_frozen_target20_experiment() -> None:
    module = _module()

    args = module._parser().parse_args(  # type: ignore[attr-defined]
        [
            "--ledger-root",
            "data/live/bidirectional_cohort",
            "--config",
            "configs/multi_asset_bidirectional_canary.toml",
            "--matrix-template",
            "matrix.json",
            "--out",
            "target.json",
            "--run-id",
            "run-1",
            "--experiment",
            "v3-target20",
        ]
    )

    assert args.experiment == "v3-target20"


def test_parser_accepts_the_fixed_matched_experiment() -> None:
    module = _module()

    args = module._parser().parse_args(  # type: ignore[attr-defined]
        [
            "--ledger-root",
            "data/live/bidirectional_cohort",
            "--config",
            "configs/multi_asset_bidirectional_canary.toml",
            "--matrix-template",
            "matrix.json",
            "--out",
            "fixed-matched.json",
            "--run-id",
            "run-1",
            "--experiment",
            "v4-fixed-matched",
        ]
    )

    assert args.experiment == "v4-fixed-matched"


def test_parser_accepts_the_btc_structural_experiment() -> None:
    module = _module()

    args = module._parser().parse_args(  # type: ignore[attr-defined]
        [
            "--ledger-root",
            "data/live/bidirectional_cohort",
            "--config",
            "configs/multi_asset_bidirectional_canary.toml",
            "--matrix-template",
            "matrix.json",
            "--out",
            "btc-structural.json",
            "--run-id",
            "run-1",
            "--experiment",
            "v5-btc-structural-fixed",
        ]
    )

    assert args.experiment == "v5-btc-structural-fixed"


def test_parser_accepts_the_hype_hulk_squeeze_experiment() -> None:
    module = _module()

    args = module._parser().parse_args(  # type: ignore[attr-defined]
        [
            "--ledger-root",
            "data/live/bidirectional_cohort",
            "--config",
            "configs/multi_asset_bidirectional_canary.toml",
            "--matrix-template",
            "matrix.json",
            "--out",
            "hype-hulk-squeeze.json",
            "--run-id",
            "run-1",
            "--experiment",
            "v6-hype-hulk-squeeze-fixed",
        ]
    )

    assert args.experiment == "v6-hype-hulk-squeeze-fixed"


def test_frozen_target20_spec_carries_target_and_cutoff() -> None:
    module = _module()
    config = module.load_multi_asset_live_config(  # type: ignore[attr-defined]
        Path("configs/multi_asset_bidirectional_canary.toml"), mode="observe"
    )
    experiment = module._experiment("v3-target20")  # type: ignore[attr-defined]

    spec = module._frozen_spec(config, experiment)  # type: ignore[attr-defined]

    assert spec.cutoff_time_ms == experiment.cutoff_time_ms
    assert spec.target_proxy_bps == 20.0


def test_frozen_btc_structural_spec_uses_btc_range_source_geometry() -> None:
    """The forward observer must isolate one BTC entry blocker at fixed risk."""
    module = _module()
    config = module.load_multi_asset_live_config(  # type: ignore[attr-defined]
        Path("configs/multi_asset_bidirectional_canary.toml"), mode="observe"
    )
    experiment = module._experiment(  # type: ignore[attr-defined]
        "v5-btc-structural-fixed"
    )

    spec = module._frozen_spec(config, experiment)  # type: ignore[attr-defined]

    assert spec.strategy_id == "range_onset_bidirectional_v1"
    assert spec.symbol == "BTC"
    assert spec.blocker == "awaiting_hourly_sma_cross"
    assert spec.cutoff_time_ms == experiment.cutoff_time_ms
    assert spec.stop_proxy_bps == 60.0
    assert spec.target_proxy_bps is None


def test_frozen_hype_hulk_spec_validates_structural_source_and_fixed_proxy() -> None:
    """The candidate proxy must retain the deployed Hulk structural bounds."""
    module = _module()
    config = module.load_multi_asset_live_config(  # type: ignore[attr-defined]
        Path("configs/multi_asset_bidirectional_canary.toml"), mode="observe"
    )
    experiment = module._experiment(  # type: ignore[attr-defined]
        "v6-hype-hulk-squeeze-fixed"
    )

    spec = module._frozen_spec(config, experiment)  # type: ignore[attr-defined]

    assert spec.strategy_id == "hulk_expansion_bidirectional_tuned_v2"
    assert spec.symbol == "HYPE"
    assert spec.blocker == "squeeze_not_armed"
    assert spec.cutoff_time_ms == experiment.cutoff_time_ms
    assert spec.stop_proxy_bps == 75.0
    assert spec.target_proxy_bps is None


def test_frozen_hype_range_absorption_spec_keeps_both_sides_and_opposed_opi() -> None:
    """The new observer changes only the declared blocker and OPI cohort."""
    module = _module()
    config = module.load_multi_asset_live_config(  # type: ignore[attr-defined]
        Path("configs/multi_asset_bidirectional_canary.toml"), mode="observe"
    )
    experiment = module._experiment(  # type: ignore[attr-defined]
        "v7-hype-range-absorption-fixed"
    )

    spec = module._frozen_spec(config, experiment)  # type: ignore[attr-defined]

    assert spec.strategy_id == "range_onset_bidirectional_v1"
    assert spec.symbol == "HYPE"
    assert spec.stop_proxy_bps == 60.0
    assert spec.opi_cohort == "opposed"
    assert spec.execution_contract().as_payload()["opi_cohort"] == "opposed"


def test_btc_structural_funding_request_starts_at_its_frozen_hour() -> None:
    module = _module()
    experiment = module._experiment(  # type: ignore[attr-defined]
        "v5-btc-structural-fixed"
    )

    request = module._funding_request(  # type: ignore[attr-defined]
        datetime(2026, 8, 4, 23, 45, tzinfo=timezone.utc), experiment
    )

    assert request.symbol == "BTC"
    assert request.start == datetime(2026, 8, 4, 23, 0, tzinfo=timezone.utc)
    assert request.end == datetime(2026, 8, 5, 0, 0, tzinfo=timezone.utc)


def test_once_mode_reports_rate_limit_without_overwriting_or_retrying() -> None:
    module = _module()

    def fail(_: Namespace) -> dict[str, object]:
        raise HTTPError("429")

    module._publish = fail  # type: ignore[attr-defined]

    assert module.run(Namespace(interval_seconds=300.0, once=True)) == 2  # type: ignore[attr-defined]


def test_asset_selection_requires_one_matching_identity_per_compatible_run() -> None:
    module = _module()
    records = [
        _asset_row("configuration_identity", "run-a", "asset-profile"),
        _asset_row("book_observation", "run-a", "asset-profile"),
        _asset_row("configuration_identity", "run-b", "other-profile"),
        _asset_row("book_observation", "run-b", "other-profile"),
        _asset_row("configuration_identity", "run-c", "asset-profile"),
        _asset_row("book_observation", "run-c", "asset-profile"),
    ]

    selected = module._select_compatible_asset_records(  # type: ignore[attr-defined]
        records, ("run-a", "run-c")
    )

    assert {row["run_id"] for row in selected} == {"run-a", "run-c"}


def test_asset_selection_rejects_profile_drift_between_compatible_runs() -> None:
    module = _module()
    records = [
        _asset_row("configuration_identity", "run-a", "asset-profile-a"),
        _asset_row("configuration_identity", "run-c", "asset-profile-c"),
    ]

    try:
        module._select_compatible_asset_records(  # type: ignore[attr-defined]
            records, ("run-a", "run-c")
        )
    except ValueError as exc:
        assert "asset execution identity changed" in str(exc)
    else:
        raise AssertionError("asset profile drift was accepted")


def _module() -> ModuleType:
    path = Path("scripts/cohort_forward_one_blocker_challenger.py")
    spec = spec_from_file_location("cohort_forward_one_blocker_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("forward challenger script cannot be loaded")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _asset_row(
    event_type: str, source_run_id: str, fingerprint: str
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "run_id": source_run_id,
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "asset-profile-id",
        "profile_fingerprint": fingerprint,
        "run_fingerprint": "asset-run-fingerprint",
        "payload": {"symbol": "HYPE"},
    }
