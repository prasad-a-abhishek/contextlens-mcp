"""Typed exception hierarchy for contextlens.

All public APIs catch and re-raise these as structured errors so callers
never see an uncaught ``ValueError`` / ``TypeError`` from a malformed input
(see Invariant 21 in HIGHEST_QUALITY_REPO.md).
"""

from __future__ import annotations

from typing import Any


class ContextlensError(Exception):
    """Base class for every public-API error.

    Carries an optional ``code`` (a stable machine-readable string) and
    a ``details`` mapping that survives across the JSON-Lines and JSON-RPC
    boundaries.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "contextlens_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details: dict[str, Any] = dict(details) if details else {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": str(self), "details": self.details}


class InvalidJSON(ContextlensError):
    """Raised when a JSON-Lines / JSON-RPC frame cannot be decoded."""

    def __init__(self, message: str = "invalid JSON", *, raw: str | None = None) -> None:
        super().__init__(message, code="invalid_json", details={"raw": raw} if raw else {})


class InvalidRequest(ContextlensError):
    """Raised when the decoded frame is not a valid request envelope."""

    def __init__(self, message: str, *, request_id: Any = None) -> None:
        super().__init__(
            message, code="invalid_request", details={"id": request_id}
        )


class UnknownOperation(ContextlensError):
    """Raised when an ``op`` field names a handler we do not implement."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"unknown operation: {operation!r}",
            code="unknown_operation",
            details={"operation": operation},
        )


__all__ = [
    "ContextlensError",
    "InvalidJSON",
    "InvalidRequest",
    "UnknownOperation",
]