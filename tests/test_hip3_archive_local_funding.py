"""Network-free official funding input for HIP-3 archive qualification."""

from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import sys

import pandas as pd

from hypervector.data.hl_funding_archive import HlFundingRequest, store_hl_funding

_SCRIPT = Path("scripts/mu_hip3_archive_research.py")
_SPEC = importlib.util.spec_from_file_location("hip3_archive_funding_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_explicit_local_funding_path_bypasses_network(tmp_path: Path) -> None:
    """Exact CL qualification consumes its immutable local funding bundle."""
    start = datetime(2026, 7, 25, 12, tzinfo=UTC)
    end = datetime(2026, 7, 25, 14, tzinfo=UTC)
    request = HlFundingRequest("xyz:CL", start, end)
    start_ms = int(pd.Timestamp(start).timestamp() * 1_000)
    stored = store_hl_funding(
        tmp_path,
        request,
        (
            (
                _row(start_ms, "0.00001"),
                _row(start_ms + 3_600_000, "-0.00002"),
            ),
        ),
    )
    args = _MODULE.build_parser().parse_args(["--funding", str(stored.funding_path)])

    def forbidden_fetch(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise AssertionError("network funding fetch must not run")

    frame, evidence = _MODULE._load_funding_input(
        args,
        "xyz:CL",
        pd.Timestamp(start),
        pd.Timestamp(end),
        forbidden_fetch,
    )

    assert len(frame) == 2
    assert frame["timestamp"].tolist() == list(pd.date_range(start, end, freq="h")[:-1])
    assert evidence["mode"] == "immutable_local_bundle"
    assert evidence["sha256"]
    assert evidence["manifest_sha256"]


def _row(timestamp_ms: int, rate: str) -> dict[str, object]:
    return {
        "coin": "xyz:CL",
        "fundingRate": rate,
        "premium": "0.0",
        "time": timestamp_ms + 30,
    }
