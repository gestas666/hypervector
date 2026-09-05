#!/usr/bin/env python3
"""Publish one immutable V62 all-executable-route stop diagnostic."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import tomllib

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.route_stop_diagnostic import build_route_stop_diagnostic

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_eight_asset_"
    "sndk_exit_preserved_candidate_v61.toml"
)
_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable diagnostic parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Build one source-bound all-route diagnostic without live authority."""
    config = _toml(args.config)
    checkpoint = _json(args.checkpoint)
    sources = {
        "config": _source_evidence(args.config),
        "checkpoint": _source_evidence(args.checkpoint),
    }
    diagnostic = build_route_stop_diagnostic(config, checkpoint)
    _require_sources_unchanged(args, sources)
    return {
        "schema_version": 1,
        "mode": "v62_all_route_stop_diagnostic_publication",
        "diagnostic": diagnostic,
        "sources": sources,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _toml(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"route diagnostic config is missing: {path}")
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("route diagnostic config must be an object")
    return payload


def _json(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"route diagnostic checkpoint is missing: {path}")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, Mapping):
        raise ValueError("route diagnostic checkpoint must be an object")
    return payload


def _source_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _require_sources_unchanged(
    args: argparse.Namespace,
    sources: Mapping[str, object],
) -> None:
    for name, path in (("config", args.config), ("checkpoint", args.checkpoint)):
        expected = sources.get(name)
        if not isinstance(expected, Mapping):
            raise ValueError(f"route diagnostic source evidence is missing: {name}")
        actual = file_evidence(path)
        if actual.get("sha256") != expected.get("sha256") or actual.get(
            "bytes"
        ) != expected.get("bytes"):
            raise ValueError(f"route diagnostic source changed during run: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Write one immutable diagnostic and print its bounded summary."""
    args = build_parser().parse_args(argv)
    report = run(args)
    write_immutable_json(args.out, report)
    diagnostic = report["diagnostic"]
    if not isinstance(diagnostic, Mapping):
        raise RuntimeError("route diagnostic result is unavailable")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "summary": diagnostic.get("summary"),
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
