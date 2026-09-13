"""Independent rational reconstruction from retained raw SNDK source depth."""

from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path

import pytest

from hypervector.research.native_replay_depth import BookLiquidity, ExactLevel, RecordedBook

FIXTURE = Path(__file__).parent / "fixtures/native_replay_sndk_book_20260701.json"


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("quantity", ["0.001", "0.306", "10", "1000"])
@pytest.mark.parametrize("level_index", [-1, 0, 9, 19])
def test_raw_source_matches_independent_cumulative_liquidity(
    side: str, quantity: str, level_index: int
) -> None:
    """Every matched lot and quote amount comes from original strings, without VWAP input."""
    data = json.loads(FIXTURE.read_text())
    normalized, raw = data["normalized_row"], data["raw_row"]
    source = RecordedBook(
        "source:20260701:first",
        raw["symbol"],
        normalized["ts_exchange_ms"],
        Decimal(data["quantity_step"]),
        tuple(ExactLevel(Decimal(row["px"]), Decimal(row["sz"])) for row in normalized["bids"]),
        tuple(ExactLevel(Decimal(row["px"]), Decimal(row["sz"])) for row in normalized["asks"]),
    )
    rows = raw["asks" if side == "buy" else "bids"]
    limit = Fraction(rows[max(level_index, 0)]["px"])
    if level_index == -1:
        limit += Fraction(-1 if side == "buy" else 1, 10)
    decimal_limit = Decimal(limit.numerator) / Decimal(limit.denominator)
    result = BookLiquidity(source).execute(side=side, quantity=Decimal(quantity), limit_price=decimal_limit)
    prior = Fraction(0)
    expected = []
    for row in rows:
        price, available = Fraction(row["px"]), Fraction(row["sz"])
        if price > limit if side == "buy" else price < limit:
            continue
        cumulative = min(Fraction(quantity), prior + available)
        if cumulative > prior:
            expected.append((price, cumulative - prior))
        prior = cumulative
    assert [(Fraction(row.price), Fraction(row.quantity)) for row in result.matches] == expected
    assert Fraction(result.filled_quantity) == prior
    assert Fraction(result.unfilled_quantity) == Fraction(quantity) - prior
    assert Fraction(result.quote_usd) == sum(price * size for price, size in expected)
    assert result.disposition == (
        "no_fill" if not prior else "complete" if prior == Fraction(quantity) else "partial"
    )
