"""CLI acceptance for the v51 SOL route-native evidence monitor."""

from __future__ import annotations

from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v51_sol_route_native_one_blocker_shadow.py")
_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)


def test_parser_defaults_to_exact_v51_report_only_inputs() -> None:
    """The CLI exposes observation controls but no live-risk authority flags."""
    module = _module()
    args = module.build_parser().parse_args(
        ["--run-id", "run-v51", "--capture-start-ms", "123", "--once"]
    )

    assert args.config == _CONFIG
    assert args.cohort_ledger == Path("data/live/bidirectional_cohort/decisions.jsonl")
    assert args.asset_ledger == Path("data/live/bidirectional_cohort/sol.jsonl")
    assert args.data_root == Path("data")
    assert args.interval_seconds == 120.0
    assert args.archive_lag_seconds == 60.0
    assert not hasattr(args, "enabled")
    assert not hasattr(args, "i_accept_live_risk")


def test_main_passes_frozen_identity_to_zero_authority_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The script delegates one bounded poll without creating an order client."""
    module = _module()
    calls: list[dict[str, object]] = []
    locks: list[Path] = []

    @contextmanager
    def lock(path: Path) -> object:
        locks.append(path)
        yield path

    def run(**kwargs: object) -> int:
        assert locks
        calls.append(dict(kwargs))
        return 0

    monkeypatch.setattr(module, "cohort_checkpoint_runtime_lock", lock)
    monkeypatch.setattr(module, "run_sol_route_native_monitor", run)
    result = module.main(["--run-id", "run-v51", "--capture-start-ms", "123", "--once"])

    assert result == 0
    spec = calls[0]["spec"]
    assert spec.source_run_id == "run-v51"
    assert spec.capture_start_ms == 123
    assert calls[0]["once"] is True
    assert locks == [spec.output]


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v51 SOL route-native shadow script is missing")
    spec = spec_from_file_location("v51_sol_route_native_shadow_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v51 SOL route-native shadow script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
