"""The offline runtime-validation check reproduces the live runner's refusals."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tomllib

import pytest

import hypervector.operations.cohort_runtime_validation_check as check
from hypervector_supervision.cohort_supervisor_models import (
    REPOSITORY_ROOT,
    SupervisorPaths,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfigError,
    load_multi_asset_live_config,
)

CHAIN = Path("tests/fixtures/cohort_chain")
PROFILE_A = CHAIN / "profile_a.toml"
PROFILE_B = CHAIN / "profile_b.toml"
ROLLBACK_B_TO_A = CHAIN / "rollback_b_to_a.toml"
FIXTURE_PROFILES = Path("tests/fixtures/profiles")
HULK_CANARY = FIXTURE_PROFILES / "cohort_base.toml"
# Profile A keeps HYPE as a watch-only provider (execution_symbols = []) with a side
# override: the observe-only shape whose leftover sizing table broke the
# 2026-09-22 armed start.
HYPE_WATCH_ONLY_MARKER = 'execution_side_overrides = { HYPE = ["long"] }\n'
HYPE_SIZING_RESIDUE = (
    "sizing_overrides = { HYPE = { margin_fraction = 0.013, max_notional_usd = 500.0 } }\n"
)


@pytest.mark.parametrize("profile", [PROFILE_B, PROFILE_A, ROLLBACK_B_TO_A])
@pytest.mark.parametrize("mode", ["observe", "live"])
def test_chain_profiles_pass_the_runner_validator(profile: Path, mode: str) -> None:
    assert check.check(profile, mode=mode) == []


def _with_hype_sizing_residue(tmp_path: Path) -> Path:
    """Profile A with a sizing table left on its watch-only HYPE provider."""
    text = PROFILE_A.read_text()
    assert text.count(HYPE_WATCH_ONLY_MARKER) == 1
    hype = [
        provider
        for provider in load_multi_asset_live_config(
            PROFILE_A, mode="observe"
        ).providers
        if provider.symbols == ("HYPE",)
    ]
    assert len(hype) == 1 and hype[0].execution_symbols == ()
    profile = tmp_path / "broken.toml"
    profile.write_text(
        text.replace(
            HYPE_WATCH_ONLY_MARKER, HYPE_WATCH_ONLY_MARKER + HYPE_SIZING_RESIDUE
        )
    )
    return profile


def test_sizing_override_on_an_observe_only_provider_is_refused(tmp_path: Path) -> None:
    """The 2026-09-22 armed-start failure: loader and preflight accept, runner refuses."""
    profile = _with_hype_sizing_residue(tmp_path)
    load_multi_asset_live_config(profile, mode="live")
    problems = check.check(profile, mode="live")
    assert problems == [
        "provider entry sizing exceeds executable provider-symbol scope"
    ]


def test_main_exit_codes_distinguish_loader_from_runner_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["check", "--config", str(PROFILE_B), "--mode", "live"]
    )
    assert check.main() == 0
    assert "accepts" in capsys.readouterr().out
    unparseable = tmp_path / "bad.toml"
    unparseable.write_text('profile = "x"\n')
    monkeypatch.setattr("sys.argv", ["check", "--config", str(unparseable)])
    assert check.main() == 2


def test_a_missing_profile_reports_a_loader_refusal_not_a_runner_objection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 1 is reserved for "the runner would refuse this profile".

    `load_multi_asset_live_config` also raises bare FileNotFoundError and
    CohortExecutionPlanError; both escaped as a traceback with exit 1, which an
    operator or wrapper reads as a genuine runtime-validation objection.
    """
    missing = tmp_path / "absent.toml"
    monkeypatch.setattr("sys.argv", ["check", "--config", str(missing)])

    assert check.main() == 2
    assert "loader refused" in capsys.readouterr().err


def test_a_runner_objection_reports_exit_one_with_its_exact_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exit-1 branch was never asserted, so it could not be told from a crash."""
    profile = _with_hype_sizing_residue(tmp_path)
    monkeypatch.setattr("sys.argv", ["check", "--config", str(profile)])

    assert check.main() == 1
    assert (
        "runtime validator would refuse: provider entry sizing exceeds executable "
        "provider-symbol scope"
    ) in capsys.readouterr().err


def test_a_provider_contract_defect_is_a_loader_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CohortExecutionPlanError is a loader refusal, not a runner objection."""
    text = PROFILE_B.read_text()
    assert 'entry_liquidity = "taker_ioc"' in text
    broken = text.replace(
        'entry_liquidity = "taker_ioc"', 'entry_liquidity = "none"', 1
    )
    profile = tmp_path / "bad_contract.toml"
    profile.write_text(broken)
    monkeypatch.setattr("sys.argv", ["check", "--config", str(profile)])

    assert check.main() == 2
    assert "loader refused" in capsys.readouterr().err


