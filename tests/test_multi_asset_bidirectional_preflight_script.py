"""CLI tests for the execution-incapable multi-asset transition preflight."""

from __future__ import annotations

import ast
from importlib import import_module
import json
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.live.hyperliquid_sol_factory import SolSdkFactoryError
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_read_only_preflight import AssetLedgerExpectation

_MODULE = "hypervector.operations.multi_asset_bidirectional_preflight"
_SCRIPT = (
    Path(__file__).parents[1]
    / "src/hypervector/operations/multi_asset_bidirectional_preflight.py"
)
_CHAIN = Path("tests/fixtures/cohort_chain")
_PROFILE_A = _CHAIN / "profile_a.toml"
_PROFILE_B = _CHAIN / "profile_b.toml"
_ROLLBACK_B_TO_A = _CHAIN / "rollback_b_to_a.toml"
# Routes the HIP-3 fresh15 v3 provider whose observer dependency the preflight
# must enforce.
_OBSERVER_PROFILE = Path("tests/fixtures/profiles/six_asset_profit_lock.toml")


def _load_module() -> ModuleType:
    return import_module(_MODULE)


@pytest.mark.parametrize("path", (_SCRIPT, Path(__file__)))
def test_preflight_functions_respect_project_size_limit(path: Path) -> None:
    """Keep the report-only orchestration within the project function limit."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    oversized = {
        node.name: node.end_lineno - node.lineno + 1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno is not None
        and node.end_lineno - node.lineno + 1 > 50
    }

    assert oversized == {}


def _checkpoint(
    path: Path,
    config_path: Path,
    *,
    open_symbol: str | None = None,
) -> None:
    """Write a report-only active checkpoint, optionally with one open asset."""
    config = load_multi_asset_live_config(config_path, mode="observe")
    assets = {
        symbol: {
            "position_size_signed": 0.0171 if symbol == open_symbol else 0.0,
            "open_order_ids": [91] if symbol == open_symbol else [],
        }
        for symbol in config.symbols
    }
    path.write_text(
        json.dumps(
            {
                "checkpoint_contract": {
                    "report_only": True,
                    "execution_authority": "none",
                },
                "audit": {
                    "run": {
                        "run_id": "active-run",
                        "profile_id": config.profile_id,
                        "profile_fingerprint": config.profile_fingerprint,
                        "symbols": list(config.symbols),
                    },
                    "health": {"assets": assets},
                },
            }
        ),
        encoding="utf-8",
    )


def test_command_has_no_live_flags_and_writes_atomic_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command cannot arm execution and returns transition readiness."""
    module = _load_module()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "preflight.json"
    _checkpoint(checkpoint, _PROFILE_B, open_symbol="xyz:CCC")
    readers = {
        symbol: object()
        for symbol in load_multi_asset_live_config(_PROFILE_B, mode="observe").symbols
    }
    monkeypatch.setattr(module, "_readers", lambda config: readers)

    def collect(**kwargs: object) -> dict[str, object]:
        assert set(kwargs["readers"]) == set(readers)
        assert kwargs["sizing_reference_equity_usd"] == pytest.approx(5_000.0)
        expectations = kwargs["ledger_expectations"]
        assert expectations["xyz:CCC"].owned_order_ids == frozenset({91})
        return {
            "authority": {"execution_authority": "none"},
            "portfolio": {"technically_ready_for_profile_transition": True},
        }

    monkeypatch.setattr(module, "collect_multi_asset_read_only_preflight", collect)
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_PROFILE_B),
            "--active-config",
            str(_PROFILE_B),
            "--checkpoint",
            str(checkpoint),
            "--output",
            str(output),
            "--sizing-equity-usd",
            "5000",
        ]
    )

    result = module.run_preflight(args)

    assert result == 0
    assert json.loads(output.read_text()) == json.loads(capsys.readouterr().out)
    help_text = module.build_parser().format_help()
    assert "--enabled" not in help_text
    assert "--i-accept-live-risk" not in help_text


