"""JSON-Lines dispatcher used by the ``contextlens`` CLI and the
:class:`contextlens.mcp.MCPServer` for non-JSON-RPC endpoints.

Each input frame is a single JSON object:

- ``{"op": "estimate", ...}`` → returns an :class:`Estimate`.
- ``{"op": "truncate", ...}`` → returns a :class:`TruncateResult`.
- ``{"op": "budget", ...}``  → returns a :class:`BudgetReport`.

Errors never crash the dispatcher. A malformed frame is converted into
a single-line JSON error response (``{"ok": false, "error": ...}``) so
a long-running process can keep serving subsequent requests.

The dispatcher is total on its inputs: passing a non-dict, a missing
``op``, or an unknown operation produces a structured error instead of
an uncaught exception.
"""

from __future__ import annotations

import json
from typing import Any

from contextlens.budget import Message, budget_report
from contextlens.errors import ContextlensError
from contextlens.estimator import estimate
from contextlens.truncation import truncate

__all__ = ["handle_request", "handle_raw_line", "dispatch"]


def handle_raw_line(line: str) -> str:
    """Parse one JSONL frame and return the JSON response line.

    Whitespace-only lines round-trip to an empty reply (the dispatcher
    is silent for blank input — handy for piped ``grep``/``awk``).
    """
    stripped = line.strip()
    if not stripped:
        return ""
    try:
        request = json.loads(stripped, strict=False)
    except json.JSONDecodeError as exc:
        return _error_response(
            code="invalid_json",
            message=f"could not decode JSON: {exc.msg}",
            details={"line": stripped, "position": exc.pos},
        )
    return handle_request(request)


def handle_request(request: Any) -> str:
    """Route a decoded request to its handler.

    Always returns a single-line JSON string — never raises.
    """
    if not isinstance(request, dict):
        return _error_response(
            code="invalid_request",
            message="request must be a JSON object",
            details={"type": type(request).__name__},
        )
    op = request.get("op")
    if not isinstance(op, str):
        return _error_response(
            code="invalid_request",
            message="request is missing string field 'op'",
            details={"op": op},
        )
    try:
        if op == "estimate":
            return _ok(_handle_estimate(request))
        if op == "truncate":
            return _ok(_handle_truncate(request))
        if op == "budget":
            return _ok(_handle_budget(request))
        return _error_response(
            code="unknown_operation",
            message=f"unknown operation: {op!r}",
            details={"operation": op},
        )
    except ContextlensError as exc:
        return _error_response(
            code=exc.code, message=str(exc), details=exc.details
        )
    except (TypeError, ValueError) as exc:
        return _error_response(
            code="invalid_request", message=str(exc), details={}
        )


def dispatch(stdin_text: str) -> str:
    """Process a multi-line JSONL payload and return the joined responses.

    Every non-blank input line produces exactly one output line. Blank
    input lines produce no output.
    """
    out_lines: list[str] = []
    for line in stdin_text.splitlines():
        response = handle_raw_line(line)
        if response:
            out_lines.append(response)
    return "\n".join(out_lines)


def _handle_estimate(request: dict[str, Any]) -> dict[str, Any]:
    text = request.get("text", "")
    encoding = request.get("encoding", "cl100k_approx")
    message_overhead = request.get("message_overhead", 4)
    est = estimate(
        text,
        encoding=encoding,  # type: ignore[arg-type]
        message_overhead=message_overhead,
    )
    return {"op": "estimate", **est.details, "tokens": est.tokens, "confidence": est.confidence}


def _handle_truncate(request: dict[str, Any]) -> dict[str, Any]:
    text = request.get("text", "")
    max_tokens = request.get("max_tokens", 4000)
    strategy = request.get("strategy", "tail")
    message_overhead = request.get("message_overhead", 0)
    res = truncate(
        text,
        max_tokens=max_tokens,
        strategy=strategy,  # type: ignore[arg-type]
        message_overhead=message_overhead,
    )
    return {
        "op": "truncate",
        "text": res.text,
        "tokens": res.tokens,
        "truncated": res.truncated,
        "strategy": res.strategy,
        "budget": res.budget,
        "original_tokens": res.original_tokens,
    }


def _handle_budget(request: dict[str, Any]) -> dict[str, Any]:
    messages = request.get("messages", [])
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    limit = request.get("limit", 8192)
    message_overhead = request.get("message_overhead", 4)
    normalised = [
        m if isinstance(m, Message) else Message.from_mapping(m) for m in messages
    ]
    report = budget_report(
        normalised, limit=limit, message_overhead=message_overhead
    )
    return {
        "op": "budget",
        "total_tokens": report.total_tokens,
        "limit": report.limit,
        "remaining": report.remaining,
        "overflow": report.overflow,
        "overhead_per_message": report.overhead_per_message,
        "per_message": list(report.per_message),
        "count": report.details["count"],
    }


def _ok(payload: dict[str, Any]) -> str:
    payload = {"ok": True, **payload}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _error_response(*, code: str, message: str, details: dict[str, Any]) -> str:
    return json.dumps(
        {"ok": False, "error": code, "message": message, "details": details},
        ensure_ascii=False,
        separators=(",", ":"),
    )