"""The generic paper session identity keeps a stable, meaning-named shape."""

from __future__ import annotations

import ast
from pathlib import Path

from paper_fix_fixtures import write_strict_export
from synthetic_strategies import MANAGED_LONG

from hypervector.paper import session_identity
from hypervector.paper.session import PaperSession
from hypervector.paper.session_identity import session_identity_payload

SESSION_SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "hypervector" / "paper" / "session.py"
)

IDENTITY_KEYS = [
    "feed_ts", "run_id", "export_id", "strategy_name", "symbol", "timeframe",
    "data_root", "action", "execution_model", "conviction", "metalabel_mode",
    "metalabel_bundle_id", "strategy_params", "execution_profile", "portfolio_spec",
    "portfolio_fingerprint", "exits", "risk", "execution", "costs", "runtime",
    "bars_processed", "execution_mode", "submitted", "network", "position_qty",
    "position_avg_px", "realized_pnl", "unrealized_pnl", "equity", "init_cash",
    "no_submit",
]


def test_identity_key_order_is_the_same_for_every_declared_profile(
    tmp_path: Path,
) -> None:
    standard = PaperSession(
        export_dir=write_strict_export(tmp_path / "a"), data_root=tmp_path / "a" / "d"
    )
    declared = PaperSession(
        export_dir=write_strict_export(tmp_path / "b", strategy=MANAGED_LONG),
        data_root=tmp_path / "b" / "d",
        execution_mode="shadow",
    )
    assert list(session_identity_payload(standard)) == IDENTITY_KEYS
    assert list(session_identity_payload(declared)) == IDENTITY_KEYS


def test_identity_sections_are_named_by_meaning() -> None:
    names = {name for name in vars(session_identity) if name.startswith("_section_")}
    assert names == {
        "_section_identity",
        "_section_model",
        "_section_strategy_policy",
        "_section_risk_costs",
        "_section_runtime",
        "_section_portfolio_state",
    }


def test_session_module_has_no_bottom_reimports_or_dead_helpers() -> None:
    tree = ast.parse(SESSION_SOURCE.read_text(encoding="utf-8"))
    body = tree.body
    first_def = next(
        index
        for index, node in enumerate(body)
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    )
    late_imports = [
        node.lineno
        for node in body[first_def:]
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert late_imports == []
    assigned = {
        target.id
        for node in body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "_OHLCV_REQUIRED" not in assigned
    offline = next(
        node
        for node in body
        if isinstance(node, ast.FunctionDef) and node.name == "run_paper_session_offline"
    )
    assert "once per bar" not in (ast.get_docstring(offline) or "")
