"""Command-surface tests for immutable regime component attribution."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.regime_component_attribution import AttributionSegment

_SCRIPT = Path("scripts/regime_component_attribution.py")
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


def _module() -> ModuleType:
    spec = spec_from_file_location("regime_component_attribution_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load attribution script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _paths(tmp_path: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for symbol in _SYMBOLS:
        path = tmp_path / f"{symbol}.parquet"
        path.touch()
        paths[symbol] = path
    return paths


def _segments() -> tuple[AttributionSegment, ...]:
    return (
        AttributionSegment(
            "development",
            pd.Timestamp("2025-07-28T00:00:00Z"),
            pd.Timestamp("2026-01-28T00:00:00Z"),
        ),
        AttributionSegment(
            "validation",
            pd.Timestamp("2026-01-28T00:00:00Z"),
            pd.Timestamp("2026-05-28T00:00:00Z"),
        ),
        AttributionSegment(
            "pseudo_holdout",
            pd.Timestamp("2026-05-28T00:00:00Z"),
            pd.Timestamp("2026-07-28T00:00:00Z"),
        ),
    )


def _asset_report(
    symbol: str,
    segments: tuple[AttributionSegment, ...],
    horizons: tuple[int, ...],
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "segments": {
            segment.name: {
                "horizons": {
                    str(horizon): {
                        "observations": {
                            "total": 1,
                            "usable": 1,
                            "gap_decision": 0,
                            "gap_label_path": 0,
                            "right_censored": 0,
                        }
                    }
                    for horizon in horizons
                }
            }
            for segment in segments
        },
        "evidence_disposition": "STOP",
    }


def test_parse_bars_requires_exact_unique_four_asset_set(tmp_path: Path) -> None:
    module = _module()
    paths = _paths(tmp_path)
    values = [f"{symbol}={path}" for symbol, path in paths.items()]

    assert module.parse_bar_mappings(values) == paths
    with pytest.raises(ValueError, match="duplicate"):
        module.parse_bar_mappings(values + [values[0]])
    with pytest.raises(ValueError, match="exactly BTC, ETH, SOL, HYPE"):
        module.parse_bar_mappings(values[:-1])


def test_chronological_boundaries_must_be_utc_and_ordered() -> None:
    module = _module()

    valid = module.build_segments(
        "2025-07-28T00:00:00Z",
        "2026-01-28T00:00:00Z",
        "2026-05-28T00:00:00Z",
        "2026-07-28T00:00:00Z",
    )
    assert [segment.name for segment in valid] == [
        "development",
        "validation",
        "pseudo_holdout",
    ]

    with pytest.raises(ValueError, match="UTC"):
        module.build_segments(
            "2025-07-28T00:00:00-04:00",
            "2026-01-28T00:00:00Z",
            "2026-05-28T00:00:00Z",
            "2026-07-28T00:00:00Z",
        )
    with pytest.raises(ValueError, match="strictly ordered"):
        module.build_segments(
            "2025-07-28T00:00:00Z",
            "2026-05-28T00:00:00Z",
            "2026-01-28T00:00:00Z",
            "2026-07-28T00:00:00Z",
        )


def test_load_bars_rejects_missing_file_or_unsupported_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    with pytest.raises(FileNotFoundError, match="bar evidence is missing"):
        module.load_bars(tmp_path / "missing.parquet")
    path = tmp_path / "bars.parquet"
    path.touch()
    frame = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01T00:00:00Z")],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
            "source": ["binance"],
        }
    )
    monkeypatch.setattr(module.pd, "read_parquet", lambda _: frame)

    with pytest.raises(ValueError, match="unsupported attribution provenance"):
        module.load_bars(path)


def test_report_retains_all_assets_and_weak_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    paths = _paths(tmp_path)
    frame = pd.DataFrame({"source": ["hl"]})
    monkeypatch.setattr(module, "load_bars", lambda _: frame)
    monkeypatch.setattr(
        module,
        "build_component_attribution",
        lambda bars,
        symbol,
        segments,
        horizons_minutes,
        gap_quarantine_minutes: _asset_report(symbol, segments, horizons_minutes),
    )

    report = module.generate_report(paths, _segments(), (5, 15))

    assert set(report["assets"]) == set(_SYMBOLS)
    assert all(
        asset["evidence_disposition"] == "STOP" for asset in report["assets"].values()
    )
    assert report["execution_authority"] == "none"
    assert report["pnl_claimed"] is False
    module.validate_report(report, horizons=(5, 15))


def test_report_validator_rejects_missing_asset_or_pooled_ic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    paths = _paths(tmp_path)
    monkeypatch.setattr(module, "load_bars", lambda _: pd.DataFrame({"source": ["hl"]}))
    monkeypatch.setattr(
        module,
        "build_component_attribution",
        lambda bars,
        symbol,
        segments,
        horizons_minutes,
        gap_quarantine_minutes: _asset_report(symbol, segments, horizons_minutes),
    )
    report = module.generate_report(paths, _segments(), (5,))
    del report["assets"]["HYPE"]
    with pytest.raises(ValueError, match="all four assets"):
        module.validate_report(report, horizons=(5,))

    report = module.generate_report(paths, _segments(), (5,))
    report["assets"]["BTC"]["pooled_ic"] = 0.9
    with pytest.raises(ValueError, match="pooled IC"):
        module.validate_report(report, horizons=(5,))


def test_failure_or_existing_output_never_publishes_partial_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    paths = _paths(tmp_path)
    output = tmp_path / "report.json"
    monkeypatch.setattr(module, "load_bars", lambda _: pd.DataFrame())
    monkeypatch.setattr(
        module,
        "build_component_attribution",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("failed")),
    )

    with pytest.raises(RuntimeError, match="failed"):
        module.run_attribution(paths, _segments(), (5,), output)
    assert not output.exists()
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.run_attribution(paths, _segments(), (5,), output)
