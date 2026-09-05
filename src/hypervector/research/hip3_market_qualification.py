"""Pure, execution-incapable qualification for proposed HIP-3 roster markets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from hypervector.data.oxa_api import validate_hip3_symbol as _validate_hip3_symbol
from hypervector.live.hyperliquid_perp_parsing import parse_book_for_symbol
from hypervector.live.hyperliquid_sol_parsing import (
    HyperliquidAdapterError,
    mapping,
    nonnegative_integer,
    number,
    positive_integer,
    positive_number,
    sequence,
    text,
)

_CANDLE_INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000}
_PUBLIC_CANDLE_ROW_CAP = 5_000


class Hip3QualificationError(ValueError):
    """HIP-3 market evidence is absent, malformed, or internally inconsistent."""


def build_hip3_market_qualification(
    *,
    dex: object,
    metadata: object,
    spot_metadata: object,
    contexts: object,
    books: Mapping[str, object],
    candles: Mapping[str, Mapping[str, Sequence[object]]],
    requested_symbols: tuple[str, ...],
    observed_at_utc: str,
) -> dict[str, object]:
    """Build one report-only qualification snapshot from official API payloads."""
    try:
        return _build_report(
            dex=dex,
            metadata=metadata,
            spot_metadata=spot_metadata,
            contexts=contexts,
            books=books,
            candles=candles,
            requested_symbols=requested_symbols,
            observed_at_utc=observed_at_utc,
        )
    except (HyperliquidAdapterError, TypeError, ValueError) as exc:
        if isinstance(exc, Hip3QualificationError):
            raise
        raise Hip3QualificationError(str(exc)) from exc


def validate_hip3_symbol(value: str) -> tuple[str, str]:
    """Return the exact lower-case dex and upper-case asset namespace."""
    try:
        return _validate_hip3_symbol(value)
    except ValueError as exc:
        raise Hip3QualificationError(str(exc)) from exc


def _build_report(
    *,
    dex: object,
    metadata: object,
    spot_metadata: object,
    contexts: object,
    books: Mapping[str, object],
    candles: Mapping[str, Mapping[str, Sequence[object]]],
    requested_symbols: tuple[str, ...],
    observed_at_utc: str,
) -> dict[str, object]:
    if not requested_symbols or len(set(requested_symbols)) != len(requested_symbols):
        raise Hip3QualificationError(
            "requested HIP-3 symbols must be non-empty and unique"
        )
    observed = _observed_at(observed_at_utc)
    dex_record = mapping(dex, "perp dex")
    dex_name = text(dex_record.get("name"), "perp dex name")
    _require_requested_dex(requested_symbols, dex_name)
    metadata_record = mapping(metadata, "HIP-3 metadata")
    collateral_index = nonnegative_integer(
        metadata_record.get("collateralToken"), "collateralToken"
    )
    universe, aligned_contexts = _aligned_market_rows(metadata_record, contexts)
    margin_tables = _margin_tables(metadata_record)
    market_rows = _market_reports(
        requested_symbols,
        universe,
        aligned_contexts,
        dex_record,
        margin_tables,
        books,
        candles,
    )
    return {
        "schema_version": 1,
        "mode": "hip3_market_qualification_v1",
        "status": "qualified_for_observation_only",
        "observed_at_utc": observed,
        "dex": dex_name,
        "collateral_token_index": collateral_index,
        "collateral": _collateral(spot_metadata, collateral_index),
        "symbols": list(requested_symbols),
        "markets": market_rows,
        "readiness": _market_readiness(market_rows),
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _market_readiness(markets: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return _readiness(
        all(bool(row["margin_table_details_available"]) for row in markets),
        all(row["positive_fee_multiplier_vs_native"] is not None for row in markets),
    )


def _market_reports(
    symbols: tuple[str, ...],
    universe: tuple[Mapping[str, object], ...],
    contexts: tuple[Mapping[str, object], ...],
    dex: Mapping[str, object],
    margin_tables: Mapping[int, list[dict[str, float | int]]],
    books: Mapping[str, object],
    candles: Mapping[str, Mapping[str, Sequence[object]]],
) -> list[dict[str, object]]:
    return [
        _market_report(
            symbol=symbol,
            universe=universe,
            contexts=contexts,
            dex=dex,
            margin_tables=margin_tables,
            book=books.get(symbol),
            candles=candles.get(symbol),
        )
        for symbol in symbols
    ]


def _market_report(
    *,
    symbol: str,
    universe: tuple[Mapping[str, object], ...],
    contexts: tuple[Mapping[str, object], ...],
    dex: Mapping[str, object],
    margin_tables: Mapping[int, list[dict[str, float | int]]],
    book: object | None,
    candles: Mapping[str, Sequence[object]] | None,
) -> dict[str, object]:
    index, market = _market_identity(universe, symbol)
    if book is None:
        raise Hip3QualificationError(f"{symbol} live book is unavailable")
    if candles is None:
        raise Hip3QualificationError(f"{symbol} candles are unavailable")
    context = contexts[index]
    margin_table_id = positive_integer(
        market.get("marginTableId"), f"{symbol} marginTableId"
    )
    tiers = margin_tables.get(margin_table_id, [])
    return {
        "symbol": symbol,
        "size_decimals": nonnegative_integer(
            market.get("szDecimals"), f"{symbol} szDecimals"
        ),
        "max_leverage": positive_integer(
            market.get("maxLeverage"), f"{symbol} maxLeverage"
        ),
        "margin_table_id": margin_table_id,
        "margin_table_details_available": bool(tiers),
        "margin_tiers": tiers,
        **_fee_evidence(dex, market, symbol),
        "streaming_open_interest_cap_usd": _pair_value(
            dex, "assetToStreamingOiCap", symbol
        ),
        "funding_multiplier": _pair_value(dex, "assetToFundingMultiplier", symbol),
        "market": _market_context(context, symbol),
        "book": _book_report(book, symbol),
        "candles": _candle_reports(candles, symbol),
    }


def _fee_evidence(
    dex: Mapping[str, object],
    market: Mapping[str, object],
    symbol: str,
) -> dict[str, float | str | None]:
    fee_scale = _deployer_fee_scale(market, dex)
    raw_growth_mode = market.get("growthMode")
    if raw_growth_mode is None:
        return {
            "growth_mode": None,
            "deployer_fee_scale": fee_scale,
            "positive_fee_multiplier_vs_native": None,
        }
    growth_mode = text(raw_growth_mode, f"{symbol} growthMode")
    if growth_mode not in {"enabled", "disabled"}:
        raise Hip3QualificationError(f"{symbol} growthMode is unsupported")
    return {
        "growth_mode": growth_mode,
        "deployer_fee_scale": fee_scale,
        "positive_fee_multiplier_vs_native": _positive_fee_multiplier(
            fee_scale, growth_mode == "enabled"
        ),
    }


def _aligned_market_rows(
    metadata: Mapping[str, object],
    contexts: object,
) -> tuple[tuple[Mapping[str, object], ...], tuple[Mapping[str, object], ...]]:
    raw_universe = sequence(metadata.get("universe"), "market universe")
    raw_contexts = sequence(contexts, "market contexts")
    if len(raw_universe) != len(raw_contexts):
        raise Hip3QualificationError("HIP-3 metadata and context lengths differ")
    universe = tuple(mapping(row, "market metadata") for row in raw_universe)
    aligned = tuple(mapping(row, "market context") for row in raw_contexts)
    return universe, aligned


def _market_identity(
    universe: tuple[Mapping[str, object], ...],
    symbol: str,
) -> tuple[int, Mapping[str, object]]:
    matches = [
        (index, row) for index, row in enumerate(universe) if row.get("name") == symbol
    ]
    if len(matches) != 1:
        raise Hip3QualificationError(
            f"{symbol} metadata must contain exactly one market"
        )
    return matches[0]


def _market_context(value: Mapping[str, object], symbol: str) -> dict[str, float]:
    return {
        "mark_price": positive_number(value.get("markPx"), f"{symbol} markPx"),
        "mid_price": positive_number(value.get("midPx"), f"{symbol} midPx"),
        "oracle_price": positive_number(value.get("oraclePx"), f"{symbol} oraclePx"),
        "funding_rate": number(value.get("funding"), f"{symbol} funding"),
        "open_interest_base": positive_number(
            value.get("openInterest"), f"{symbol} openInterest"
        ),
        "day_notional_volume_usd": positive_number(
            value.get("dayNtlVlm"), f"{symbol} dayNtlVlm"
        ),
    }


def _book_report(value: object, symbol: str) -> dict[str, float | int]:
    parsed = parse_book_for_symbol(value, symbol=symbol, depth_levels=20)
    return {
        "exchange_timestamp_ms": parsed.exchange_timestamp_ms,
        "best_bid": parsed.bids[0].price,
        "best_ask": parsed.asks[0].price,
        "mid_price": parsed.mid_price,
        "spread_bps": parsed.spread_bps,
        "bid_depth_base": parsed.bid_depth,
        "ask_depth_base": parsed.ask_depth,
        "order_pressure": parsed.order_pressure,
    }


def _candle_reports(
    values: Mapping[str, Sequence[object]],
    symbol: str,
) -> dict[str, object]:
    if not values:
        raise Hip3QualificationError(f"{symbol} candle windows are empty")
    return {
        timeframe: _candle_report(rows, timeframe, symbol)
        for timeframe, rows in sorted(values.items())
    }


def _candle_report(
    rows: Sequence[object],
    timeframe: str,
    symbol: str,
) -> dict[str, object]:
    interval = _CANDLE_INTERVAL_MS.get(timeframe)
    if interval is None:
        raise Hip3QualificationError(
            f"{symbol} unsupported candle interval {timeframe}"
        )
    opens = tuple(
        nonnegative_integer(mapping(row, "candle").get("t"), "candle open")
        for row in rows
    )
    if not opens:
        raise Hip3QualificationError(f"{symbol} {timeframe} candles are empty")
    if tuple(sorted(set(opens))) != opens:
        raise Hip3QualificationError(
            f"{symbol} {timeframe} candles are not unique and ordered"
        )
    deltas = tuple(right - left for left, right in zip(opens, opens[1:], strict=False))
    if any(delta < interval for delta in deltas):
        raise Hip3QualificationError(f"{symbol} {timeframe} candle spacing is invalid")
    gaps = tuple(delta for delta in deltas if delta > interval)
    return {
        "row_count": len(opens),
        "first_open_ms": opens[0],
        "last_open_ms": opens[-1],
        "gap_count": len(gaps),
        "maximum_gap_ms": max(gaps, default=interval),
        "api_row_cap_reached": len(opens) >= _PUBLIC_CANDLE_ROW_CAP,
    }


def _pair_value(
    dex: Mapping[str, object],
    field: str,
    symbol: str,
) -> float:
    rows = sequence(dex.get(field), field)
    matches = []
    for row in rows:
        pair = sequence(row, f"{field} pair")
        if len(pair) != 2:
            raise Hip3QualificationError(f"{field} pair must contain two values")
        if pair[0] == symbol:
            matches.append(positive_number(pair[1], f"{symbol} {field}"))
    if len(matches) != 1:
        raise Hip3QualificationError(f"{symbol} {field} must contain one value")
    return matches[0]


def _deployer_fee_scale(
    market: Mapping[str, object], dex: Mapping[str, object]
) -> float:
    raw_value = market.get("deployerFeeScale")
    if raw_value is None:
        raw_value = dex.get("deployerFeeScale")
    value = number(raw_value, "deployerFeeScale")
    if not 0.0 <= value <= 3.0:
        raise Hip3QualificationError("deployerFeeScale must be between zero and three")
    return value


def _margin_tables(
    metadata: Mapping[str, object],
) -> dict[int, list[dict[str, float | int]]]:
    output: dict[int, list[dict[str, float | int]]] = {}
    for raw in sequence(metadata.get("marginTables"), "marginTables"):
        pair = sequence(raw, "margin table")
        if len(pair) != 2:
            raise Hip3QualificationError("margin table must contain id and definition")
        table_id = positive_integer(pair[0], "margin table id")
        definition = mapping(pair[1], "margin table definition")
        tiers = [
            _margin_tier(row, table_id)
            for row in sequence(definition.get("marginTiers"), "margin tiers")
        ]
        if not tiers or table_id in output:
            raise Hip3QualificationError(
                "margin table definitions must be unique and nonempty"
            )
        output[table_id] = tiers
    return output


def _margin_tier(value: object, table_id: int) -> dict[str, float | int]:
    tier = mapping(value, f"margin table {table_id} tier")
    lower = number(tier.get("lowerBound"), "margin tier lowerBound")
    if lower < 0.0:
        raise Hip3QualificationError("margin tier lowerBound must be nonnegative")
    return {
        "lower_bound_usd": lower,
        "max_leverage": positive_integer(
            tier.get("maxLeverage"), "margin tier maxLeverage"
        ),
    }


def _collateral(value: object, token_index: int) -> dict[str, object]:
    tokens = sequence(mapping(value, "spot metadata").get("tokens"), "spot tokens")
    matches = [
        mapping(row, "spot token")
        for row in tokens
        if mapping(row, "spot token").get("index") == token_index
    ]
    if len(matches) != 1:
        raise Hip3QualificationError(
            f"collateral token index {token_index} must resolve exactly once"
        )
    token = matches[0]
    return {
        "name": text(token.get("name"), "collateral token name"),
        "index": token_index,
        "size_decimals": nonnegative_integer(
            token.get("szDecimals"), "collateral szDecimals"
        ),
        "wei_decimals": nonnegative_integer(
            token.get("weiDecimals"), "collateral weiDecimals"
        ),
    }


def _positive_fee_multiplier(scale: float, growth_mode: bool) -> float:
    hip3_scale = scale + 1.0 if scale < 1.0 else scale * 2.0
    return hip3_scale * (0.1 if growth_mode else 1.0)


def _require_requested_dex(symbols: tuple[str, ...], dex_name: str) -> None:
    for symbol in symbols:
        symbol_dex, _ = validate_hip3_symbol(symbol)
        if symbol_dex != dex_name:
            raise Hip3QualificationError(
                f"HIP-3 symbol {symbol} does not belong to dex {dex_name}"
            )


def _observed_at(value: str) -> str:
    normalized = text(value, "observed_at_utc")
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Hip3QualificationError("observed_at_utc must be timezone-aware")
    return normalized


def _readiness(
    all_margin_tables_resolved: bool,
    all_fee_multipliers_resolved: bool,
) -> dict[str, object]:
    return {
        "identity_verified": True,
        "public_market_data_available": True,
        "all_margin_tables_resolved": all_margin_tables_resolved,
        "all_fee_multipliers_resolved": all_fee_multipliers_resolved,
        "live_execution_supported": False,
        "strategy_transfer_validated": False,
        "required_next_steps": [
            "add explicit HIP-3 SDK namespace support",
            "validate independent dex account reconciliation and fee attribution",
            "collect venue-matched chronological data beyond the public candle cap",
            "evaluate both sides without pooling HIP-3 evidence with crypto",
            "add read-only backend and TUI roster telemetry before execution",
        ],
    }
