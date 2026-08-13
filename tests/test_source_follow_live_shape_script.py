"""CLI-boundary tests for the deployed BTC source-follow shape replay."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd

from hypervector.data.oxa_storage import file_evidence

SCRIPT = Path(__file__).parents[1] / "scripts" / "source_follow_live_shape_replay.py"
COHORT_CONFIG = Path("configs/multi_asset_bidirectional_canary.toml")
SOURCE_PROFILE = Path(
    "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow.toml"
)


def _load_module() -> ModuleType:
    spec = spec_from_file_location("source_follow_live_shape_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_bars(path: Path) -> None:
    timestamps = pd.date_range("2026-01-01", periods=20, freq="1min", tz="UTC")
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 100.2,
            "low": 99.8,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl",
        }
    ).to_parquet(path, index=False)


def _write_labels(labels_path: Path, metadata_path: Path) -> None:
    index = pd.date_range("2026-01-01", periods=4, freq="5min", tz="UTC")
    labels = pd.DataFrame(
        {
            "available_at": index + pd.Timedelta(minutes=5),
            "primary_code": ["UNKNOWN", "TREND_UP", "RANGE", "TREND_DOWN"],
            "secondary_code": [None, None, None, None],
            "confidence": [0.0, 0.9, 0.8, 0.9],
        },
        index=index,
    )
    labels.index.name = "timestamp"
    labels.to_parquet(labels_path)
    metadata_path.write_text(
        json.dumps(
            {
                "upstream_revision": "ad15f2bdc949619be495a5f516babd08f7f52a90",
                "output": file_evidence(labels_path),
            }
        ),
        encoding="utf-8",
    )


def _write_funding(path: Path) -> None:
    pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01T00:00:00Z")],
            "funding_rate": [0.00001],
            "source": ["hl_funding_history"],
        }
    ).to_parquet(path, index=False)


def test_report_uses_current_cohort_execution_contract(tmp_path: Path) -> None:
    """The research replay must not inherit the old maker/no-stop profile."""
    module = _load_module()
    bars = tmp_path / "bars.parquet"
    labels = tmp_path / "labels.parquet"
    metadata = tmp_path / "labels.json"
    funding = tmp_path / "funding.parquet"
    _write_bars(bars)
    _write_labels(labels, metadata)
    _write_funding(funding)
    args = module.build_parser().parse_args(
        [
            "--cohort-config",
            str(COHORT_CONFIG),
            "--source-profile",
            str(SOURCE_PROFILE),
            "--labels",
            str(labels),
            "--labels-metadata",
            str(metadata),
            "--candles",
            str(bars),
            "--funding",
            str(funding),
            "--out",
            str(tmp_path / "report.json"),
        ]
    )

    report = module.build_report(args)

    contract = report["deployed_contract"]
    assert contract["entry_liquidity"] == "taker_ioc"
    assert contract["stop_bps"] == 80.0
    assert contract["target_bps"] == 26.6666666667
    assert contract["maximum_hold_seconds"] == 86_400
    assert contract["leverage"] == 5.0
    assert contract["margin_fraction"] == 0.03
    assert contract["maximum_notional_usd"] == 25.0
    assert report["signal_audit"]["eligible_events"] == 2
    assert report["replay"]["signal_count"] == 2
    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
