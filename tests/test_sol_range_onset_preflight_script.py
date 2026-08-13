"""CLI tests for the execution-incapable SOL mainnet preflight."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live.hyperliquid_sol_factory import SolSdkFactoryError

SCRIPT = Path(__file__).parents[1] / "scripts" / "sol_range_onset_preflight.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_preflight", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_preflight_command_has_no_live_authority_flags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command cannot accept arming flags and reports no execution client."""
    module = _load_module()
    args = module.build_parser().parse_args([])
    reader = object()
    monkeypatch.setattr(module, "create_read_only_sol_reader", lambda: reader)

    def collect(**kwargs: object) -> dict[str, object]:
        assert kwargs["reader"] is reader
        return {
            "authority": {"execution_client_constructed": False},
            "canary": {"technically_ready": True},
        }

    monkeypatch.setattr(module, "collect_sol_read_only_preflight", collect)

    result = module.run_preflight(args)

    assert result == 0
    assert "--enabled" not in module.build_parser().format_help()
    assert '"execution_client_constructed": false' in capsys.readouterr().out


def test_main_reports_missing_wallet_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing public identity is actionable and cannot fall through to SDK calls."""
    module = _load_module()
    monkeypatch.setattr(module, "load_wallet_env_if_present", lambda: ())
    monkeypatch.setattr(
        module,
        "create_read_only_sol_reader",
        lambda: (_ for _ in ()).throw(SolSdkFactoryError("wallet address missing")),
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    result = module.main()

    captured = capsys.readouterr()
    assert result == 2
    assert "wallet address missing" in captured.err
    assert "Traceback" not in captured.err
