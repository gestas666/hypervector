"""Technical-failure exceptions for the Phase 2 Nautilus runner.

Import-light (no NautilusTrader) so command handlers and checks can catch them
without loading the engine. Every class derives from ``ValueError`` or
``RuntimeError`` so the unified CLI maps it to ``{"ok": false, ...}`` and exit
code 1 even without a dedicated handler.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hypervector.export.schema import ExportSchemaError


class Phase2TechnicalFailure(RuntimeError):
    """A Nautilus historical run failed for a technical reason (never a gate).

    Raised instead of writing a success ``summary.json``: strategy errors,
    unusable signal lookups or engine faults must abort the trial
    (``SRS_HV1_NO_GATES``: only technical failure aborts).
    """

    def __init__(
        self,
        message: str,
        *,
        strategy: str | None = None,
        export_dir: Path | str | None = None,
        first_error: dict[str, Any] | str | None = None,
    ) -> None:
        self.strategy = strategy
        self.export_dir = str(export_dir) if export_dir is not None else None
        self.first_error = first_error
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error_type": type(self).__name__,
            "error": str(self),
            "strategy": self.strategy,
            "export_dir": self.export_dir,
            "first_error": self.first_error,
        }


class Phase2IntentError(Phase2TechnicalFailure):
    """The strategy signal builder raised while the engine was replaying bars."""


class UnsupportedNautilusSymbol(ValueError):
    """No instrument definition (precision / venue leverage) is known for a symbol."""

    def __init__(self, symbol: str, reason: str) -> None:
        self.symbol = symbol
        self.reason = reason
        super().__init__(f"nautilus run does not support symbol {symbol!r}: {reason}")


class UnknownStrategyError(ExportSchemaError):
    """The bundle names a strategy the registry does not know (invalid bundle)."""

    def __init__(self, path: Path | str, strategy_name: str) -> None:
        self.strategy_name = strategy_name
        super().__init__(
            path,
            [f"params.strategy {strategy_name!r} is not a registered strategy"],
        )