def test_nonflat_preflight_returns_distinct_not_ready_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid but non-flat report is not confused with a technical crash."""
    module = _load_module()
    checkpoint = tmp_path / "checkpoint.json"
    _checkpoint(checkpoint, _PROFILE_B, open_symbol="BTC")
    monkeypatch.setattr(
        module,
        "_readers",
        lambda config: {symbol: object() for symbol in config.symbols},
    )
    monkeypatch.setattr(
        module,
        "collect_multi_asset_read_only_preflight",
        lambda **kwargs: {
            "portfolio": {"technically_ready_for_profile_transition": False}
        },
    )
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_PROFILE_B),
            "--active-config",
            str(_PROFILE_B),
            "--checkpoint",
            str(checkpoint),
        ]
    )

    assert module.run_preflight(args) == 3


def test_changed_profile_without_approval_is_visible_but_has_no_authority(
    tmp_path: Path,
) -> None:
    """Public preflight distinguishes technical checks from live approval."""
    module = _load_module()
    active = load_multi_asset_live_config(_PROFILE_A, mode="observe")
    raw = _PROFILE_B.read_text(encoding="utf-8")
    approval_line = next(
        line
        for line in raw.splitlines(keepends=True)
        if line.startswith("transition_approval =")
    )
    unapproved = tmp_path / "profile_b_without_approval.toml"
    unapproved.write_text(raw.replace(approval_line, "", 1), encoding="utf-8")
    candidate = load_multi_asset_live_config(unapproved, mode="observe")
    assert candidate.transition_approval is None

    evidence = module._profile_change_approval_evidence(candidate, active)

    assert evidence["state"] == "blocked_profile_change"
    assert evidence["approval_required"] is True
    assert evidence["execution_authority"] == "none"
    assert "exact approval document" in evidence["reason"]


@pytest.mark.parametrize(
    ("active_path", "candidate_path"),
    [(_PROFILE_A, _PROFILE_B), (_PROFILE_B, _ROLLBACK_B_TO_A)],
    ids=["a-to-b", "b-to-a-rollback"],
)
def test_chain_approvals_are_projected_without_authority(
    active_path: Path,
    candidate_path: Path,
) -> None:
    """The forward and rollback chain approvals pass yet grant no authority."""
    module = _load_module()
    active = load_multi_asset_live_config(active_path, mode="observe")
    candidate = load_multi_asset_live_config(candidate_path, mode="observe")

    evidence = module._profile_change_approval_evidence(candidate, active)

    assert evidence["state"] == "approved_profile_change"
    assert evidence["approval_document"] == str(candidate.transition_approval)
    assert evidence["execution_authority"] == "none"
    assert module._profile_change_blockers(evidence, {"state": "ok"}) == ()


def test_checkpoint_null_reconciliation_fields_use_explicit_state_evidence() -> None:
    """Current checkpoints can derive flat/open expectations without guessing."""
    module = _load_module()
    flat = {
        "final_state": "FLAT",
        "position_size_signed": None,
        "open_order_ids": None,
        "stop_oid": None,
    }
    opened = {
        "final_state": "OPEN",
        "position_size_signed": None,
        "open_order_ids": None,
        "stop_oid": 91,
    }
    venue_positions = {"ETH": {"symbol": "ETH", "size_signed": -0.5}}

    assert module._asset_expectation("BTC", flat, venue_positions) == (
        module.AssetLedgerExpectation(0.0, frozenset())
    )
    assert module._asset_expectation("ETH", opened, venue_positions) == (
        module.AssetLedgerExpectation(-0.5, frozenset({91}))
    )


def test_open_checkpoint_without_position_evidence_fails_closed() -> None:
    """An OPEN state cannot be converted into a success-shaped flat expectation."""
    module = _load_module()
    opened = {
        "final_state": "OPEN",
        "position_size_signed": None,
        "open_order_ids": None,
        "stop_oid": 91,
    }

    with pytest.raises(ValueError, match="OPEN but has no execution position"):
        module._asset_expectation("ETH", opened, {})


def test_stale_index_observer_aborts_before_venue_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final launch preflight must enforce its observer dependency."""
    module = _load_module()
    checkpoint = tmp_path / "checkpoint.json"
    _checkpoint(checkpoint, _PROFILE_B)
    venue_read = False

    def reject_observer(_observed_at: object) -> None:
        raise ValueError("HIP-3 v3 observer status is stale")

    def readers(_config: object) -> dict[str, object]:
        nonlocal venue_read
        venue_read = True
        return {}

    monkeypatch.setattr(module, "require_fresh_index_observers", reject_observer)
    monkeypatch.setattr(module, "_readers", readers)
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_OBSERVER_PROFILE),
            "--active-config",
            str(_PROFILE_B),
            "--checkpoint",
            str(checkpoint),
        ]
    )

    with pytest.raises(ValueError, match="observer status is stale"):
        module.run_preflight(args)
    assert venue_read is False


