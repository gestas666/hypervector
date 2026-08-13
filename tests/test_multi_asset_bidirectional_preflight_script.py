"""CLI tests for the execution-incapable multi-asset transition preflight."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live.hyperliquid_sol_factory import SolSdkFactoryError
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "multi_asset_bidirectional_preflight.py"
)
_V35 = Path("configs/multi_asset_bidirectional_all_live_canary_v35.toml")
_V37 = Path("configs/multi_asset_bidirectional_growth_5000_candidate_v37.toml")
_V51 = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)


def _load_module() -> ModuleType:
    spec = spec_from_file_location("multi_asset_bidirectional_preflight", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _checkpoint(path: Path) -> None:
    assets = {}
    symbols = (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:GOLD",
        "xyz:BRENTOIL",
    )
    for symbol in symbols:
        assets[symbol] = {
            "position_size_signed": 0.0171 if symbol == "xyz:GOLD" else 0.0,
            "open_order_ids": [91] if symbol == "xyz:GOLD" else [],
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
                        "profile_id": "multi_asset_bidirectional_all_live_canary_v35",
                        "profile_fingerprint": load_multi_asset_live_config(
                            _V35,
                            mode="observe",
                        ).profile_fingerprint,
                        "symbols": list(symbols),
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
    _checkpoint(checkpoint)
    readers = {
        symbol: object()
        for symbol in load_multi_asset_live_config(_V35, mode="observe").symbols
    }
    monkeypatch.setattr(module, "_readers", lambda config: readers)

    def collect(**kwargs: object) -> dict[str, object]:
        assert set(kwargs["readers"]) == set(readers)
        assert kwargs["sizing_reference_equity_usd"] == pytest.approx(5_000.0)
        expectations = kwargs["ledger_expectations"]
        assert expectations["xyz:GOLD"].owned_order_ids == frozenset({91})
        return {
            "authority": {"execution_authority": "none"},
            "portfolio": {"technically_ready_for_profile_transition": True},
        }

    monkeypatch.setattr(module, "collect_multi_asset_read_only_preflight", collect)
    args = module.build_parser().parse_args(
        [
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
    _checkpoint(checkpoint)
    monkeypatch.setattr(
        module,
        "_readers",
        lambda config: {
            symbol: object()
            for symbol in load_multi_asset_live_config(_V35, mode="observe").symbols
        },
    )
    monkeypatch.setattr(
        module,
        "collect_multi_asset_read_only_preflight",
        lambda **kwargs: {
            "portfolio": {"technically_ready_for_profile_transition": False}
        },
    )

    result = module.run_preflight(
        module.build_parser().parse_args(["--checkpoint", str(checkpoint)])
    )

    assert result == 3


def test_v51_stale_index_observer_aborts_before_venue_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final launch preflight must enforce its observer dependency."""
    module = _load_module()
    checkpoint = tmp_path / "checkpoint.json"
    _checkpoint(checkpoint)
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
            str(_V51),
            "--active-config",
            str(_V35),
            "--checkpoint",
            str(checkpoint),
        ]
    )

    with pytest.raises(ValueError, match="observer status is stale"):
        module.run_preflight(args)
    assert venue_read is False


def test_removed_gold_remains_a_transition_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A candidate cannot hide active GOLD exposure by removing its route."""
    module = _load_module()
    checkpoint = tmp_path / "checkpoint.json"
    _checkpoint(checkpoint)
    readers = {
        symbol: object()
        for symbol in module.load_multi_asset_live_config(_V35, mode="observe").symbols
    }
    monkeypatch.setattr(module, "_readers", lambda _config: readers)
    monkeypatch.setattr(
        module,
        "collect_multi_asset_read_only_preflight",
        lambda **_kwargs: {
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
        },
    )
    monkeypatch.setattr(
        module,
        "collect_retired_asset_report",
        lambda asset, reader, ledger: {
            "symbol": asset.symbol,
            "position_size_signed": ledger.position_size_signed,
            "open_order_ids": tuple(ledger.owned_order_ids),
            "ledger_reconciled": True,
            "flat_no_orders": False,
        },
    )
    args = module.build_parser().parse_args(
        [
            "--config",
            str(_V37),
            "--active-config",
            str(_V35),
            "--checkpoint",
            str(checkpoint),
        ]
    )

    result = module.run_preflight(args)

    assert result == 3


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
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT)])

    result = module.main()

    captured = capsys.readouterr()
    assert result == 2
    assert "wallet missing" in captured.err
    assert "Traceback" not in captured.err
