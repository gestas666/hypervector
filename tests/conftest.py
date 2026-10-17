"""Default unit tests are offline; external evidence/integrations are opt-in."""

from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_unit_test_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail at the network boundary when a unit test missed a public API mock."""
    if request.node.get_closest_marker("network") or request.node.get_closest_marker("integration"):
        return

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("network access is forbidden in unit tests; inject a local fixture or mock")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
