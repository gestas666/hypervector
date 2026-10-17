"""Default unit tests are offline; external evidence/integrations are opt-in."""

from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_unit_test_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail at the network boundary when a unit test missed a public API mock."""
    if request.node.get_closest_marker("network") or request.node.get_closest_marker(
        "integration"
    ):
        return

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(
            "network access is forbidden in unit tests; inject a local fixture or mock"
        )

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture(autouse=True)
def forbid_unit_operational_data(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep default test results independent of real paper/live journal contents."""
    import builtins
    import io
    import os
    from pathlib import Path

    if any(
        request.node.get_closest_marker(marker)
        for marker in ("network", "integration", "evidence", "performance")
    ):
        return
    root = Path(__file__).resolve().parents[1] / "data"
    protected = tuple((root / name).resolve() for name in ("live", "paper"))
    original = builtins.open

    def isolated_open(file: object, *args: object, **kwargs: object) -> object:
        if isinstance(file, (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(file)).resolve()
            if any(path == parent or parent in path.parents for parent in protected):
                raise AssertionError(
                    f"unit access to operational trading data is forbidden; use a temporary ledger: {path}"
                )
        return original(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", isolated_open)
    monkeypatch.setattr(io, "open", isolated_open)
