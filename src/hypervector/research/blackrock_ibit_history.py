"""Fail-closed normalization of the official BlackRock IBIT history sheet."""

from __future__ import annotations

from datetime import datetime
from html.parser import HTMLParser
import math

import pandas as pd


_HISTORICAL_SHEET = "Historical"
_EXPECTED_HEADERS = (
    "As Of",
    "NAV per Share",
    "Ex-Dividends",
    "Shares Outstanding",
)
_SPLIT_FACTORS = (2.0, 3.0, 4.0, 5.0, 10.0)
_SPLIT_SHARES_TOLERANCE = 0.02
_SPLIT_NAV_TOLERANCE = 0.20
IBIT_COMPLETE_SHARES_REQUIRED_FROM = pd.Timestamp("2025-07-28")


class _HistoricalWorksheetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.historical_count = 0
        self.rows: list[tuple[str, ...]] = []
        self.malformed = False
        self._worksheet_name: str | None = None
        self._capture = False
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._in_data = False
        self._cells: list[str] = []
        self._text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        name = _local_tag_name(tag)
        if name == "worksheet":
            self._start_worksheet(attrs)
        elif self._capture and name == "table":
            self._start_table()
        elif self._capture and name == "row":
            self._start_row()
        elif self._capture and name == "cell":
            self._start_cell()
        elif self._capture and name == "data":
            self._start_data()

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        name = _local_tag_name(tag)
        if name == "worksheet":
            self._end_worksheet()
        elif self._capture and name == "table":
            self._end_table()
        elif self._capture and name == "row":
            self._end_row()
        elif self._capture and name == "cell":
            self._end_cell()
        elif self._capture and name == "data":
            self._end_data()

    def handle_data(self, data: str) -> None:
        if self._capture and self._in_data:
            self._text.append(data)

    def structurally_complete(self) -> bool:
        return not any(
            (
                self.malformed,
                self._worksheet_name is not None,
                self._capture,
                self._in_table,
                self._in_row,
                self._in_cell,
                self._in_data,
            )
        )

    def _start_worksheet(self, attrs: list[tuple[str, str | None]]) -> None:
        if self._worksheet_name is not None:
            self.malformed = True
        name = _worksheet_name(attrs)
        self._worksheet_name = name
        self._capture = name == _HISTORICAL_SHEET
        if self._capture:
            self.historical_count += 1

    def _end_worksheet(self) -> None:
        if self._worksheet_name is None:
            self.malformed = True
            return
        if self._capture and any(
            (self._in_table, self._in_row, self._in_cell, self._in_data)
        ):
            self.malformed = True
        self._worksheet_name = None
        self._capture = False
        self._reset_structure()

    def _start_table(self) -> None:
        if self._in_table or self._in_row or self._in_cell or self._in_data:
            self.malformed = True
        self._in_table = True

    def _end_table(self) -> None:
        if not self._in_table or self._in_row or self._in_cell or self._in_data:
            self.malformed = True
        self._in_table = False

    def _start_row(self) -> None:
        if not self._in_table or self._in_row or self._in_cell or self._in_data:
            self.malformed = True
        self._in_row = True
        self._cells = []

    def _end_row(self) -> None:
        if not self._in_row or self._in_cell or self._in_data:
            self.malformed = True
        else:
            self.rows.append(tuple(self._cells))
        self._in_row = False
        self._cells = []

    def _start_cell(self) -> None:
        if not self._in_row or self._in_cell or self._in_data:
            self.malformed = True
        self._in_cell = True
        self._text = []

    def _end_cell(self) -> None:
        if not self._in_cell or self._in_data:
            self.malformed = True
        else:
            self._cells.append(_normalized_text("".join(self._text)))
        self._in_cell = False
        self._text = []

    def _start_data(self) -> None:
        if not self._in_cell or self._in_data:
            self.malformed = True
        self._in_data = True

    def _end_data(self) -> None:
        if not self._in_data:
            self.malformed = True
        self._in_data = False

    def _reset_structure(self) -> None:
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._in_data = False
        self._cells = []
        self._text = []


