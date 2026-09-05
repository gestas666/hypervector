"""Verified vectorized materialization of registered BTC option flow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.oxa_storage import file_evidence, verify_file_evidence


_SCHEMA = "deribit_btc_option_flow_source_bundle_v1"
_MINIMUM_TRADES_PER_HOUR = 20
_BASE_CTE = """
WITH joined AS (
    SELECT
        t.*,
        i.expiration_timestamp_ms,
        i.strike,
        i.option_type,
        i.contract_size,
        i.instrument_name AS matched_instrument,
        (i.expiration_timestamp_ms - t.timestamp_ms) / 86400000.0 AS expiry_days
    FROM read_parquet(?) AS t
    LEFT JOIN read_parquet(?) AS i USING (instrument_name)
    WHERE t.timestamp_ms >= ? AND t.timestamp_ms < ?
), inputs AS (
    SELECT *,
        (ln(index_price / strike)
         + 0.5 * pow(iv / 100.0, 2) * (expiry_days / 365.0))
        / ((iv / 100.0) * sqrt(expiry_days / 365.0)) AS d1
    FROM joined
    WHERE matched_instrument IS NOT NULL
      AND block_trade_id IS NULL
      AND block_rfq_id IS NULL
      AND combo_id IS NULL
      AND combo_trade_id IS NULL
      AND iv > 0.0
      AND index_price > 0.0
      AND amount > 0.0
      AND strike > 0.0
      AND contract_size > 0.0
      AND expiry_days BETWEEN 1.0 AND 21.0
), deltas AS (
    SELECT *, CASE
        WHEN option_type = 'call' THEN normal_cdf(d1)
        WHEN option_type = 'put' THEN 1.0 - normal_cdf(d1)
        ELSE NULL
    END AS absolute_delta
    FROM inputs
), eligible AS (
    SELECT *,
        amount * contract_size * index_price * absolute_delta AS weight_usd,
        CASE
            WHEN (direction = 'buy' AND option_type = 'call')
              OR (direction = 'sell' AND option_type = 'put') THEN 1.0
            ELSE -1.0
        END AS flow_sign
    FROM deltas
    WHERE absolute_delta > 0.02 AND absolute_delta <= 0.375
)
"""


@dataclass(frozen=True)
class DeribitOptionSourceAudit:
    """Integrity and exclusion counts for one exact option-flow window."""

    bundle: str
    manifest: dict[str, object]
    trades: dict[str, object]
    instruments: dict[str, object]
    supplemental_instruments: dict[str, object] | None
    trade_rows: int
    analysis_trade_rows: int
    eligible_trade_rows: int
    excluded_nonordinary_rows: int
    excluded_invalid_feature_rows: int
    excluded_delta_rows: int
    unmatched_instrument_rows: int
    raw_trade_pages_verified: int
    all_registered_files_verified: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible source-audit record."""
        return asdict(self)


def materialize_registered_hourly_flow(
    bundle: Path,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    expected_preregistration_sha256: str,
    supplemental_instruments_path: Path | None = None,
) -> tuple[pd.DataFrame, DeribitOptionSourceAudit]:
    """Verify a registered bundle and aggregate the frozen causal flow feature."""
    start_at, end_at = _validated_bounds(start, end)
    manifest = _validated_manifest(bundle, expected_preregistration_sha256)
    trades_path = bundle / "trades.parquet"
    base_instruments_path = bundle / "instruments.parquet"
    instrument_paths = (base_instruments_path,) + (
        (supplemental_instruments_path,)
        if supplemental_instruments_path is not None
        else ()
    )
    connection = duckdb.connect(":memory:")
    try:
        connection.create_function("normal_cdf", _normal_cdf, ["DOUBLE"], "DOUBLE")
        source_counts = _validate_normalized_source(
            connection, trades_path, instrument_paths, manifest
        )
        rows = _aggregate_rows(
            connection, trades_path, instrument_paths, start_at, end_at
        )
        exclusions = _exclusion_counts(
            connection, trades_path, instrument_paths, start_at, end_at
        )
    finally:
        connection.close()
    hourly = _complete_hourly(rows, start_at, end_at)
    audit = _source_audit(
        bundle,
        manifest,
        source_counts,
        exclusions,
        supplemental_instruments_path,
    )
    return hourly, audit


def _validated_manifest(
    bundle: Path,
    expected_preregistration_sha256: str,
) -> dict[str, object]:
    path = bundle / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Deribit option-flow manifest is missing: {path}")
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Deribit option-flow manifest must be an object")
    expected = {
        "schema_version": _SCHEMA,
        "source": "deribit_official_btc_option_trades",
        "symbol": "BTC",
        "report_only": True,
        "execution_authority": "none",
        "candidate_outcomes_computed": False,
    }
    if value.get("execution_authority") != "none":
        raise ValueError("Deribit option-flow manifest gained execution authority")
    if any(
        value.get(key) != expected_value for key, expected_value in expected.items()
    ):
        raise ValueError("Deribit option-flow manifest identity drifted")
    _validate_context(value, expected_preregistration_sha256)
    verify_file_evidence(bundle, value.get("files"))
    return value


