"""Structured logging tests for the report-only live checkpoint sidecar."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = (
    Path(__file__).parents[1]
    / "src" / "hypervector" / "operations" / 'multi_asset_bidirectional_live_checkpoint.py'
)


_CHECKPOINT_CONFIG = ["--config", "configs/multi_asset_bidirectional_canary.toml"]


def _load_module() -> ModuleType:
    spec = spec_from_file_location("cohort_checkpoint_logging_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _CompletedSync:
    def pop_report(self) -> dict[str, object]:
        return {"imported_events": 3}

    def pop_error(self) -> None:
        return None


def test_background_sync_is_one_flushed_stderr_json_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Merged launchd streams must retain one parseable line per sync event."""
    module = _load_module()

    module._log_background_sync(_CompletedSync())

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "event": "cohort_research_sync",
        "execution_authority": "none",
        "result": {"imported_events": 3},
    }


def test_historical_refresh_is_a_structured_stderr_event(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full-history refresh cannot corrupt the adjacent sync event line."""
    module = _load_module()
    monkeypatch.setattr(
        module, "publish_rolling_checkpoint", lambda *args, **kwargs: True
    )
    args = module.build_parser().parse_args(_CHECKPOINT_CONFIG + [])

    module._publish_real_snapshot(args, lambda *args, **kwargs: {}, None, None, None)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "event": "cohort_historical_projection_refreshed",
        "execution_authority": "none",
        "source": "complete_ledgers",
    }