def _write_variant(tmp_path: Path, source: Path, old: str, new: str) -> Path:
    text = source.read_text()
    assert old in text
    profile = tmp_path / f"variant_{source.name}"
    profile.write_text(text.replace(old, new))
    return profile


def _cohort_profiles() -> list[Path]:
    """Return every checked-in TOML whose runtime table declares a cohort ledger."""
    candidates = [
        *sorted(Path("configs").glob("**/*.toml")),
        *sorted(FIXTURE_PROFILES.glob("*.toml")),
        *sorted(CHAIN.glob("*.toml")),
    ]
    profiles = []
    for profile in candidates:
        with profile.open("rb") as handle:
            runtime = tomllib.load(handle).get("runtime")
        if isinstance(runtime, dict) and "cohort_ledger" in runtime:
            profiles.append(profile)
    return profiles


def _live_loadable(profiles: list[Path]) -> list[Path]:
    """Return the profiles that load in live mode; no refusal may be the stop rule."""
    loadable = []
    for profile in profiles:
        try:
            load_multi_asset_live_config(profile, mode="live")
        except MultiAssetLiveConfigError as exc:
            assert "live stop_file must be" not in str(exc), profile
            continue
        loadable.append(profile)
    return loadable


def test_every_checked_in_profile_keeps_stop_beside_the_supervised_ledger() -> None:
    """Catch a typo'd kill-switch or ledger path when the profile is authored.

    Every cohort profile must load in observe mode (a loader break fails here
    rather than skipping the profile) and keeps STOP beside its own ledger;
    every live-loadable one uses exactly the paths the supervisor watches.
    """
    profiles = _cohort_profiles()
    for profile in profiles:
        config = load_multi_asset_live_config(profile, mode="observe")
        assert config.stop_file == config.cohort_ledger.parent / "STOP", profile
    live_loadable = _live_loadable(profiles)
    for profile in live_loadable:
        check.require_supervised_paths(
            load_multi_asset_live_config(profile, mode="live")
        )

    assert {PROFILE_B, PROFILE_A, ROLLBACK_B_TO_A} <= set(live_loadable)
    assert SupervisorPaths().stop_file == SupervisorPaths().ledger.parent / "STOP"


@pytest.mark.parametrize("profile", [PROFILE_B, ROLLBACK_B_TO_A])
def test_the_live_profile_passes_the_live_path_and_collector_checks(
    profile: Path,
) -> None:
    assert check.check(profile, mode="live") == []


def test_a_ledger_the_supervisor_does_not_watch_is_refused_in_live_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A consistent but misspelt runtime directory passes the loader, not the gate."""
    profile = _write_variant(
        tmp_path,
        PROFILE_B,
        "data/live/bidirectional_cohort/",
        "data/live/bidirectional_cohrot/",
    )
    assert check.check(profile, mode="observe") == []
    monkeypatch.setattr("sys.argv", ["check", "--config", str(profile)])

    assert check.main() == 2

    error = capsys.readouterr().err
    assert "loader refused: stop_file " in error
    assert f"is not the supervisor's {SupervisorPaths().stop_file}" in error
    assert f"is not the supervisor's {SupervisorPaths().ledger}" in error


def test_supervised_path_check_names_each_divergence() -> None:
    config = load_multi_asset_live_config(PROFILE_B, mode="live")
    typo = replace(config, stop_file=Path("data/live/bidirectional_cohort/SOTP"))

    with pytest.raises(MultiAssetLiveConfigError) as raised:
        check.require_supervised_paths(typo)

    message = str(raised.value)
    assert message.startswith(
        "stop_file data/live/bidirectional_cohort/SOTP is not STOP beside "
        "cohort_ledger data/live/bidirectional_cohort/decisions.jsonl; stop_file "
    )
    assert "cohort_ledger" not in message.split("; ")[-1]


def test_a_strategy_id_without_a_default_collector_is_refused_in_live_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The armed start would refuse it only after the pre-arm checks had passed."""
    profile = _write_variant(
        tmp_path,
        PROFILE_B,
        'strategy_id = "hourly_donchian_20_10_atr20_strong_short_v1"',
        'strategy_id = "hourly_donchian_20_10_atr20_strong_shrot_v1"',
    )
    monkeypatch.setattr("sys.argv", ["check", "--config", str(profile)])

    assert check.main() == 2

    assert (
        "loader refused: default collector is not defined for provider: "
        "hourly_donchian_20_10_atr20_strong_shrot_v1"
    ) in capsys.readouterr().err


