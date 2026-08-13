"""CLI-boundary tests for the SOL live-only process."""

from __future__ import annotations

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live.hyperliquid_sol_factory import SolSdkFactoryError
from hypervector.live.sol_range_onset_config import (
    SolCanaryConfigError,
    load_sol_range_onset_config,
)
from hypervector.runtime_lock import sol_live_runtime_lock

SCRIPT = Path(__file__).parents[1] / "scripts" / "sol_range_onset_live.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_live", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_script_defaults_are_disarmed() -> None:
    """Merely invoking the script cannot satisfy either explicit risk gate."""
    args = _load_module().build_parser().parse_args([])

    assert args.config == Path("configs/sol_range_onset_canary.toml")
    assert args.enabled is False
    assert args.i_accept_live_risk is False


def test_live_script_refuses_before_constructing_sdk_without_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing flags fail before authenticated client construction."""
    module = _load_module()
    args = module.build_parser().parse_args([])
    constructed = False

    def forbidden_factory(_config: object) -> None:
        nonlocal constructed
        constructed = True

    monkeypatch.setattr(module, "create_armed_sol_adapter", forbidden_factory)
    monkeypatch.setattr(
        module,
        "credential_presence_from_env",
        lambda: type(
            "Presence", (), {"wallet_configured": True, "signing_key_configured": True}
        )(),
    )

    with pytest.raises(SolCanaryConfigError, match="--enabled"):
        module.run_live(args)

    assert constructed is False


def test_live_main_reports_refusal_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Operator configuration errors are concise while retaining failure status."""
    module = _load_module()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    result = module.main()

    captured = capsys.readouterr()
    assert result == 2
    assert "live start requires --enabled" in captured.err
    assert "Traceback" not in captured.err


def test_live_main_reports_agent_identity_refusal_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A mismatched or overprivileged signer fails with an operator-safe error."""
    module = _load_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--enabled", "--i-accept-live-risk"],
    )
    monkeypatch.setattr(
        module,
        "run_live",
        lambda args: (_ for _ in ()).throw(
            SolSdkFactoryError("signing key must belong to an authorized API agent")
        ),
    )

    result = module.main()

    captured = capsys.readouterr()
    assert result == 2
    assert "authorized API agent" in captured.err
    assert "Traceback" not in captured.err


def test_live_process_lock_precedes_authenticated_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A second process must fail before it can construct venue write authority."""
    module = _load_module()
    args = module.build_parser().parse_args(
        ["--enabled", "--i-accept-live-risk", "--max-polls", "1"]
    )
    config = load_sol_range_onset_config(
        args.config,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        config,
        live_ledger=tmp_path / "live/sol_range_onset_canary/decisions.jsonl",
        live_stop_file=tmp_path / "live/sol_range_onset_canary/STOP",
    )
    constructed = False

    def forbidden_factory(_config: object) -> object:
        nonlocal constructed
        constructed = True
        return object()

    monkeypatch.setattr(module, "create_armed_sol_adapter", forbidden_factory)
    monkeypatch.setattr(
        module,
        "load_sol_range_onset_config",
        lambda *_a, **_kw: config,
    )
    monkeypatch.setattr(
        module,
        "credential_presence_from_env",
        lambda: type(
            "Presence",
            (),
            {"wallet_configured": True, "signing_key_configured": True},
        )(),
    )

    with sol_live_runtime_lock(config.live_ledger):
        with pytest.raises(RuntimeError, match="SOL live backend already running"):
            module.run_live(args)

    assert constructed is False