def _validate_context(value: Mapping[str, object], expected_sha256: str) -> None:
    context = _mapping(value, "context")
    if context.get("execution_authority") != "none":
        raise ValueError("Deribit option-flow context gained execution authority")
    if context.get("candidate_outcomes_inspected_before_acquisition") is not False:
        raise ValueError("Deribit option-flow acquisition context contains outcomes")
    if context.get("live_change_authorized") is not False:
        raise ValueError(
            "Deribit option-flow acquisition context authorizes live change"
        )
    preregistration = _mapping(context, "preregistration")
    if preregistration.get("sha256") != expected_sha256:
        raise ValueError("Deribit option-flow preregistration hash drifted")


def _validate_normalized_source(
    connection: duckdb.DuckDBPyConnection,
    trades: Path,
    instruments: Sequence[Path],
    manifest: Mapping[str, object],
) -> tuple[int, int]:
    trade_values = _one(
        connection,
        "SELECT count(*), count(DISTINCT trade_id) FROM read_parquet(?)",
        [str(trades)],
    )
    trade_rows, unique_trades = _integers(trade_values, "trade counts")
    if trade_rows != unique_trades:
        raise ValueError(
            "Deribit option-flow normalized source has duplicate trade IDs"
        )
    base_values = _one(
        connection,
        "SELECT count(*), count(DISTINCT instrument_name) FROM read_parquet(?)",
        [str(instruments[0])],
    )
    base_rows, base_unique = _integers(base_values, "base instrument counts")
    if base_rows != base_unique:
        raise ValueError("Deribit option-flow source has duplicate instrument names")
    _validate_manifest_counts(manifest, trade_rows, base_rows)
    instrument_values = _one(
        connection,
        "SELECT count(*), count(DISTINCT instrument_name) FROM read_parquet(?)",
        [[str(path) for path in instruments]],
    )
    instrument_rows, unique_instruments = _integers(
        instrument_values, "combined instrument counts"
    )
    if instrument_rows != unique_instruments:
        raise ValueError("Deribit option-flow combined instruments contain duplicates")
    _validate_all_instruments_join(connection, trades, instruments)
    return trade_rows, instrument_rows


def _validate_manifest_counts(
    manifest: Mapping[str, object], trade_rows: int, instrument_rows: int
) -> None:
    coverage = _mapping(manifest, "coverage")
    if coverage.get("trade_rows") != trade_rows:
        raise ValueError("Deribit option-flow manifest trade count drifted")
    if coverage.get("instrument_rows") != instrument_rows:
        raise ValueError("Deribit option-flow manifest instrument count drifted")
    raw_pages = _integer(coverage.get("raw_trade_pages"), "raw trade-page count")
    parent_pages = _integer(coverage.get("truncated_pages"), "split parent-page count")
    if parent_pages >= raw_pages:
        raise ValueError("Deribit option-flow source has no complete terminal pages")


def _validate_all_instruments_join(
    connection: duckdb.DuckDBPyConnection,
    trades: Path,
    instruments: Sequence[Path],
) -> None:
    row = _one(
        connection,
        """SELECT count(*) FROM read_parquet(?) AS t
        LEFT JOIN read_parquet(?) AS i USING (instrument_name)
        WHERE i.instrument_name IS NULL""",
        [str(trades), [str(path) for path in instruments]],
    )
    if _integer(row[0], "unmatched instrument count") != 0:
        raise ValueError("Deribit option-flow trades are missing instrument metadata")