def test_live_collectors_use_the_given_backtest_lab_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lab-backed provider needs the same dependency root the armed start uses."""
    missing = tmp_path / "no-lab"
    monkeypatch.setattr(
        "sys.argv",
        ["check", "--config", str(HULK_CANARY), "--backtest-lab-root", str(missing)],
    )

    assert check.main() == 2

    assert f"backtest-lab dependency root not found: {missing}" in (
        capsys.readouterr().err
    )


def test_the_default_backtest_lab_root_does_not_depend_on_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The supervisor runs the entrypoint from the repository root; so does the check."""
    roots: list[Path] = []
    monkeypatch.setattr(
        check,
        "build_default_collector",
        lambda _provider, _config, root: roots.append(root),
    )
    monkeypatch.chdir(tmp_path)

    assert check.check(REPOSITORY_ROOT / PROFILE_B, mode="live") == []

    entrypoint_default = REPOSITORY_ROOT / ".." / "backtest-lab" / "backtest_lab"
    assert set(roots) == {entrypoint_default.resolve()}


@pytest.mark.parametrize(
    ("leverage", "venue_max_leverage", "expected_bps"),
    [(10.0, 10, 476.19), (10.0, 40, 864.20), (20.0, 20, 243.90), (8.0, 8, 588.24)],
)
def test_isolated_liquidation_distance_follows_the_maintenance_margin(
    leverage: float, venue_max_leverage: int, expected_bps: float
) -> None:
    """Maintenance is half the initial margin at the venue maximum (short side)."""
    distance = check.isolated_liquidation_distance_bps(leverage, venue_max_leverage)

    assert distance == pytest.approx(expected_bps, abs=0.01)


def test_every_checked_in_live_profile_keeps_its_stops_inside_liquidation() -> None:
    """No venue maximum the armed start tolerates can put a stop beyond liquidation."""
    live_loadable = _live_loadable(_cohort_profiles())

    assert {PROFILE_B, PROFILE_A, ROLLBACK_B_TO_A} <= set(live_loadable)
    assert {
        profile: check.liquidation_problems(profile)
        for profile in live_loadable
        if check.liquidation_problems(profile)
    } == {}


def _with_sol_leverage(tmp_path: Path, leverage: float) -> Path:
    return _write_variant(
        tmp_path,
        PROFILE_B,
        'symbol = "SOL"\nsides = ["long", "short"]\nleverage = 8.0\n',
        f'symbol = "SOL"\nsides = ["long", "short"]\nleverage = {leverage}\n',
    )


def test_a_stop_beyond_liquidation_at_a_tolerated_venue_cut_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SOL at 19x: a venue cut to 19x puts liquidation 256 bps out, inside 250 + 20."""
    profile = _with_sol_leverage(tmp_path, 19.0)
    assert check.check(profile, mode="observe") == []
    monkeypatch.setattr("sys.argv", ["check", "--config", str(profile)])

    assert check.main() == 2

    assert capsys.readouterr().err == (
        "loader refused: hourly_donchian_20_10_atr20_strong_short_v1 SOL stop 250 "
        "bps plus cost buffer 20 bps reaches its 256 bps liquidation distance at "
        "19x once the venue maximum is 19x\n"
    )


def test_a_stop_just_inside_liquidation_at_the_lowest_tolerated_venue_passes(
    tmp_path: Path,
) -> None:
    """SOL at 18x: liquidation 270.3 bps out still clears the 270 bps stop."""
    profile = _with_sol_leverage(tmp_path, 18.0)

    assert check.liquidation_problems(profile) == []
    assert check.check(profile, mode="live") == []
