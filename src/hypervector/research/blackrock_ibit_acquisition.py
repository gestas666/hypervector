"""Immutable outcome-blind acquisition of official BlackRock IBIT history."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_immutable_parquet,
    write_json,
)
from hypervector.research.blackrock_ibit_history import (
    IBIT_COMPLETE_SHARES_REQUIRED_FROM,
    parse_blackrock_ibit_history,
)


BLACKROCK_IBIT_HISTORY_URL = (
    "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
    "product-data/api/v1/get-fund-document?appSubType=ISHARES&"
    "appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&"
    "portfolioId=333011&targetSite=us-ishares&userType=individual"
)
_SCHEMA_VERSION = "blackrock_ibit_historical_bundle_v1"
_HYPOTHESIS = "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1"


def acquire_blackrock_ibit_history_bundle(
    output: Path,
    fetch_bytes: Callable[[str], bytes],
    *,
    context: dict[str, object],
) -> Path:
    """Fetch and atomically publish source-only IBIT historical evidence."""
    bound_context = _validated_context(context)
    if output.exists():
        raise FileExistsError(f"BlackRock IBIT history bundle already exists: {output}")

    def writer(staging: Path) -> None:
        content = _fetched_bytes(fetch_bytes)
        history = parse_blackrock_ibit_history(
            content,
            allow_share_placeholders_before=IBIT_COMPLETE_SHARES_REQUIRED_FROM,
        )
        _write_bundle(staging, content, history, bound_context)

    publish_immutable_directory(output, writer)
    return output


def _validated_context(context: dict[str, object]) -> dict[str, object]:
    if context.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BlackRock IBIT acquisition hypothesis identity drifted")
    if context.get("execution_authority") != "none":
        raise ValueError("BlackRock IBIT acquisition gained execution authority")
    if context.get("candidate_results_inspected_before_acquisition") is not False:
        raise ValueError(
            "BlackRock IBIT acquisition context contains candidate results"
        )
    preregistration = context.get("preregistration")
    if not isinstance(preregistration, dict) or not preregistration:
        raise ValueError("BlackRock IBIT acquisition lacks preregistration evidence")
    addendum = context.get("source_integrity_addendum")
    if not isinstance(addendum, dict) or not addendum:
        raise ValueError("BlackRock IBIT acquisition lacks source-integrity addendum")
    return dict(context)


def _fetched_bytes(fetch_bytes: Callable[[str], bytes]) -> bytes:
    content = fetch_bytes(BLACKROCK_IBIT_HISTORY_URL)
    if not isinstance(content, bytes) or not content:
        raise ValueError("BlackRock IBIT fund-data fetch returned no bytes")
    return content


def _write_bundle(
    staging: Path,
    content: bytes,
    history: pd.DataFrame,
    context: dict[str, object],
) -> None:
    raw_path = staging / "fund_data.xml"
    history_path = staging / "history.parquet"
    raw_path.write_bytes(content)
    write_immutable_parquet(history_path, history)
    manifest = {
        "schema_version": _SCHEMA_VERSION,
        "source": "blackrock_official_ibit_fund_data_workbook",
        "source_url": BLACKROCK_IBIT_HISTORY_URL,
        "symbol": "IBIT",
        "report_only": True,
        "execution_authority": "none",
        "candidate_outcomes_computed": False,
        "context": context,
        "coverage": _coverage(history),
        "files": {
            "fund_data.xml": file_evidence(raw_path),
            "history.parquet": file_evidence(history_path),
        },
    }
    write_json(staging / "manifest.json", manifest)


def _coverage(history: pd.DataFrame) -> dict[str, object]:
    dates = pd.DatetimeIndex(history["as_of_date"])
    excluded = list(history.attrs.get("excluded_share_placeholder_dates", ()))
    return {
        "rows": len(history),
        "raw_historical_rows": len(history) + len(excluded),
        "normalized_valid_observation_rows": len(history),
        "first_as_of_date": dates[0].date().isoformat(),
        "last_as_of_date": dates[-1].date().isoformat(),
        "duplicate_as_of_dates": 0,
        "split_like_discontinuities": 0,
        "excluded_share_placeholder_rows": len(excluded),
        "excluded_share_placeholder_dates": excluded,
        "candidate_outcomes_computed": False,
    }
