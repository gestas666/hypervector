"""Regression coverage for initial checkpoint research synchronization."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "multi_asset_bidirectional_live_checkpoint.py"
)


def _load_module() -> ModuleType:
    spec = spec_from_file_location("checkpoint_initial_sync_order", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_initial_sync_publishes_bounded_current_run_without_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep live telemetry fresh without building all-time history in-process."""
    module = _load_module()
    published: list[dict[str, object]] = []

    class PendingSync:
        portfolio_archive = None

        def poll(self, *, now: float) -> None:
            del now

        def pop_report(self) -> None:
            return None

        def pop_error(self) -> None:
            return None

        def close(self) -> None:
            return None

    def stop_after_wait(_seconds: float) -> None:
        raise RuntimeError("bounded test stop")

    monkeypatch.setattr(module, "_background_sync", lambda *_args: PendingSync())
    monkeypatch.setattr(
        module,
        "_publish_once",
        lambda *_args, **kwargs: published.append(kwargs),
    )
    args = module.build_parser().parse_args(
        ["--research-database", str(tmp_path / "market.duckdb")]
    )

    with pytest.raises(RuntimeError, match="bounded test stop"):
        module._run_owned_checkpoint_loop(
            args,
            publish_fn=lambda *_args, **_kwargs: {},
            sync_fn=lambda *_args: {},
            portfolio_fn=None,
            funding_fn=None,
            sleep_fn=stop_after_wait,
        )

    assert published[0]["current_run_only"] is True
