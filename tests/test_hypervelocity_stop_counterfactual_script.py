from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _script() -> object:
    path = Path("scripts/hypervelocity_stop_counterfactual.py")
    spec = importlib.util.spec_from_file_location("stop_counterfactual_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load stop counterfactual script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lifecycle_rows_supports_legacy_event_replay() -> None:
    script = _script()
    payload = {"event_replay": {"lifecycles": [{"lifecycle_id": 1}]}}

    assert script._lifecycle_rows(payload, None) == [{"lifecycle_id": 1}]


def test_lifecycle_rows_selects_named_grid_candidate() -> None:
    script = _script()
    payload = {
        "comparison": {
            "candidates": {"hard": {"replay": {"lifecycles": [{"lifecycle_id": 2}]}}}
        }
    }

    assert script._lifecycle_rows(payload, "hard") == [{"lifecycle_id": 2}]


def test_lifecycle_rows_rejects_missing_candidate() -> None:
    script = _script()

    with pytest.raises(ValueError, match="candidate is missing"):
        script._lifecycle_rows({"comparison": {"candidates": {}}}, "hard")
