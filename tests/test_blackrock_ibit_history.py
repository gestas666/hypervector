"""Tests for fail-closed parsing of official BlackRock IBIT history."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.blackrock_ibit_history import (
    parse_blackrock_ibit_history,
)


_HEADERS = ("As Of", "NAV per Share", "Ex-Dividends", "Shares Outstanding")


def test_parser_extracts_descending_source_as_ascending_history() -> None:
    """Issuer-newest-first rows must normalize without changing their values."""
    content = _workbook(
        [
            ("Aug 20, 2026", "$38.25", "-", "1,200"),
            ("Aug 19, 2026", "$37.50", "-", "1,100"),
            ("Aug 18, 2026", "$36.75", "-", "1,000"),
        ]
    )

    result = parse_blackrock_ibit_history(content)

    assert list(result) == [
        "as_of_date",
        "nav_per_share",
        "shares_outstanding",
    ]
    assert result["as_of_date"].tolist() == list(
        pd.to_datetime(["2026-08-18", "2026-08-19", "2026-08-20"])
    )
    assert result["nav_per_share"].tolist() == [36.75, 37.5, 38.25]
    assert result["shares_outstanding"].tolist() == [1000, 1100, 1200]


def test_parser_tolerates_embedded_html_and_unescaped_ampersand() -> None:
    """Non-strict issuer markup outside Historical must not break extraction."""
    content = _workbook(
        [("Aug 20, 2026", "38.25", "-", "1,200")],
        disclaimer="Terms & <b>conditions</b>",
    )

    result = parse_blackrock_ibit_history(content)

    assert len(result) == 1
    assert result.iloc[0]["shares_outstanding"] == 1200


def test_parser_accepts_official_ss_prefixed_structural_tags() -> None:
    """The endpoint qualifies Workbook, Worksheet, Table, Row, Cell, and Data."""
    content = _workbook([("Aug 20, 2026", "38.25", "-", "1,200")])
    for tag in ("Workbook", "Worksheet", "Table", "Row", "Cell", "Data"):
        content = content.replace(f"<{tag}".encode(), f"<ss:{tag}".encode())
        content = content.replace(f"</{tag}>".encode(), f"</ss:{tag}>".encode())

    result = parse_blackrock_ibit_history(content)

    assert result["shares_outstanding"].tolist() == [1200]


def test_parser_rejects_missing_or_duplicate_historical_worksheet() -> None:
    """Source identity requires exactly one Historical worksheet."""
    missing = _workbook([], worksheet_name="Holdings")
    duplicate = _workbook([("Aug 20, 2026", "38.25", "-", "1,200")]).replace(
        b"</Workbook>", _historical_sheet([]) + b"</Workbook>"
    )

    with pytest.raises(ValueError, match="exactly one Historical worksheet"):
        parse_blackrock_ibit_history(missing)
    with pytest.raises(ValueError, match="exactly one Historical worksheet"):
        parse_blackrock_ibit_history(duplicate)


def test_parser_rejects_malformed_historical_structure() -> None:
    """Unbalanced row markup must not yield a success-shaped partial frame."""
    content = _workbook([("Aug 20, 2026", "38.25", "-", "1,200")]).replace(
        b"</Row></Table></Worksheet></Workbook>",
        b"</Table></Worksheet></Workbook>",
        1,
    )

    with pytest.raises(ValueError, match="Historical worksheet is malformed"):
        parse_blackrock_ibit_history(content)


def test_parser_rejects_unexpected_historical_columns() -> None:
    """An issuer schema change must be explicit before normalization."""
    content = _workbook(
        [("Aug 20, 2026", "38.25", "-", "1,200")],
        headers=("As Of", "NAV per Share", "Ex-Dividends", "Shares Issued"),
    )

    with pytest.raises(ValueError, match="Historical worksheet columns drifted"):
        parse_blackrock_ibit_history(content)


@pytest.mark.parametrize(
    "rows, message",
    [
        (
            [
                ("Aug 20, 2026", "38", "-", "1,200"),
                ("Aug 20, 2026", "37", "-", "1,100"),
            ],
            "duplicate as-of dates",
        ),
        (
            [
                ("Aug 20, 2026", "38", "-", "1,200"),
                ("Aug 18, 2026", "36", "-", "1,000"),
                ("Aug 19, 2026", "37", "-", "1,100"),
            ],
            "strictly ordered",
        ),
    ],
)
def test_parser_rejects_duplicate_or_unordered_dates(
    rows: list[tuple[str, str, str, str]],
    message: str,
) -> None:
    """Date ambiguity must fail instead of being silently sorted away."""
    with pytest.raises(ValueError, match=message):
        parse_blackrock_ibit_history(_workbook(rows))


@pytest.mark.parametrize(
    "nav, shares, message",
    [
        ("0", "1,200", "NAV per share must be finite and positive"),
        ("NaN", "1,200", "NAV per share must be finite and positive"),
        ("38", "0", "shares outstanding must be finite and positive"),
        ("38", "Infinity", "shares outstanding must be finite and positive"),
        ("38", "1,200.5", "shares outstanding must be whole units"),
    ],
)
def test_parser_rejects_invalid_economic_fields(
    nav: str,
    shares: str,
    message: str,
) -> None:
    """Invalid NAV or share values cannot become causal input."""
    content = _workbook([("Aug 20, 2026", nav, "-", shares)])

    with pytest.raises(ValueError, match=message):
        parse_blackrock_ibit_history(content)


def test_parser_rejects_split_like_discontinuity() -> None:
    """A 3-for-1 shares/NAV discontinuity requires explicit registration."""
    content = _workbook(
        [
            ("Aug 20, 2026", "10.00", "-", "3,000"),
            ("Aug 19, 2026", "30.00", "-", "1,000"),
        ]
    )

    with pytest.raises(ValueError, match="split-like discontinuity"):
        parse_blackrock_ibit_history(content)


def test_parser_excludes_only_explicit_pre_window_share_placeholders() -> None:
    """Pre-window calendar placeholders are missing observations, not zero shares."""
    content = _workbook(
        [
            ("Aug 01, 2025", "30", "-", "1,200"),
            ("Mar 31, 2024", "20", "-", "--"),
            ("Mar 28, 2024", "20", "-", "1,000"),
        ]
    )

    result = parse_blackrock_ibit_history(
        content,
        allow_share_placeholders_before=pd.Timestamp("2025-07-28"),
    )

    assert result["as_of_date"].tolist() == list(
        pd.to_datetime(["2024-03-28", "2025-08-01"])
    )
    assert result.attrs["excluded_share_placeholder_dates"] == ("2024-03-31",)


def test_parser_rejects_share_placeholder_inside_required_window() -> None:
    """Missing shares at or after the frozen market start are a technical failure."""
    content = _workbook(
        [
            ("Jul 28, 2025", "30", "-", "--"),
            ("Jul 25, 2025", "30", "-", "1,000"),
        ]
    )

    with pytest.raises(ValueError, match="share placeholder is not allowed"):
        parse_blackrock_ibit_history(
            content,
            allow_share_placeholders_before=pd.Timestamp("2025-07-28"),
        )


def _workbook(
    rows: list[tuple[str, str, str, str]],
    *,
    headers: tuple[str, str, str, str] = _HEADERS,
    worksheet_name: str = "Historical",
    disclaimer: str = "Terms",
) -> bytes:
    prefix = (
        '<?xml version="1.0"?>'
        '<Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
        '<Worksheet ss:Name="Disclaimers"><Table><Row><Cell>'
        f'<Data ss:Type="String">{disclaimer}</Data>'
        "</Cell></Row></Table></Worksheet>"
    ).encode()
    return prefix + _historical_sheet(rows, headers, worksheet_name) + b"</Workbook>"


def _historical_sheet(
    rows: list[tuple[str, str, str, str]],
    headers: tuple[str, str, str, str] = _HEADERS,
    worksheet_name: str = "Historical",
) -> bytes:
    rendered = [_row(headers), *(_row(row) for row in rows)]
    return (
        f'<Worksheet ss:Name="{worksheet_name}"><Table>'
        + "".join(rendered)
        + "</Table></Worksheet>"
    ).encode()


def _row(values: tuple[str, str, str, str]) -> str:
    cells = "".join(
        f'<Cell><Data ss:Type="String">{value}</Data></Cell>' for value in values
    )
    return f"<Row>{cells}</Row>"
