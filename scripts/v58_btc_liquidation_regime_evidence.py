#!/usr/bin/env python3
"""Publish source-bound causal BTC regime labels for V58 research."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_candles import (
    OxaCandleRequest,
    read_complete_candle_evidence,
)
from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_json,
)
from hypervector.regime import classifier as regime_classifier
from hypervector.regime.classifier import RegimeClassifierConfig
from hypervector.research import btc_liquidation_regime_evidence as regime_evidence
from hypervector.research.btc_liquidation_regime_evidence import (
    build_causal_regime_labels,
    regime_config_evidence,
)

_MODE = "v58_btc_liquidation_causal_regime_evidence"
_HYPOTHESIS = "v58-btc-short-liquidation-continuation-long-data-preflight"
_SOURCE_START = datetime(2025, 11, 30, tzinfo=UTC)
_EVALUATION_START = pd.Timestamp("2025-12-01T00:00:00Z")
_EVALUATION_END = pd.Timestamp("2026-06-01T00:00:00Z")
_MINIMUM_CONTEXT_BARS = 288
_BUNDLE = Path(
    "data/cache/vendor/0xarchive/hyperliquid/BTC/"
    "20251130T000000000000Z_20260601T000000000000Z_candles_5m"
)
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_btc_liquidation_causal_regime_evidence_20260822_v1"
)
_LABEL_COLUMNS = (
    "bar_open_at",
    "available_at",
    "in_evaluation_partition",
    "primary_regime",
    "breakout_direction",
    "confidence",
    "regime_strength_score",
    "regime_strength_percentile",
    "reason",
    "coiling",
    "bbwp_percentile",
    "compression_ready",
    "ema_gap_bps_signed",
    "rsi",
    "rsi_ema",
    "rsi_cross_direction",
    "tactical_breakout_direction",
    "breakout_volume_ratio",
    "range_cause_coiling",
    "range_cause_strength",
    "range_cause_gap",
    "range_cause_filter",
)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed, execution-incapable regime-publication parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candle-bundle", type=Path, default=_BUNDLE)
    parser.add_argument("--out", type=Path, default=_OUTPUT)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Publish the frozen V58 BTC development regime covariate."""
    request = OxaCandleRequest(
        symbol="BTC",
        start=_SOURCE_START,
        end=_EVALUATION_END.to_pydatetime(),
        interval="5m",
        limit=10_000,
        max_pages=20,
    )
    return publish_regime_evidence(
        candle_bundle=args.candle_bundle,
        output=args.out,
        request=request,
        evaluation_start=_EVALUATION_START,
        evaluation_end=_EVALUATION_END,
        minimum_context_bars=_MINIMUM_CONTEXT_BARS,
    )


def publish_regime_evidence(
    *,
    candle_bundle: Path,
    output: Path,
    request: OxaCandleRequest,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
    minimum_context_bars: int,
) -> Path:
    """Verify, classify, and atomically publish descriptive regime evidence."""
    if output.exists():
        raise FileExistsError(f"causal regime evidence already exists: {output}")
    candles, source = read_complete_candle_evidence(
        candle_bundle, request, require_complete_cadence=True
    )
    config = RegimeClassifierConfig()
    labels = build_causal_regime_labels(
        candles,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        minimum_context_bars=minimum_context_bars,
        config=config,
    ).loc[:, _LABEL_COLUMNS]
    _, unchanged = read_complete_candle_evidence(
        candle_bundle, request, require_complete_cadence=True
    )
    if unchanged != source:
        raise RuntimeError("candle evidence changed during regime classification")
    report = _build_report(
        labels,
        source=source,
        config=config,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        minimum_context_bars=minimum_context_bars,
    )
    _publish(output, labels, report)
    return output


def _build_report(
    labels: pd.DataFrame,
    *,
    source: dict[str, object],
    config: RegimeClassifierConfig,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
    minimum_context_bars: int,
) -> dict[str, object]:
    evaluation = labels.loc[labels["in_evaluation_partition"]]
    return {
        "schema_version": 1,
        "mode": _MODE,
        "hypothesis_id": _HYPOTHESIS,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "descriptive_evidence_complete",
        "contract": _contract(),
        "evaluation_partition": {
            "start_utc": evaluation_start.isoformat(),
            "end_utc": evaluation_end.isoformat(),
            "minimum_context_bars": minimum_context_bars,
            "bar_interval": "5m",
            "label_available_at": "bar_open_at_plus_5m",
        },
        "source_evidence": source,
        "classifier_evidence": _classifier_evidence(config),
        "summary": {
            "label_rows": len(labels),
            "evaluation_rows": len(evaluation),
            "context_rows": len(labels) - len(evaluation),
            "evaluation_primary_regime_counts": _value_counts(
                evaluation["primary_regime"]
            ),
        },
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "strategy_mutation": False,
        "market_returns_computed": False,
        "pnl_computed": False,
        "validation_and_pseudo_outcomes_opened": False,
        "regime_labels_are_entry_gates": False,
        "regime_labels_are_descriptive_covariates": True,
    }


def _classifier_evidence(config: RegimeClassifierConfig) -> dict[str, object]:
    paths = (
        Path(regime_classifier.__file__),
        Path(regime_evidence.__file__),
        Path(__file__),
    )
    return {
        "configuration": regime_config_evidence(config),
        "source_files": [
            {"path": str(path.resolve()), **file_evidence(path)} for path in paths
        ],
    }


def _value_counts(values: pd.Series) -> dict[str, int]:
    counts = values.value_counts(dropna=False).sort_index()
    return {str(key): int(value) for key, value in counts.items()}


def _publish(output: Path, labels: pd.DataFrame, report: dict[str, object]) -> None:
    def writer(staging: Path) -> None:
        labels_path = staging / "labels.parquet"
        labels.to_parquet(labels_path, index=False)
        report_path = staging / "report.json"
        write_json(report_path, report)
        write_json(
            staging / "manifest.json",
            {
                "schema_version": "immutable_evidence_manifest_v1",
                "files": {
                    path.name: file_evidence(path)
                    for path in (labels_path, report_path)
                },
            },
        )

    publish_immutable_directory(output, writer)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only publication and print its immutable path."""
    output = run_command(build_parser().parse_args(argv))
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
