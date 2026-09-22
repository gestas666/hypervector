"""The offline runtime-validation check reproduces the live runner's refusals."""

from __future__ import annotations

from pathlib import Path

import pytest

import cohort_runtime_validation_check as check

V90 = Path("configs/multi_asset_growth_first_5000_bankroll_builder_candidate_v90.toml")
V89 = Path("configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml")


@pytest.mark.parametrize("profile", [V90, V89])
@pytest.mark.parametrize("mode", ["observe", "live"])
def test_shipping_profiles_pass_the_runner_validator(profile: Path, mode: str) -> None:
    assert check.check(profile, mode=mode) == []


def test_sizing_override_on_an_observe_only_provider_is_refused(tmp_path: Path) -> None:
    """The 2026-09-22 armed-start failure: loader and preflight accept, runner refuses."""
    text = V90.read_text()
    marker = 'execution_symbols = []\nexecution_side_overrides = { ETH = ["long"] }\n'
    assert text.count(marker) == 1
    broken = text.replace(
        marker,
        marker
        + "sizing_overrides = { ETH = { margin_fraction = 0.02, max_notional_usd = 500.0 } }\n",
    )
    profile = tmp_path / "broken.toml"
    profile.write_text(broken)
    problems = check.check(profile, mode="live")
    assert problems == [
        "provider entry sizing exceeds executable provider-symbol scope"
    ]


def test_main_exit_codes_distinguish_loader_from_runner_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["check", "--config", str(V90), "--mode", "live"])
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
    text = V90.read_text()
    marker = 'execution_symbols = []\nexecution_side_overrides = { ETH = ["long"] }\n'
    broken = text.replace(
        marker,
        marker
        + "sizing_overrides = { ETH = { margin_fraction = 0.02, max_notional_usd = 500.0 } }\n",
    )
    profile = tmp_path / "broken.toml"
    profile.write_text(broken)
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
    text = V90.read_text()
    broken = text.replace('entry_liquidity = "taker_ioc"', 'entry_liquidity = "none"', 1)
    profile = tmp_path / "bad_contract.toml"
    profile.write_text(broken)
    monkeypatch.setattr("sys.argv", ["check", "--config", str(profile)])

    assert check.main() == 2
    assert "loader refused" in capsys.readouterr().err