def parse_blackrock_ibit_history(
    content: bytes,
    *,
    allow_share_placeholders_before: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return validated ascending IBIT NAV and shares-outstanding history."""
    if not content:
        raise ValueError("BlackRock IBIT fund-data response is empty")
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("BlackRock IBIT fund-data response is not UTF-8") from exc
    parser = _HistoricalWorksheetParser()
    parser.feed(source)
    parser.close()
    if parser.historical_count != 1:
        raise ValueError("BlackRock source requires exactly one Historical worksheet")
    if not parser.structurally_complete():
        raise ValueError("BlackRock Historical worksheet is malformed")
    cutoff = _placeholder_cutoff(allow_share_placeholders_before)
    frame = _frame_from_rows(parser.rows, cutoff)
    _reject_split_like_discontinuities(frame)
    return frame


def _worksheet_name(attrs: list[tuple[str, str | None]]) -> str | None:
    names = [
        value
        for key, value in attrs
        if key.casefold() in {"name", "ss:name"} and value is not None
    ]
    return names[0] if len(names) == 1 else None


def _local_tag_name(value: str) -> str:
    return value.rsplit(":", maxsplit=1)[-1].casefold()


def _normalized_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _frame_from_rows(
    rows: list[tuple[str, ...]],
    placeholder_cutoff: pd.Timestamp | None,
) -> pd.DataFrame:
    nonempty = [row for row in rows if any(row)]
    headers = [index for index, row in enumerate(nonempty) if row == _EXPECTED_HEADERS]
    if headers != [0]:
        raise ValueError("BlackRock Historical worksheet columns drifted")
    values = nonempty[1:]
    if not values:
        raise ValueError("BlackRock Historical worksheet contains no data rows")
    if any(len(row) != len(_EXPECTED_HEADERS) for row in values):
        raise ValueError("BlackRock Historical worksheet row width drifted")
    filtered, excluded = _filtered_share_placeholders(values, placeholder_cutoff)
    frame = pd.DataFrame(filtered, columns=_EXPECTED_HEADERS)
    result = pd.DataFrame(
        {
            "as_of_date": [_as_of_date(value) for value in frame["As Of"]],
            "nav_per_share": [_nav(value) for value in frame["NAV per Share"]],
            "shares_outstanding": [
                _shares(value) for value in frame["Shares Outstanding"]
            ],
        }
    )
    result = _ascending_dates(result)
    result.attrs["excluded_share_placeholder_dates"] = tuple(
        value.date().isoformat() for value in sorted(excluded)
    )
    return result


def _placeholder_cutoff(value: pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    cutoff = pd.Timestamp(value)
    if cutoff.tz is not None or cutoff != cutoff.normalize():
        raise ValueError("BlackRock share-placeholder cutoff must be a naive date")
    return cutoff


def _filtered_share_placeholders(
    rows: list[tuple[str, ...]],
    cutoff: pd.Timestamp | None,
) -> tuple[list[tuple[str, ...]], list[pd.Timestamp]]:
    filtered: list[tuple[str, ...]] = []
    excluded: list[pd.Timestamp] = []
    for row in rows:
        if row[3] != "--":
            filtered.append(row)
            continue
        as_of = _as_of_date(row[0])
        if cutoff is None or as_of >= cutoff:
            raise ValueError(
                f"BlackRock IBIT share placeholder is not allowed: {row[0]}"
            )
        excluded.append(as_of)
    if not filtered:
        raise ValueError("BlackRock Historical worksheet has no complete share rows")
    return filtered, excluded


def _as_of_date(value: str) -> pd.Timestamp:
    try:
        return pd.Timestamp(datetime.strptime(value, "%b %d, %Y"))
    except ValueError as exc:
        raise ValueError(f"BlackRock IBIT as-of date is invalid: {value}") from exc


def _nav(value: str) -> float:
    number = _number(value, "NAV per share")
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError("BlackRock IBIT NAV per share must be finite and positive")
    return number


def _shares(value: str) -> int:
    number = _number(value, "shares outstanding")
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(
            "BlackRock IBIT shares outstanding must be finite and positive"
        )
    rounded = round(number)
    if not math.isclose(number, rounded, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("BlackRock IBIT shares outstanding must be whole units")
    return int(rounded)


def _number(value: str, field: str) -> float:
    normalized = value.replace("$", "").replace(",", "").strip()
    try:
        return float(normalized)
    except ValueError as exc:
        raise ValueError(f"BlackRock IBIT {field} is not numeric: {value}") from exc


def _ascending_dates(frame: pd.DataFrame) -> pd.DataFrame:
    dates = pd.DatetimeIndex(frame["as_of_date"])
    if dates.has_duplicates:
        raise ValueError("BlackRock IBIT history contains duplicate as-of dates")
    if not dates.is_monotonic_increasing and not dates.is_monotonic_decreasing:
        raise ValueError("BlackRock IBIT as-of dates must be strictly ordered")
    result = frame if dates.is_monotonic_increasing else frame.iloc[::-1]
    return result.reset_index(drop=True)


def _reject_split_like_discontinuities(frame: pd.DataFrame) -> None:
    for prior, current in zip(
        frame.iloc[:-1].itertuples(), frame.iloc[1:].itertuples()
    ):
        shares_ratio = current.shares_outstanding / prior.shares_outstanding
        nav_ratio = current.nav_per_share / prior.nav_per_share
        for factor in _SPLIT_FACTORS:
            if _near(shares_ratio, factor, _SPLIT_SHARES_TOLERANCE) and _near(
                nav_ratio, 1.0 / factor, _SPLIT_NAV_TOLERANCE
            ):
                raise ValueError(
                    "BlackRock IBIT history has a split-like discontinuity"
                )
            if _near(shares_ratio, 1.0 / factor, _SPLIT_SHARES_TOLERANCE) and _near(
                nav_ratio, factor, _SPLIT_NAV_TOLERANCE
            ):
                raise ValueError(
                    "BlackRock IBIT history has a split-like discontinuity"
                )


def _near(value: float, expected: float, relative_tolerance: float) -> bool:
    return abs(value / expected - 1.0) <= relative_tolerance
