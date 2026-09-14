"""Independent rational reconstruction for simultaneous native-engine portfolio receipts."""

from dataclasses import dataclass
from fractions import Fraction

from native_replay_partial_protective_fixture import PartialProtectiveFixture

INITIAL_CASH = Fraction(5000)
DECIMAL_TOLERANCE = Fraction(1, 10**40)


@dataclass(frozen=True)
class AssetReceiptEconomics:
    """Per-symbol economics derived solely from original raw receipt values and declared marks."""

    remaining_signed: Fraction
    entry_price: Fraction
    gross: Fraction
    fees: Fraction
    unrealized: Fraction
    notional: Fraction


def portfolio_receipt_oracle(replay: PartialProtectiveFixture) -> dict[str, AssetReceiptEconomics]:
    """Compare independent per-symbol inventory, cash, fees and equity with the shared account."""
    result = {
        symbol: _asset_receipts(
            [row for row in replay.fills if row["coin"] == symbol], Fraction(replay.marks[symbol])
        )
        for symbol in replay.symbols
    }
    account = replay.account.snapshot()
    assert account.funding_usd == 0, "these short prescribed scenarios contain no funding events"
    cash = INITIAL_CASH + sum(row.gross - row.fees for row in result.values())
    unrealized = sum(row.unrealized for row in result.values())
    assert abs(Fraction(account.cash_usd) - cash) < DECIMAL_TOLERANCE
    assert abs(Fraction(account.equity_usd) - cash - unrealized) < DECIMAL_TOLERANCE
    assert (
        abs(Fraction(account.gross_notional_usd) - sum(row.notional for row in result.values()))
        < DECIMAL_TOLERANCE
    )
    assert set(account.positions) == {
        symbol for symbol, row in result.items() if row.remaining_signed
    }
    for symbol, position in account.positions.items():
        expected = result[symbol]
        assert Fraction(position.quantity_signed) == expected.remaining_signed
        assert abs(Fraction(position.entry_price) - expected.entry_price) < DECIMAL_TOLERANCE
    replay.assert_native_account_agreement()
    return result


def _asset_receipts(rows: list[dict[str, object]], mark: Fraction) -> AssetReceiptEconomics:
    entries = [row for row in rows if _text(row, "dir").startswith("Open ")]
    exits = [row for row in rows if _text(row, "dir").startswith("Close ")]
    assert entries and len(entries) + len(exits) == len(rows)
    assert len({row["tid"] for row in rows}) == len(rows)
    sign = 1 if entries[0]["side"] == "B" else -1
    assert all(row["side"] == entries[0]["side"] for row in entries)
    assert all(row["side"] != entries[0]["side"] for row in exits)
    opened = sum((Fraction(_text(row, "sz")) for row in entries), Fraction(0))
    price = (
        sum(
            (Fraction(_text(row, "sz")) * Fraction(_text(row, "px")) for row in entries),
            Fraction(0),
        )
        / opened
    )
    remaining = sign * (opened - sum((Fraction(_text(row, "sz")) for row in exits), Fraction(0)))
    gross = sign * sum(
        (Fraction(_text(row, "sz")) * (Fraction(_text(row, "px")) - price) for row in exits),
        Fraction(0),
    )
    fees = sum((Fraction(_text(row, "fee")) for row in rows), Fraction(0))
    return AssetReceiptEconomics(
        remaining, price, gross, fees, remaining * (mark - price), abs(remaining) * mark
    )


def _text(row: dict[str, object], key: str) -> str:
    value = row[key]
    assert isinstance(value, str) and value, (key, value)
    return value