def test_additive_candidate_reconciles_new_asset_outside_active_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new flat asset must use its ledger plus venue instead of being impossible."""
    module = _load_module()
    checkpoint = tmp_path / "checkpoint.json"
    _checkpoint(checkpoint, _PROFILE_B)
    candidate = load_multi_asset_live_config(_ROLLBACK_B_TO_A, mode="observe")
    readers = {symbol: object() for symbol in candidate.symbols}
    monkeypatch.setattr(module, "_readers", lambda config: readers)
    monkeypatch.setattr(
        module,
        "_addition_expectation",
        lambda asset: module.AssetLedgerExpectation(0.0, frozenset()),
    )

    def collect(**kwargs: object) -> dict[str, object]:
        assert set(kwargs["readers"]) == set(candidate.symbols)
        expectations = kwargs["ledger_expectations"]
        for added in ("HYPE", "xyz:BBB"):
            assert expectations[added] == module.AssetLedgerExpectation(
                0.0, frozenset()
            )
        return {"portfolio": {"technically_ready_for_profile_transition": True}}

    monkeypatch.setattr(module, "collect_multi_asset_read_only_preflight", collect)
    monkeypatch.setattr(
        module,
        "_attach_profile_change_evidence",
        lambda report, *_args: report,
    )
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_ROLLBACK_B_TO_A),
            "--active-config",
            str(_PROFILE_B),
            "--checkpoint",
            str(checkpoint),
        ]
    )

    assert module.run_preflight(args) == 0


def test_removed_asset_remains_a_transition_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Profile B cannot hide active profile A BBB exposure by removing the asset."""
    module = _load_module()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "preflight.json"
    _checkpoint(checkpoint, _PROFILE_A, open_symbol="xyz:BBB")
    readers = {
        symbol: object()
        for symbol in load_multi_asset_live_config(_PROFILE_A, mode="observe").symbols
    }
    retired: list[str] = []
    monkeypatch.setattr(module, "_readers", lambda _config: readers)
    monkeypatch.setattr(
        module,
        "collect_multi_asset_read_only_preflight",
        lambda **_kwargs: _ready_transition_report(),
    )
    monkeypatch.setattr(
        module,
        "collect_retired_asset_report",
        lambda asset, reader, ledger: _retired_report(retired, asset, ledger),
    )
    monkeypatch.setattr(
        module, "_attach_profile_change_evidence", lambda report, *_args: report
    )
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_PROFILE_B),
            "--active-config",
            str(_PROFILE_A),
            "--checkpoint",
            str(checkpoint),
            "--output",
            str(output),
        ]
    )

    result = module.run_preflight(args)

    assert result == 3
    assert sorted(retired) == ["HYPE", "xyz:BBB"]
    portfolio = json.loads(output.read_text(encoding="utf-8"))["portfolio"]
    assert portfolio["transition_blocking_assets"] == ["xyz:BBB"]
    assert portfolio["technically_ready_for_profile_transition"] is False


def _retired_report(
    seen: list[str],
    asset: AssetLiveConfig,
    ledger: AssetLedgerExpectation,
) -> dict[str, object]:
    """Report a removed asset from its active ledger expectation only."""
    seen.append(asset.symbol)
    size = ledger.position_size_signed
    owned = tuple(ledger.owned_order_ids)
    return {
        "symbol": asset.symbol,
        "position_size_signed": size,
        "open_order_ids": owned,
        "ledger_reconciled": True,
        "flat_no_orders": size == 0.0 and not owned,
    }


def _ready_transition_report() -> dict[str, object]:
    return {
        "portfolio": {
            "open_positions": 0,
            "open_orders": 0,
            "transition_blocking_assets": (),
            "ledger_reconciled": True,
            "sizing_technically_ready": True,
            "technically_ready_for_profile_transition": True,
            "readiness_reasons": (),
        },
        "assets": (),
    }


def test_main_reports_missing_public_wallet_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing public identity cannot fall through to an SDK construction trace."""
    module = _load_module()
    monkeypatch.setattr(module, "load_wallet_env_if_present", lambda: ())
    monkeypatch.setattr(
        module,
        "run_preflight",
        lambda args: (_ for _ in ()).throw(SolSdkFactoryError("wallet missing")),
    )
    result = module.main(
        ["--config", str(_PROFILE_B), "--active-config", str(_PROFILE_A)]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "wallet missing" in captured.err
    assert "Traceback" not in captured.err