def _aggregate_rows(
    connection: duckdb.DuckDBPyConnection,
    trades: Path,
    instruments: Sequence[Path],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[tuple[object, ...]]:
    query = (
        _BASE_CTE
        + """
    SELECT floor(timestamp_ms / 3600000) * 3600000 AS hour_ms,
           count(*) AS eligible_trade_count,
           sum(weight_usd) AS weight_usd,
           sum(flow_sign * weight_usd) AS signed_weight_usd
    FROM eligible GROUP BY hour_ms ORDER BY hour_ms
    """
    )
    return connection.execute(
        query, _parameters(trades, instruments, start, end)
    ).fetchall()


def _exclusion_counts(
    connection: duckdb.DuckDBPyConnection,
    trades: Path,
    instruments: Sequence[Path],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[int, int, int, int, int]:
    query = (
        _BASE_CTE
        + """
    SELECT
      (SELECT count(*) FROM joined),
      (SELECT count(*) FROM joined WHERE block_trade_id IS NOT NULL
        OR block_rfq_id IS NOT NULL OR combo_id IS NOT NULL
        OR combo_trade_id IS NOT NULL),
      (SELECT count(*) FROM joined WHERE block_trade_id IS NULL
        AND block_rfq_id IS NULL AND combo_id IS NULL AND combo_trade_id IS NULL
        AND (iv <= 0.0 OR index_price <= 0.0 OR amount <= 0.0 OR strike <= 0.0
          OR contract_size <= 0.0 OR expiry_days NOT BETWEEN 1.0 AND 21.0)),
      (SELECT count(*) FROM deltas
        WHERE absolute_delta <= 0.02 OR absolute_delta > 0.375),
      (SELECT count(*) FROM eligible)
    """
    )
    values = _one(connection, query, _parameters(trades, instruments, start, end))
    result = _integers(values, "option-flow exclusion counts")
    if len(result) != 5:
        raise ValueError("option-flow exclusion query returned the wrong width")
    return result[0], result[1], result[2], result[3], result[4]


def _complete_hourly(
    rows: list[tuple[object, ...]], start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    frame = pd.DataFrame.from_records(
        rows,
        columns=(
            "hour_ms",
            "eligible_trade_count",
            "weight_usd",
            "signed_weight_usd",
        ),
    )
    if frame.empty:
        grouped = pd.DataFrame(
            columns=("eligible_trade_count", "weight_usd", "signed_weight_usd")
        )
    else:
        frame["timestamp"] = pd.to_datetime(frame.pop("hour_ms"), unit="ms", utc=True)
        grouped = frame.set_index("timestamp")
    hours = pd.date_range(start, end, freq="1h", inclusive="left")
    output = grouped.reindex(hours).fillna(0.0)
    output.index.name = "timestamp"
    output["eligible_trade_count"] = output["eligible_trade_count"].astype(int)
    eligible = output["eligible_trade_count"].ge(_MINIMUM_TRADES_PER_HOUR)
    output["directional_imbalance"] = (
        output["signed_weight_usd"] / output["weight_usd"]
    ).where(eligible)
    return output.reset_index()


def _source_audit(
    bundle: Path,
    manifest: Mapping[str, object],
    source_counts: tuple[int, int],
    exclusions: tuple[int, int, int, int, int],
    supplemental_instruments_path: Path | None,
) -> DeribitOptionSourceAudit:
    coverage = _mapping(manifest, "coverage")
    return DeribitOptionSourceAudit(
        bundle=str(bundle.resolve()),
        manifest=file_evidence(bundle / "manifest.json"),
        trades=file_evidence(bundle / "trades.parquet"),
        instruments=file_evidence(bundle / "instruments.parquet"),
        supplemental_instruments=(
            file_evidence(supplemental_instruments_path)
            if supplemental_instruments_path is not None
            else None
        ),
        trade_rows=source_counts[0],
        analysis_trade_rows=exclusions[0],
        eligible_trade_rows=exclusions[4],
        excluded_nonordinary_rows=exclusions[1],
        excluded_invalid_feature_rows=exclusions[2],
        excluded_delta_rows=exclusions[3],
        unmatched_instrument_rows=0,
        raw_trade_pages_verified=_integer(
            coverage.get("raw_trade_pages"), "raw trade-page count"
        ),
        all_registered_files_verified=True,
    )


def _validated_bounds(
    start: pd.Timestamp, end: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_at, end_at = pd.Timestamp(start), pd.Timestamp(end)
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise ValueError("option-flow analysis bounds must be timezone-aware")
    start_at, end_at = start_at.tz_convert("UTC"), end_at.tz_convert("UTC")
    if start_at != start_at.floor("h") or end_at != end_at.floor("h"):
        raise ValueError("option-flow analysis bounds must be hour-aligned")
    if end_at <= start_at:
        raise ValueError("option-flow analysis bounds must be increasing")
    return start_at, end_at


def _parameters(
    trades: Path,
    instruments: Sequence[Path],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[object]:
    return [
        str(trades),
        [str(path) for path in instruments],
        int(start.timestamp() * 1_000),
        int(end.timestamp() * 1_000),
    ]


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"Deribit option-flow manifest lacks object: {key}")
    return nested


def _one(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    parameters: Sequence[object],
) -> tuple[object, ...]:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise ValueError("Deribit option-flow integrity query returned no row")
    return row


def _integers(values: Sequence[object], label: str) -> tuple[int, ...]:
    return tuple(_integer(value, label) for value in values)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Deribit option-flow {label} is not a nonnegative integer")
    return value


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))
