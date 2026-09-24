"""The book-level config check bounds total at-stop risk and margin (V94 plan D).

It is a configuration validation over executable routes at a stated equity, not a
trade gate: nothing here is consulted by the live runner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import cohort_runtime_validation_check as check

V93 = Path("configs/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml")
EQUITY = 4_831.0
DONCHIAN_BUDGET = 'stop_risk_budget = { maximum_loss_usd = 25.0, cost_buffer_bps = 20.0 } }\n\n[[providers]]\nstrategy_id = "hype_breakout'


def _write(tmp_path: Path, text: str, name: str = "profile.toml") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def _v93_text() -> str:
    # The copy lives outside the repo; the approval path is irrelevant to sizing.
    return (
        "\n".join(
            line
            for line in V93.read_text().splitlines()
            if not line.startswith("transition_approval")
        )
        + "\n"
    )


def _routes(result: check.BookCheck) -> dict[str, check.RouteExposure]:
    return {route.symbol: route for route in result.routes}


def test_v93_book_at_review_equity_is_inside_both_limits() -> None:
    result = check.book_check(V93, equity_usd=EQUITY)
    assert result.problems == ()
    routes = _routes(result)
    assert set(routes) == {
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:BRENTOIL",
        "xyz:TSLA",
    }
    sndk = routes["xyz:SNDK"]
    # min(4831 x 0.05 x 8, 2600) = 1932.4; 1932.4 x 270 bps = 52.17 > $25 budget.
    assert sndk.planned_notional_usd == pytest.approx(1_932.4)
    assert sndk.margin_usd == pytest.approx(241.55)
    assert sndk.stop_bps == pytest.approx(250.0)
    assert sndk.at_stop_loss_usd == pytest.approx(25.0)
    sol = routes["SOL"]
    assert sol.at_stop_loss_usd == pytest.approx(4_831 * 0.013 * 8 * 0.027)
    btc = routes["BTC"]
    # The BTC provider's fixed 60 bps stop, not the asset's inert 80 bps.
    assert btc.stop_bps == pytest.approx(60.0)
    assert btc.at_stop_loss_usd == pytest.approx(4_831 * 0.011 * 10 * 0.008)
    assert routes["HYPE"].at_stop_loss_usd == pytest.approx(25.0)
    assert result.at_stop_loss_usd == pytest.approx(
        sum(route.at_stop_loss_usd for route in result.routes)
    )
    assert result.at_stop_loss_usd / EQUITY < 0.03
    assert result.margin_usd / EQUITY < 0.25


def test_equity_fraction_budget_is_parsed_and_compounds(tmp_path: Path) -> None:
    text = _v93_text()
    assert text.count(DONCHIAN_BUDGET) == 1
    text = text.replace(
        DONCHIAN_BUDGET,
        DONCHIAN_BUDGET.replace(
            "maximum_loss_usd = 25.0", "maximum_loss_fraction_of_equity = 0.006"
        ),
    )
    profile = _write(tmp_path, text)
    sndk = _routes(check.book_check(profile, equity_usd=EQUITY))["xyz:SNDK"]
    assert sndk.stop_budget_usd == pytest.approx(0.006 * EQUITY)
    assert sndk.budget_source == "maximum_loss_fraction_of_equity"
    assert sndk.at_stop_loss_usd == pytest.approx(28.986)
    richer = _routes(check.book_check(profile, equity_usd=10_000.0))["xyz:SNDK"]
    # Notional hits the $2,600 cap: min($60 budget, 2600 x 270 bps = $70.20).
    assert richer.at_stop_loss_usd == pytest.approx(60.0)
    btc = _routes(check.book_check(profile, equity_usd=10_000.0))["BTC"]
    assert btc.budget_source == "maximum_loss_usd"


def test_both_budget_forms_take_the_smaller_as_the_runtime_does(
    tmp_path: Path,
) -> None:
    text = _v93_text().replace(
        DONCHIAN_BUDGET,
        DONCHIAN_BUDGET.replace(
            "maximum_loss_usd = 25.0",
            "maximum_loss_usd = 25.0, maximum_loss_fraction_of_equity = 0.006",
        ),
    )
    profile = _write(tmp_path, text)
    sndk = _routes(check.book_check(profile, equity_usd=EQUITY))["xyz:SNDK"]
    assert sndk.stop_budget_usd == pytest.approx(25.0)
    assert sndk.budget_source == "maximum_loss_usd"
    poorer = _routes(check.book_check(profile, equity_usd=3_000.0))["xyz:SNDK"]
    assert poorer.stop_budget_usd == pytest.approx(18.0)
    assert poorer.budget_source == "maximum_loss_fraction_of_equity"


def test_watch_only_routes_do_not_count(tmp_path: Path) -> None:
    text = _v93_text()
    for symbol in ("HYPE", "xyz:SPCX"):
        marker = f'execution_symbols = ["{symbol}"]'
        assert text.count(marker) == 1
        text = text.replace(marker, "execution_symbols = []")
    result = check.book_check(_write(tmp_path, text), equity_usd=EQUITY)
    assert set(_routes(result)) == {
        "BTC",
        "ETH",
        "SOL",
        "xyz:SNDK",
        "xyz:BRENTOIL",
        "xyz:TSLA",
    }


def _oversized_text() -> str:
    """Donchian assets at margin 0.2 with a $5,000 cap and a non-binding budget."""
    output: list[str] = []
    donchian = False
    for line in _v93_text().splitlines():
        if line.startswith("symbol = "):
            donchian = line.split('"')[1] in {
                "SOL",
                "xyz:SNDK",
                "xyz:BRENTOIL",
                "xyz:TSLA",
            }
        elif donchian and line.startswith("margin_fraction"):
            line = "margin_fraction = 0.2"
        elif donchian and line.startswith("max_notional_usd"):
            line = "max_notional_usd = 5000.0"
        output.append(line)
    text = "\n".join(output) + "\n"
    assert text.count(DONCHIAN_BUDGET) == 1
    return text.replace(
        DONCHIAN_BUDGET,
        DONCHIAN_BUDGET.replace("maximum_loss_usd = 25.0", "maximum_loss_usd = 250.0"),
    )


def test_book_over_the_risk_and_margin_limits_fails_with_a_clear_message(
    tmp_path: Path,
) -> None:
    result = check.book_check(_write(tmp_path, _oversized_text()), equity_usd=EQUITY)
    # Four $5,000 Donchian routes lose min($250, 5000 x 270 bps) = $135 each.
    assert _routes(result)["xyz:SNDK"].at_stop_loss_usd == pytest.approx(135.0)
    assert len(result.problems) == 2
    risk, margin = result.problems
    assert "at-stop risk" in risk and "exceeds 3.00% of equity" in risk
    assert "margin" in margin and "exceeds 25.00% of equity" in margin


def test_maximum_positions_sums_only_the_largest_routes(tmp_path: Path) -> None:
    text = _v93_text().replace("maximum_positions = 8", "maximum_positions = 2")
    result = check.book_check(_write(tmp_path, text), equity_usd=EQUITY)
    losses = sorted((route.at_stop_loss_usd for route in result.routes), reverse=True)
    margins = sorted((route.margin_usd for route in result.routes), reverse=True)
    assert result.at_stop_loss_usd == pytest.approx(sum(losses[:2]))
    assert result.margin_usd == pytest.approx(sum(margins[:2]))


def test_non_positive_equity_is_refused() -> None:
    with pytest.raises(ValueError, match="equity"):
        check.book_check(V93, equity_usd=0.0)


def test_main_prints_the_book_table_when_equity_is_given(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["check", "--config", str(V93), "--mode", "live", "--equity", "4831"],
    )
    assert check.main() == 0
    out = capsys.readouterr().out
    assert "accepts" in out
    assert "xyz:SNDK" in out
    assert "book at-stop risk" in out


def test_main_exit_three_when_the_book_exceeds_its_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = _write(tmp_path, _oversized_text())
    monkeypatch.setattr(
        "sys.argv", ["check", "--config", str(profile), "--equity", "4831"]
    )
    assert check.main() == 3
    captured = capsys.readouterr()
    assert "book-level check would refuse" in captured.err
    assert "xyz:SNDK" in captured.out
