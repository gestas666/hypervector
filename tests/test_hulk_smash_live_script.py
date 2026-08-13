from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import signal
import sys
from types import ModuleType

import pytest

from hypervector.live.hulk_smash_live_config import (
    HulkSmashLiveConfigError,
    load_hulk_smash_live_config,
)
from hypervector.runtime_lock import hulk_smash_live_runtime_lock

SCRIPT = Path(__file__).parents[1] / "scripts" / "hulk_smash_live.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("hulk_smash_live", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_hulk_live_script_defaults_are_disarmed() -> None:
    args = _load_module().parser().parse_args([])

    assert args.config == Path("configs/hulk_smash_short_robust_v3_canary.toml")
    assert args.enabled is False
    assert args.i_accept_live_risk is False


def test_hulk_live_refuses_before_authenticated_factory_without_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    constructed = False

    def forbidden_factory(_config: object) -> None:
        nonlocal constructed
        constructed = True

    monkeypatch.setattr(module, "create_armed_hulk_btc_adapter", forbidden_factory)
    monkeypatch.setattr(
        module,
        "credential_presence_from_env",
        lambda: type(
            "Presence",
            (),
            {"wallet_configured": True, "signing_key_configured": True},
        )(),
    )

    with pytest.raises(HulkSmashLiveConfigError, match="--enabled"):
        module.run(module.parser().parse_args([]))

    assert constructed is False


def test_hulk_live_lock_precedes_authenticated_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    args = module.parser().parse_args(
        ["--enabled", "--i-accept-live-risk", "--max-polls", "1"]
    )
    config = load_hulk_smash_live_config(
        args.config,
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    config = replace(
        config,
        backend_ledger=tmp_path / "live/hulk_smash/decisions.jsonl",
        stop_file=tmp_path / "live/hulk_smash/STOP",
    )
    constructed = False

    def forbidden_factory(_config: object) -> None:
        nonlocal constructed
        constructed = True

    monkeypatch.setattr(module, "create_armed_hulk_btc_adapter", forbidden_factory)
    monkeypatch.setattr(
        module,
        "load_hulk_smash_live_config",
        lambda *_a, **_kw: config,
    )
    monkeypatch.setattr(module, "validate_hulk_signal_source", lambda _config: None)
    monkeypatch.setattr(
        module,
        "credential_presence_from_env",
        lambda: type(
            "Presence",
            (),
            {"wallet_configured": True, "signing_key_configured": True},
        )(),
    )

    with hulk_smash_live_runtime_lock(config.backend_ledger):
        with pytest.raises(RuntimeError, match="Hulk Smash live backend"):
            module.run(args)

    assert constructed is False


def test_hulk_live_main_converts_completed_poll_count_to_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), "--enabled", "--i-accept-live-risk", "--max-polls", "1"],
    )
    monkeypatch.setattr(module, "run", lambda _args: 1)

    assert module.main() == 0


def test_hulk_live_main_installs_deferred_signal_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.setattr(module, "run", lambda _args: 1)

    assert module.main() == 0
    installed = dict(calls[:2])
    assert set(installed) == {signal.SIGINT, signal.SIGTERM}
    module._STOP_REQUESTED.clear()
    installed[signal.SIGTERM](signal.SIGTERM, None)  # type: ignore[operator]
    assert module._STOP_REQUESTED.is_set()
    assert calls[-2:] == [
        (signal.SIGINT, previous),
        (signal.SIGTERM, previous),
    ]
