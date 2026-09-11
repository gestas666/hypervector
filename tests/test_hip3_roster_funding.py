"""Unsigned funding acquisition, exact symbol binding and unavailable-data tests."""

from __future__ import annotations

import copy

import pytest

SYMBOLS = ("xyz:SPCX", "xyz:SNDK", "xyz:BRENTOIL")


class _Info:
    """Supply a recorded-shaped public response without network or signing."""

    def __init__(self, response: object) -> None:
        """Retain one response fixture and an initially empty request ledger."""
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, path: str, payload: dict[str, object]) -> object:
        """Record the precise read-only namespace request."""
        self.calls.append((path, payload))
        return self.response


def _response(value: object = "-0.000025") -> list[object]:
    """Keep request order different from metadata order to expose positional bugs."""
    return [
        {
            "universe": [
                {"name": symbol}
                for symbol in ("xyz:OTHER", "xyz:BRENTOIL", "xyz:SPCX", "xyz:SNDK")
            ]
        },
        [
            {"funding": "99.0"},
            {"funding": "0.0000125"},
            {"funding": value},
            {"funding": "0.0"},
        ],
    ]


def test_funding_uses_one_unsigned_exact_dex_request_and_preserves_hourly_units() -> (
    None
):
    """Signed rates map by exact identity without multiplying or dividing by eight."""
    from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader

    response = _response()
    prior = copy.deepcopy(response)
    info = _Info(response)
    rates = Hip3RosterFundingReader(info=info, symbols=SYMBOLS).snapshot()

    assert info.calls == [("/info", {"type": "metaAndAssetCtxs", "dex": "xyz"})]
    assert rates == {"xyz:SPCX": -0.000025, "xyz:SNDK": 0.0, "xyz:BRENTOIL": 0.0000125}
    assert response == prior


@pytest.mark.parametrize("missing", [True, False])
def test_absent_funding_is_unavailable_without_replacing_other_market_values(
    missing: bool,
) -> None:
    """A missing/null funding field is distinct from an observed zero."""
    from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader

    response = _response(None)
    if missing:
        response[1][2].pop("funding")
    result = Hip3RosterFundingReader(info=_Info(response), symbols=SYMBOLS).snapshot()
    assert result["xyz:SPCX"] is None
    assert result["xyz:SNDK"] == 0.0


@pytest.mark.parametrize("value", [True, 0.1, "nan", "inf", "-inf", "bad"])
def test_invalid_funding_cannot_be_published_as_current(value: object) -> None:
    """Schema/type/nonfinite failures propagate to explicit unavailable publication."""
    from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader

    reader = Hip3RosterFundingReader(info=_Info(_response(value)), symbols=SYMBOLS)
    with pytest.raises(ValueError, match="funding"):
        reader.snapshot()


@pytest.mark.parametrize(
    "symbols", [(), ("SPCX",), ("xyz:SPCX", "cash:WTI"), ("xyz:SPCX", "xyz:SPCX")]
)
def test_funding_rejects_invalid_roster_before_request(
    symbols: tuple[str, ...],
) -> None:
    """Only a nonempty, unique, same-dex HIP-3 roster can be queried."""
    from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader

    info = _Info(_response())
    with pytest.raises(ValueError):
        Hip3RosterFundingReader(info=info, symbols=symbols)
    assert info.calls == []


@pytest.mark.parametrize("info", [object(), None])
def test_funding_requires_the_unsigned_context_read_surface(info: object) -> None:
    """An incompatible SDK boundary must fail before polling."""
    from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader

    with pytest.raises(ValueError, match="Info.*post"):
        Hip3RosterFundingReader(info=info, symbols=SYMBOLS)


@pytest.mark.parametrize(
    "defect", ["shape", "alignment", "duplicate", "missing", "context"]
)
def test_funding_rejects_ambiguous_context_binding(defect: str) -> None:
    """An apparently plausible rate cannot cross a metadata/context identity error."""
    from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader

    response = _response()
    if defect == "shape":
        response.pop()
    elif defect == "alignment":
        response[1].pop()
    elif defect == "duplicate":
        response[0]["universe"][0]["name"] = "xyz:SPCX"
    elif defect == "missing":
        response[0]["universe"][2]["name"] = "xyz:WRONG"
    else:
        response[1][2] = None
    with pytest.raises(ValueError):
        Hip3RosterFundingReader(info=_Info(response), symbols=SYMBOLS).snapshot()


def test_each_snapshot_refreshes_rates_and_does_not_cache_previous_success() -> None:
    """A subsequent refresh must use its own response or raise on missing evidence."""
    from hypervector.research.hip3_roster_funding import Hip3RosterFundingReader

    info = _Info(_response())
    reader = Hip3RosterFundingReader(info=info, symbols=SYMBOLS)
    assert reader.snapshot()["xyz:SPCX"] == -0.000025
    info.response = _response("0.00001")
    assert reader.snapshot()["xyz:SPCX"] == 0.00001
    info.response = None
    with pytest.raises(ValueError):
        reader.snapshot()
    assert len(info.calls) == 3
