"""The ladder power table applies each rule exactly and reproduces its draws."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import cohort_ladder_evidence as ladder
import ladder_power_table as power

HORIZON = 150


def _paths(*rows: list[float]) -> np.ndarray:
    """Pad each hand-written path to the 150-close horizon with +1R closes."""
    return np.array(
        [row + [1.0] * (HORIZON - len(row)) for row in rows], dtype=np.float64
    )


def _flags(
    r: np.ndarray, usd: np.ndarray | None = None, equity_per_r: float = 0.001
) -> dict[str, np.ndarray]:
    return power.evaluate_rules(
        r, r if usd is None else usd, np.full_like(r, equity_per_r)
    )


def test_current_rule_samples_the_first_thirty_closes_once() -> None:
    # Row 0 passes at 30. Row 1 fails at 30 (mean R < 0), then recovers by 60.
    r = _paths([0.5] * 30, [-0.2] * 30 + [1.0] * 30)
    flags = _flags(r)
    assert flags["current_advance_30"].tolist() == [True, False]
    assert flags["current_advance_90"].tolist() == [True, False]
    assert flags["proposed_advance_30"].tolist() == [True, False]
    assert flags["proposed_advance_60"].tolist() == [True, True]


def test_current_gates_ex_top_three_in_dollars_and_proposed_in_r() -> None:
    # Three big-dollar, small-R winners carry the USD sum; R ex-top-3 is positive.
    row = [0.2] * 3 + [0.3] * 10 + [-0.1] * 17
    usd_row = [100.0] * 3 + [0.3] * 10 + [-1.0] * 17
    r = _paths(row)
    usd = _paths(usd_row)
    flags = _flags(r, usd)
    assert not flags["current_advance_30"][0]
    assert flags["proposed_advance_30"][0]


def test_conservative_rule_needs_a_cumulative_t_of_one_point_six() -> None:
    # +0.5/-0.3 alternating: mean 0.1, t about 1.35 at 30 and 1.9 at 60.
    r = _paths([0.5, -0.3] * 45)
    flags = _flags(r)
    assert not flags["conservative_advance_30"][0]
    assert flags["conservative_advance_60"][0]
    assert flags["proposed_advance_30"][0]


def test_zero_spread_blocks_agree_with_the_ladder_evidence_tool() -> None:
    """A uniform block has t = +/-inf here and no t in the evidence tool; both
    tools must still reach the same conservative and step-down verdicts."""
    for value in (0.5, 0.0, -0.5):
        rows = [
            {
                "status": "closed",
                "net_usd": value * 10,
                "r_multiple": value,
                "capped": {
                    "status": "not_capped",
                    "net_usd": value * 10,
                    "r_multiple": value,
                },
            }
        ] * 50
        evidence = ladder.evaluate_proposed_ladder(rows, [])
        flags = _flags(np.full((1, HORIZON), value))
        conservative = evidence["advance"]["looks"][0]["conservative_status"] == "met"
        assert bool(flags["conservative_advance_30"][0]) == conservative
        stepped = evidence["step_down"]["looks"][0]["status"] == "triggered"
        # One look at 50 closes: the power table checks 50, 100 and 150.
        assert bool(flags["step_down_t"][0]) == stepped


def test_one_bad_window_steps_down_only_under_the_current_rule() -> None:
    middle = [0.5] * 25 + [-0.1] * 50 + [0.5] * 75
    losing = [-0.5, 0.3] * 25
    flags = _flags(_paths(middle, losing))
    assert flags["step_down_window"].tolist() == [True, True]
    assert flags["step_down_t"].tolist() == [False, True]
    assert flags["current_step_down"].tolist() == [True, True]
    assert flags["proposed_step_down"].tolist() == [False, True]


def test_the_twelve_percent_drawdown_uses_rung_one_equity_per_r() -> None:
    # Thirteen straight -1R closes at 1% of equity per R cross -12% (0.99^13).
    r = _paths([-1.0] * 13 + [3.0] * 10, [-1.0] * 12 + [3.0] * 10)
    flags = _flags(r, equity_per_r=0.01)
    assert flags["step_down_drawdown"].tolist() == [True, False]
    assert flags["proposed_step_down"][0]


def test_paths_shorter_than_the_horizon_are_refused() -> None:
    with pytest.raises(ValueError):
        power.evaluate_rules(np.zeros((1, 90)), np.zeros((1, 90)), np.zeros((1, 90)))


def _pool(values: list[float], symbol: str = "SOL") -> power.Pool:
    trades = tuple(
        power.Trade(symbol, value, f"{index}") for index, value in enumerate(values)
    )
    return power.Pool("test", trades, "synthetic")


def test_the_edge_shift_moves_only_the_mean() -> None:
    # A constant pool becomes exactly the edge after centering: every path is
    # the same, so each rule is certain.
    pool = _pool([2.0] * 7)
    up = power.simulate(pool, 0.1, simulations=64, seed=1, stream=(0, 0))
    assert up["current_advance_30"] == 1.0
    assert up["proposed_advance_30"] == 1.0
    assert up["conservative_advance_30"] == 1.0
    assert up["proposed_step_down"] == 0.0
    down = power.simulate(pool, -0.1, simulations=64, seed=1, stream=(0, 0))
    assert down["proposed_advance_90"] == 0.0
    assert down["current_step_down"] == 1.0
    assert down["step_down_t"] == 1.0


def test_the_table_is_deterministic_for_a_seed() -> None:
    pool = _pool([-1.0, -1.0, -0.5, 0.2, 0.4, 2.5, 5.0], symbol="xyz:SNDK")
    first = power.build_table([pool], edges=(0.0, 0.2), simulations=3_000, seed=7)
    again = power.build_table([pool], edges=(0.0, 0.2), simulations=3_000, seed=7)
    other = power.build_table([pool], edges=(0.0, 0.2), simulations=3_000, seed=8)
    assert first["pools"] == again["pools"]
    assert first["pools"] != other["pools"]
    rows = first["pools"]["test"]["table"]
    assert (
        rows[1]["proposed"]["p_advance"]["90"] > rows[0]["proposed"]["p_advance"]["90"]
    )
    # One pool's draws do not depend on the other edges that were requested.
    alone = power.build_table([pool], edges=(0.0,), simulations=3_000, seed=7)
    assert alone["pools"]["test"]["table"][0] == rows[0]


def test_a_row_does_not_depend_on_the_other_pools_or_edges_in_the_run() -> None:
    research = power.Pool(
        "research",
        tuple(
            power.Trade("xyz:SNDK", value, str(index))
            for index, value in enumerate([-1.0, -1.0, -0.5, 0.2, 0.4, 2.5, 5.0])
        ),
        "synthetic",
    )
    live = power.Pool("live", (power.Trade("SOL", 0.3, "x"),), "synthetic")
    alone = power.build_table([research], edges=(0.2,), simulations=2_000, seed=7)
    # The research pool now runs second and 0.2 sits at a different edge index.
    behind = power.build_table(
        [live, research], edges=(-0.1, 0.2), simulations=2_000, seed=7
    )
    assert (
        alone["pools"]["research"]["table"][0]
        == (behind["pools"]["research"]["table"][1])
    )
    # Streams are named by identity: -0.0 and 0.0 are the same edge.
    assert power.draw_stream("research", -0.0) == power.draw_stream("research", 0.0)
    assert power.draw_stream("research", 0.1) != power.draw_stream("live", 0.1)
    assert power.draw_stream("research", 0.1) != power.draw_stream("research", 0.2)


def test_rung_weights_follow_the_ladder_doc() -> None:
    assert power.RUNG0_USD_PER_R["xyz:SNDK"] == pytest.approx(1_288.27 * 0.0185)
    assert power.RUNG1_EQUITY_PER_R["SOL"] == pytest.approx(1_159.44 * 0.021 / 4_831)
    pool = _pool([0.0, 1.0], symbol="BTC")
    fallback = np.mean(list(power.RUNG0_USD_PER_R.values()))
    assert pool.weights(power.RUNG0_USD_PER_R).tolist() == pytest.approx([fallback] * 2)


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    live = tmp_path / "closed_trades.csv"
    pd.DataFrame(
        {
            "coin": ["SOL", "xyz:SNDK", "BTC", "xyz:TSLA"],
            "strategy_id": [
                "hourly_donchian_20_10_atr20_bidirectional_v1",
                "hourly_donchian_20_10_atr20_strong_short_v1",
                "liquidity_sweep_long_1h_stop60_target60_v2",
                "hourly_donchian_8_4_atr20_bidirectional_v1",
            ],
            "entry_oid": [1, 2, 3, 4],
            "R": [-1.0, 2.5, 0.4, -0.2],
        }
    ).to_csv(live, index=False)
    report = tmp_path / "ladder.json"
    report.write_text(
        json.dumps(
            {
                "lifecycles": [
                    # Already in the table: skipped.
                    {
                        "symbol": "SOL",
                        "entry_oid": 1,
                        "status": "closed",
                        "strategy_id": "hourly_donchian_20_10_atr20_strong_short_v1",
                        "r_multiple": -1.0,
                    },
                    {
                        "symbol": "xyz:BRENTOIL",
                        "entry_oid": 9,
                        "status": "closed",
                        "strategy_id": "hourly_donchian_20_10_atr20_strong_short_v1",
                        "r_multiple": 0.5,
                    },
                    {
                        "symbol": "xyz:TSLA",
                        "entry_oid": 10,
                        "status": "open",
                        "strategy_id": "hourly_donchian_20_10_atr20_strong_short_v1",
                    },
                ]
            }
        )
    )
    research = tmp_path / "pool.csv"
    pd.DataFrame(
        {
            "screen": ["recent", "recent", "recent", "year", "recent"],
            "variant": ["plain"] * 5,
            "cost": ["measured", "measured", "adverse", "measured", "measured"],
            "symbol": ["SOL", "xyz:SNDK", "SOL", "SOL", "xyz:TSLA"],
            "side": ["short", "short", "long", "long", "long"],
            "ext_atr": [0.4, 1.3, None, None, None],
            "R": [-1.0, 3.0, 9.0, 9.0, 0.5],
        }
    ).to_csv(research, index=False)
    return live, report, research


def test_loaders_select_donchian_20_10_and_the_strong_short_research_pool(
    tmp_path: Path,
) -> None:
    live, report, research = _write_inputs(tmp_path)
    table = power.load_live_trades(live)
    assert [(trade.symbol, trade.r) for trade in table] == [
        ("SOL", -1.0),
        ("xyz:SNDK", 2.5),
    ]
    merged = power.merge_live(table, power.load_ladder_reports([report]))
    assert [trade.symbol for trade in merged] == ["SOL", "xyz:SNDK", "xyz:BRENTOIL"]
    # The same report twice (or overlapping reports) adds each lifecycle once.
    twice = power.merge_live(table, power.load_ladder_reports([report, report]))
    assert [trade.symbol for trade in twice] == ["SOL", "xyz:SNDK", "xyz:BRENTOIL"]
    pool = power.load_research_pool(research)
    # The weak short, the adverse-cost row and the year screen are excluded.
    assert sorted(trade.r for trade in pool) == [0.5, 3.0]
    kept = power.load_research_pool(research, drop_weak_shorts=False)
    assert sorted(trade.r for trade in kept) == [-1.0, 0.5, 3.0]


def test_a_close_without_an_entry_oid_is_never_merged_away() -> None:
    keyless = [power.Trade("SOL", -1.0, ""), power.Trade("SOL", 0.5, "")]
    assert power.merge_live(keyless[:1], keyless[1:]) == keyless
    assert power.merge_live([], keyless) == keyless


def test_main_writes_json_and_prints_the_markdown_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    live, report, research = _write_inputs(tmp_path)
    out = tmp_path / "out" / "power.json"
    code = power.main(
        [
            "--live-trades",
            str(live),
            "--ladder-report",
            str(report),
            "--research-pool",
            str(research),
            "--edges",
            "0,0.2",
            "--simulations",
            "500",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    table = json.loads(out.read_text())
    assert table["execution_authority"] == "none"
    assert set(table["pools"]) == {"live", "research", "combined"}
    assert table["pools"]["combined"]["stats"]["n"] == 5
    text = capsys.readouterr().out
    assert "| +0.20R |" in text
    assert "**Pool `combined`**" in text


def test_main_requires_some_closes(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        power.main(["--simulations", "10"])


def test_the_tool_imports_nothing_from_the_project() -> None:
    source = Path(power.__file__).read_text()
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert "hypervector" not in modules
    assert modules <= {
        "__future__",
        "argparse",
        "collections",
        "dataclasses",
        "datetime",
        "json",
        "math",
        "numpy",
        "pandas",
        "pathlib",
        "sys",
        "zlib",
    }
