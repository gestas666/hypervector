#!/usr/bin/env python3
"""Register exact BTC OI-expansion preflight inputs before cadence counting."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import sys
from typing import Protocol, cast

from hypervector.data.oxa_storage import write_immutable_json


class _PreflightApi(Protocol):
    _PREREGISTRATION: Path
    _REGISTRATION_SCHEMA: str
    _REGISTRATION_STATUS: str
    _HYPOTHESIS: str

    def _validated_preregistration(self, path: Path) -> dict[str, object]: ...

    def _generator_identity(self, project_root: Path) -> dict[str, object]: ...

    def _analysis_bounds(self) -> tuple[datetime, datetime]: ...

    def source_evidence(
        self, database: Path, start: datetime, end: datetime
    ) -> dict[str, object]: ...


def _load_preflight() -> _PreflightApi:
    source = Path(__file__).with_name("v58_btc_oi_expansion_preflight.py")
    spec = importlib.util.spec_from_file_location(
        "v58_btc_oi_expansion_preflight", source
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("BTC OI-expansion preflight module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast(_PreflightApi, module)


preflight = _load_preflight()


_DATABASE = Path("data/research/market.duckdb")
_OUTPUT = Path(
    "docs/research-journal/"
    "v58-btc-oi-expansion-flow-continuation-preflight-"
    "input-registration-20260821-v2.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the outcome-blind input-registration parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=_DATABASE)
    parser.add_argument(
        "--preregistration", type=Path, default=preflight._PREREGISTRATION
    )
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    return parser


def build_registration_payload(
    preregistration: dict[str, object],
    generators: dict[str, object],
    sources: dict[str, object],
    *,
    generated_at: datetime,
) -> dict[str, object]:
    """Build a source-bound record containing no cadence or outcome evidence."""
    if generated_at.tzinfo is None:
        raise ValueError("BTC OI-expansion registration time must be timezone-aware")
    return {
        "schema_version": preflight._REGISTRATION_SCHEMA,
        "hypothesis_id": preflight._HYPOTHESIS,
        "generated_at_utc": generated_at.astimezone(UTC).isoformat(),
        "status": preflight._REGISTRATION_STATUS,
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "outcomes_computed": False,
            "live_change": False,
        },
        "change_scope": {
            "candidate_counts_inspected": False,
            "automatic_promotion": False,
            "runtime_strategy_changed": False,
            "orders_supported": False,
        },
        "preregistration": preregistration,
        "generator_identity": generators,
        "source_evidence": sources,
    }


def publish_registration(output: Path, payload: dict[str, object]) -> None:
    """Publish one immutable input-registration JSON file."""
    write_immutable_json(output, payload)


def run_command(args: argparse.Namespace) -> Path:
    """Hash only frozen inputs and publish their immutable registration."""
    if args.output.exists():
        raise FileExistsError(
            f"BTC OI-expansion input registration already exists: {args.output}"
        )
    project_root = Path(__file__).resolve().parents[1]
    preregistration = preflight._validated_preregistration(args.preregistration)
    generators = preflight._generator_identity(project_root)
    start, end = preflight._analysis_bounds()
    sources = preflight.source_evidence(args.database, start, end)
    payload = build_registration_payload(
        preregistration,
        generators,
        sources,
        generated_at=datetime.now(UTC),
    )
    publish_registration(args.output, payload)
    return args.output


def main(argv: Sequence[str] | None = None) -> int:
    """Publish the outcome-blind input registration and print its path."""
    output = run_command(build_parser().parse_args(argv))
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
