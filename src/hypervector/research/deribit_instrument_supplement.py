"""Immutable exact-name Deribit instrument metadata supplement."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    gzip_text_writer,
    open_text_reader,
    publish_immutable_directory,
    verify_file_evidence,
    write_json,
)
from hypervector.research.deribit_option_trade_acquisition import (
    OptionInstrument,
    parse_exact_instrument,
)


_SCHEMA = "deribit_btc_exact_instrument_supplement_v1"
_HYPOTHESIS = "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1"


class InstrumentFetcher(Protocol):
    """Fetch one official exact-instrument response by name."""

    def __call__(self, instrument_name: str) -> bytes:
        """Return raw official response bytes for the exact name."""
        ...


@dataclass(frozen=True)
class DeribitInstrumentSupplementAudit:
    """Independent raw-to-Parquet reproduction result."""

    bundle: str
    manifest: dict[str, object]
    instrument_rows: int
    raw_pages: int
    rows_match: bool
    all_registered_files_verified: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible audit record."""
        return asdict(self)


def acquire_deribit_instrument_supplement(
    output: Path,
    names: Sequence[str],
    fetch: InstrumentFetcher,
    *,
    max_workers: int,
    context: Mapping[str, object],
) -> Path:
    """Fetch exact missing names and atomically publish source-only evidence."""
    ordered = _validated_names(names)
    bound_context = _validated_context(context)
    if max_workers < 1 or max_workers > 16:
        raise ValueError("Deribit instrument supplement workers must be in [1, 16]")

    def writer(staging: Path) -> None:
        _write_bundle(staging, ordered, fetch, max_workers, bound_context)

    publish_immutable_directory(output, writer)
    return output


def reproduce_deribit_instrument_supplement(
    bundle: Path,
) -> DeribitInstrumentSupplementAudit:
    """Reparse every raw exact-name page and compare normalized rows exactly."""
    manifest_path = bundle / "manifest.json"
    manifest = _load_mapping(manifest_path)
    _validate_manifest(manifest)
    verify_file_evidence(bundle, manifest.get("files"))
    requests = manifest.get("requests")
    if not isinstance(requests, list) or not requests:
        raise ValueError("Deribit instrument supplement has no requests")
    raw = [
        _raw_instrument(bundle, value, index) for index, value in enumerate(requests)
    ]
    normalized = _normalized_instruments(bundle / "instruments.parquet")
    coverage = _mapping(manifest, "coverage")
    if coverage.get("instrument_rows") != len(raw) or len(raw) != len(normalized):
        raise ValueError("Deribit instrument supplement row count drifted")
    if raw != normalized:
        raise ValueError("Deribit instrument supplement raw rows do not reproduce")
    return DeribitInstrumentSupplementAudit(
        str(bundle.resolve()),
        file_evidence(manifest_path),
        len(normalized),
        len(requests),
        True,
        True,
    )


def _write_bundle(
    staging: Path,
    names: tuple[str, ...],
    fetch: InstrumentFetcher,
    max_workers: int,
    context: dict[str, object],
) -> None:
    raw_directory = staging / "raw"
    raw_directory.mkdir()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        contents = tuple(executor.map(fetch, names))
    instruments = tuple(
        parse_exact_instrument(content, name)
        for name, content in zip(names, contents, strict=True)
    )
    files: dict[str, dict[str, object]] = {}
    requests: list[dict[str, object]] = []
    for page, (name, content) in enumerate(zip(names, contents, strict=True), start=1):
        relative = f"raw/instrument_{page:06d}.json.gz"
        path = staging / relative
        _write_raw(path, content)
        files[relative] = file_evidence(path)
        requests.append({"page": page, "instrument_name": name, "raw_file": relative})
    path = staging / "instruments.parquet"
    pd.DataFrame.from_records([asdict(value) for value in instruments]).to_parquet(
        path, index=False
    )
    files["instruments.parquet"] = file_evidence(path)
    write_json(staging / "manifest.json", _manifest(context, requests, files))


def _manifest(
    context: dict[str, object],
    requests: list[dict[str, object]],
    files: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA,
        "source": "deribit_official_exact_instrument_metadata",
        "symbol": "BTC",
        "report_only": True,
        "execution_authority": "none",
        "candidate_signals_computed": False,
        "candidate_outcomes_computed": False,
        "context": context,
        "coverage": {
            "instrument_rows": len(requests),
            "request_count": len(requests),
        },
        "requests": requests,
        "files": files,
    }


def _raw_instrument(
    bundle: Path, value: object, expected_page: int
) -> OptionInstrument:
    if not isinstance(value, dict) or value.get("page") != expected_page + 1:
        raise ValueError("Deribit instrument supplement request order drifted")
    name = value.get("instrument_name")
    relative = value.get("raw_file")
    if not isinstance(name, str) or not isinstance(relative, str):
        raise ValueError("Deribit instrument supplement request is invalid")
    path = bundle / relative
    with open_text_reader(path) as handle:
        return parse_exact_instrument(handle.read().encode("utf-8"), name)


def _normalized_instruments(path: Path) -> list[OptionInstrument]:
    rows = pd.read_parquet(path).to_dict("records")
    return [
        OptionInstrument(
            instrument_name=str(row["instrument_name"]),
            creation_timestamp_ms=int(row["creation_timestamp_ms"]),
            expiration_timestamp_ms=int(row["expiration_timestamp_ms"]),
            strike=float(row["strike"]),
            option_type=str(row["option_type"]),
            contract_size=float(row["contract_size"]),
        )
        for row in rows
    ]


def _validated_names(names: Sequence[str]) -> tuple[str, ...]:
    ordered = tuple(names)
    if not ordered or any(not isinstance(name, str) or not name for name in ordered):
        raise ValueError("Deribit instrument supplement names are invalid")
    if tuple(sorted(set(ordered))) != ordered:
        raise ValueError(
            "Deribit instrument supplement names must be sorted and unique"
        )
    return ordered


def _validated_context(value: Mapping[str, object]) -> dict[str, object]:
    expected = {
        "hypothesis_id": _HYPOTHESIS,
        "execution_authority": "none",
        "live_change_authorized": False,
        "candidate_signals_computed": False,
        "candidate_outcomes_computed": False,
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("Deribit instrument supplement context gained authority")
    for key in ("completeness_audit", "preregistration"):
        evidence = value.get(key)
        if not isinstance(evidence, dict) or not isinstance(
            evidence.get("sha256"), str
        ):
            raise ValueError(f"Deribit instrument supplement lacks {key}")
    return dict(value)


def _validate_manifest(value: Mapping[str, object]) -> None:
    expected = {
        "schema_version": _SCHEMA,
        "source": "deribit_official_exact_instrument_metadata",
        "symbol": "BTC",
        "report_only": True,
        "execution_authority": "none",
        "candidate_signals_computed": False,
        "candidate_outcomes_computed": False,
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("Deribit instrument supplement manifest drifted")
    _validated_context(_mapping(value, "context"))


def _write_raw(path: Path, content: bytes) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Deribit instrument supplement response is not UTF-8") from exc
    with gzip_text_writer(path) as handle:
        handle.write(text)


def _load_mapping(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Deribit instrument supplement manifest must be an object")
    return value


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"Deribit instrument supplement lacks object: {key}")
    return nested
