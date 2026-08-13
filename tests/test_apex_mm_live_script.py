"""CLI-boundary tests for the Apex MM live process."""

from __future__ import annotations

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import signal
import sys
from types import ModuleType

import pytest

from hypervector.live.apex_mm_live_config import ApexMMLiveConfigError
from hypervector.live.apex_mm_live_config import load_apex_mm_live_config
from hypervector.runtime_lock import apex_mm_live_runtime_lock

SCRIPT = Path(__file__).parents[1] / "scripts" / "apex_regime_mm_live.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("apex_regime_mm_live", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_script_defaults_are_disarmed() -> None:
    """Invoking the script alone cannot satisfy either live-risk gate."""
    args = _load_module().build_parser().parse_args([])

    assert args.config == Path("configs/apex_regime_mm_canary.toml")
    assert args.enabled is False
    assert args.i_accept_live_risk is False


def test_live_script_refuses_before_authenticated_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing flags fail before any authenticated SDK construction."""
    module = _load_module()
    constructed = False

    def forbidden_factory(_config: object) -> None:
        nonlocal constructed
        constructed = True

    monkeypatch.setattr(module, "create_armed_apex_mm_adapter", forbidden_factory)
    monkeypatch.setattr(
        module,
        "credential_presence_from_env",
        lambda: type(
            "Presence", (), {"wallet_configured": True, "signing_key_configured": True}
        )(),
    )

    with pytest.raises(ApexMMLiveConfigError, match="--enabled"):
        module.run_live(module.build_parser().parse_args([]))

    assert constructed is False


def test_live_process_lock_precedes_authenticated_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A second process fails before constructing venue write authority."""
    module = _load_module()
    args = module.build_parser().parse_args(
        ["--enabled", "--i-accept-live-risk", "--max-polls", "1"]
    )
    config = load_apex_mm_live_config(
        args.config,
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        config,
        backend_ledger=tmp_path / "live/apex_regime_mm/decisions.jsonl",
        stop_file=tmp_path / "live/apex_regime_mm/STOP",
    )
    constructed = False

    def forbidden_factory(_config: object) -> object:
        nonlocal constructed
        constructed = True
        return object()

    monkeypatch.setattr(module, "create_armed_apex_mm_adapter", forbidden_factory)
    monkeypatch.setattr(module, "load_apex_mm_live_config", lambda *_a, **_kw: config)
    monkeypatch.setattr(
        module,
        "credential_presence_from_env",
        lambda: type(
            "Presence", (), {"wallet_configured": True, "signing_key_configured": True}
        )(),
    )

    with apex_mm_live_runtime_lock(config.backend_ledger):
        with pytest.raises(RuntimeError, match="Apex MM live backend already running"):
            module.run_live(args)

    assert constructed is False


def test_live_main_reports_refusal_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Operator configuration errors remain concise and actionable."""
    module = _load_module()
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])

    result = module.main()

    captured = capsys.readouterr()
    assert result == 2
    assert "live start requires --enabled" in captured.err
    assert "Traceback" not in captured.err


def test_live_main_converts_completed_poll_count_to_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bounded successful run must return a process success status."""
    module = _load_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--enabled", "--i-accept-live-risk", "--max-polls", "1"],
    )
    monkeypatch.setattr(module, "run_live", lambda _args: 1)

    assert module.main() == 0


def test_live_main_installs_and_restores_sigterm_cleanup_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIGTERM must become a cleanup-triggering interrupt, then be restored."""
    module = _load_module()
    calls: list[tuple[signal.Signals, object]] = []
    previous = object()

    def record_handler(signum: signal.Signals, handler: object) -> object:
        calls.append((signum, handler))
        return previous

    monkeypatch.setattr(signal, "signal", record_handler)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--enabled", "--i-accept-live-risk", "--max-polls", "1"],
    )
    monkeypatch.setattr(module, "run_live", lambda _args: 1)

    assert module.main() == 0
    assert calls[0][0] is signal.SIGTERM
    with pytest.raises(KeyboardInterrupt):
        calls[0][1](signal.SIGTERM, None)  # type: ignore[operator]
    assert calls[-1] == (signal.SIGTERM, previous)
